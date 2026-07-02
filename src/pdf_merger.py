from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import PDFCheckConfig

MERGE_RESULT_COLUMNS = [
    "Nama File",
    "Path Sumber A",
    "Path Sumber B",
    "Path Output",
    "Total Halaman",
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
        row["Status"] = self.status
        row["Catatan"] = " ".join(_unique_non_empty(self.notes))
        return row


def merge_pdf_folders(
    source_a: str,
    source_b: str,
    output_folder: str,
    *,
    overwrite: bool = False,
    config: PDFCheckConfig | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[MergeResult]:
    _ = config
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
    _ = config
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
        if pair.output_path.exists() and overwrite:
            pair.output_path.unlink()
        output_doc = fitz.open()
        for document in documents:
            output_doc.insert_pdf(document)
        output_doc.save(str(pair.output_path))
        result.total_pages = sum(document.page_count for document in documents)
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
