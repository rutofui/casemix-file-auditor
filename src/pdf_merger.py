from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import (
    BILLING_KEYWORDS,
    LIP_KEYWORDS,
    PDFCheckConfig,
    SEP_KEYWORDS,
    contains_keyword,
    detect_document_titles_on_page,
    normalize_text,
)


MERGE_CATEGORY_ORDER = [
    "LIP",
    "SEP",
    "Resume Medis",
    "Triage",
    "Surat Perintah Rawat Inap",
    "Hasil Pemeriksaan",
    "Pemeriksaan Radiologi",
    "Rincian Tagihan",
    "Sisa",
]

MERGE_RESULT_COLUMNS = [
    "Nama File",
    "Path Sumber A",
    "Path Sumber B",
    "Path Output",
    "Total Halaman",
    "LIP",
    "SEP",
    "Resume Medis",
    "Triage",
    "Surat Perintah Rawat Inap",
    "Hasil Pemeriksaan",
    "Pemeriksaan Radiologi",
    "Rincian Tagihan",
    "Sisa",
    "Status",
    "Catatan",
]


@dataclass(frozen=True)
class MergePair:
    file_name: str
    source_a: Path
    source_b: Path
    output_path: Path


@dataclass
class MergeResult:
    file_name: str
    source_a: str = ""
    source_b: str = ""
    output_path: str = ""
    total_pages: int = 0
    category_counts: dict[str, int] = field(
        default_factory=lambda: {category: 0 for category in MERGE_CATEGORY_ORDER}
    )
    status: str = "Dilewati"
    notes: list[str] = field(default_factory=list)

    def to_row(self) -> dict[str, object]:
        row = {
            "Nama File": self.file_name,
            "Path Sumber A": self.source_a,
            "Path Sumber B": self.source_b,
            "Path Output": self.output_path,
            "Total Halaman": self.total_pages,
        }
        for category in MERGE_CATEGORY_ORDER:
            row[category] = int(self.category_counts.get(category, 0))
        row["Status"] = self.status
        row["Catatan"] = " ".join(_unique_non_empty(self.notes))
        return row


@dataclass(frozen=True)
class PageRef:
    source_index: int
    page_index: int
    category: str


def merge_pdf_folders(
    source_a: str,
    source_b: str,
    output_folder: str,
    *,
    overwrite: bool = False,
    config: PDFCheckConfig | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[MergeResult]:
    config = config or PDFCheckConfig(use_ocr=True)
    if not source_a.strip() or not source_b.strip() or not output_folder.strip():
        return [
            MergeResult(
                file_name="",
                status="Gagal",
                notes=["Folder Sumber A, Folder Sumber B, dan Folder Output wajib diisi."],
            )
        ]
    source_a_path = Path(source_a).expanduser()
    source_b_path = Path(source_b).expanduser()
    output_path = Path(output_folder).expanduser()

    setup_error = _validate_merge_inputs(source_a_path, source_b_path, output_path)
    if setup_error:
        return [MergeResult(file_name="", status="Gagal", notes=[setup_error])]

    output_path.mkdir(parents=True, exist_ok=True)

    files_a = _index_pdf_files(source_a_path)
    files_b = _index_pdf_files(source_b_path)
    results: list[MergeResult] = []

    all_names = sorted(set(files_a) | set(files_b))
    pairs: list[MergePair] = []
    for normalized_name in all_names:
        paths_a = files_a.get(normalized_name, [])
        paths_b = files_b.get(normalized_name, [])
        display_name = _display_name(paths_a, paths_b, normalized_name)
        if len(paths_a) > 1:
            results.append(
                MergeResult(
                    file_name=display_name,
                    source_a=" | ".join(str(path) for path in paths_a),
                    source_b=" | ".join(str(path) for path in paths_b),
                    status="Dilewati",
                    notes=["Nama file duplikat di Folder Sumber A."],
                )
            )
            continue
        if len(paths_b) > 1:
            results.append(
                MergeResult(
                    file_name=display_name,
                    source_a=" | ".join(str(path) for path in paths_a),
                    source_b=" | ".join(str(path) for path in paths_b),
                    status="Dilewati",
                    notes=["Nama file duplikat di Folder Sumber B."],
                )
            )
            continue
        if not paths_a:
            results.append(
                MergeResult(
                    file_name=display_name,
                    source_b=str(paths_b[0]),
                    status="Dilewati",
                    notes=["File hanya ada di Folder Sumber B."],
                )
            )
            continue
        if not paths_b:
            results.append(
                MergeResult(
                    file_name=display_name,
                    source_a=str(paths_a[0]),
                    status="Dilewati",
                    notes=["File hanya ada di Folder Sumber A."],
                )
            )
            continue
        pairs.append(
            MergePair(
                file_name=display_name,
                source_a=paths_a[0],
                source_b=paths_b[0],
                output_path=output_path / display_name,
            )
        )

    total_pairs = len(pairs)
    for index, pair in enumerate(pairs, start=1):
        if progress_callback is not None:
            progress_callback(index, total_pairs, pair.file_name)
        results.append(merge_pdf_pair(pair, overwrite=overwrite, config=config))

    return results


def merge_pdf_pair(
    pair: MergePair,
    *,
    overwrite: bool = False,
    config: PDFCheckConfig | None = None,
) -> MergeResult:
    config = config or PDFCheckConfig(use_ocr=True)
    result = MergeResult(
        file_name=pair.file_name,
        source_a=str(pair.source_a),
        source_b=str(pair.source_b),
        output_path=str(pair.output_path),
    )
    if pair.output_path.exists() and not overwrite:
        result.status = "Dilewati"
        result.notes.append("File output sudah ada dan opsi timpa tidak aktif.")
        return result

    try:
        import fitz
    except Exception as exc:
        result.status = "Gagal"
        result.notes.append(f"PyMuPDF belum tersedia: {exc}")
        return result

    documents: list[object] = []
    output_doc = None
    try:
        documents = [fitz.open(str(pair.source_a)), fitz.open(str(pair.source_b))]
        page_refs: list[PageRef] = []
        for source_index, document in enumerate(documents):
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                category, note = classify_pdf_page(page, config)
                if note:
                    result.notes.append(note)
                page_refs.append(
                    PageRef(
                        source_index=source_index,
                        page_index=page_index,
                        category=category,
                    )
                )
                result.category_counts[category] = result.category_counts.get(category, 0) + 1

        ordered_refs = sorted(
            page_refs,
            key=lambda ref: (
                MERGE_CATEGORY_ORDER.index(ref.category),
                ref.source_index,
                ref.page_index,
            ),
        )
        if pair.output_path.exists() and overwrite:
            pair.output_path.unlink()
        output_doc = fitz.open()
        for ref in ordered_refs:
            output_doc.insert_pdf(
                documents[ref.source_index],
                from_page=ref.page_index,
                to_page=ref.page_index,
            )
        output_doc.save(str(pair.output_path))
        result.total_pages = len(ordered_refs)
        result.status = "Berhasil"
    except Exception as exc:
        result.status = "Gagal"
        result.notes.append(f"Merge PDF gagal: {exc}")
    finally:
        if output_doc is not None:
            output_doc.close()
        for document in documents:
            document.close()

    return result


def classify_pdf_page(page: object, config: PDFCheckConfig | None = None) -> tuple[str, str]:
    config = config or PDFCheckConfig(use_ocr=True)
    page_text = page.get_text("text") or ""
    header_only_ocr = False
    note = ""

    if config.use_ocr and _page_needs_ocr_for_merge(page, page_text, config):
        try:
            from .pdf_checker import _get_paddleocr_engine, _ocr_page

            ocr_text = _ocr_page(page, _get_paddleocr_engine(config), config)
            if ocr_text.strip():
                page_text = f"{page_text}\n{ocr_text}" if page_text.strip() else ocr_text
                header_only_ocr = True
        except Exception as exc:
            note = f"OCR halaman gagal, halaman diklasifikasi dari teks digital/sisa: {exc}"

    return _classify_page_text(page_text, header_only_ocr=header_only_ocr), note


def _classify_page_text(page_text: str, *, header_only_ocr: bool = False) -> str:
    normalized = normalize_text(page_text)
    titles = set(detect_document_titles_on_page(page_text, header_only_ocr=header_only_ocr))

    if contains_keyword(normalized, LIP_KEYWORDS):
        return "LIP"
    if contains_keyword(normalized, SEP_KEYWORDS):
        return "SEP"
    if "Resume Medis" in titles:
        return "Resume Medis"
    if "Triage" in titles:
        return "Triage"
    if "Surat Perintah Rawat Inap" in titles:
        return "Surat Perintah Rawat Inap"
    if "Pemeriksaan Radiologi" in titles:
        return "Pemeriksaan Radiologi"
    if "Hasil Pemeriksaan" in titles:
        return "Hasil Pemeriksaan"
    if contains_keyword(normalized, BILLING_KEYWORDS):
        return "Rincian Tagihan"
    return "Sisa"


def build_merge_summary(results: list[MergeResult]) -> dict[str, int]:
    return {
        "Total kandidat": len(results),
        "Berhasil": sum(1 for result in results if result.status == "Berhasil"),
        "Dilewati": sum(1 for result in results if result.status == "Dilewati"),
        "Gagal": sum(1 for result in results if result.status == "Gagal"),
        "Total halaman output": sum(result.total_pages for result in results if result.status == "Berhasil"),
    }


def _validate_merge_inputs(source_a: Path, source_b: Path, output_path: Path) -> str:
    if not str(source_a).strip() or not str(source_b).strip() or not str(output_path).strip():
        return "Folder Sumber A, Folder Sumber B, dan Folder Output wajib diisi."
    if not source_a.exists() or not source_a.is_dir():
        return f"Folder Sumber A tidak ditemukan atau bukan folder: {source_a}"
    if not source_b.exists() or not source_b.is_dir():
        return f"Folder Sumber B tidak ditemukan atau bukan folder: {source_b}"
    if output_path.exists() and not output_path.is_dir():
        return f"Folder Output bukan folder: {output_path}"
    return ""


def _index_pdf_files(folder: Path) -> dict[str, list[Path]]:
    indexed: dict[str, list[Path]] = {}
    for pdf_path in folder.rglob("*.pdf"):
        indexed.setdefault(pdf_path.name.casefold(), []).append(pdf_path)
    for paths in indexed.values():
        paths.sort(key=lambda path: str(path).casefold())
    return indexed


def _display_name(paths_a: list[Path], paths_b: list[Path], normalized_name: str) -> str:
    for paths in (paths_a, paths_b):
        if paths:
            return paths[0].name
    return normalized_name


def _page_needs_ocr_for_merge(page: object, page_text: str, config: PDFCheckConfig) -> bool:
    if len(normalize_text(page_text)) >= config.min_page_text_chars:
        return False
    try:
        from .pdf_checker import _page_has_scan

        return _page_has_scan(page, page_text, config)
    except Exception:
        return False


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
