from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import traceback

from .config import extract_sep_values
from .pdf_parallel import automatic_pdf_worker_count


RENAME_RESULT_COLUMNS = [
    "Nama File Lama",
    "Nama File Baru",
    "Path Lama",
    "Path Baru",
    "SEP Terdeteksi",
    "Status",
    "Catatan",
]


@dataclass
class RenameResult:
    old_name: str
    new_name: str = ""
    old_path: str = ""
    new_path: str = ""
    sep_detected: str = ""
    status: str = "Dilewati"
    notes: list[str] = field(default_factory=list)

    def to_row(self) -> dict[str, object]:
        return {
            "Nama File Lama": self.old_name,
            "Nama File Baru": self.new_name,
            "Path Lama": self.old_path,
            "Path Baru": self.new_path,
            "SEP Terdeteksi": self.sep_detected,
            "Status": self.status,
            "Catatan": " ".join(_unique_non_empty(self.notes)),
        }


@dataclass(frozen=True)
class SepScanResult:
    path: Path
    sep: str = ""
    readable: bool = False
    error: str = ""


def rename_pdfs_by_sep(
    folder_path: str,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[RenameResult]:
    folder = Path(folder_path).expanduser()
    if not folder_path.strip():
        return [RenameResult(old_name="", status="Gagal", notes=["Folder PDF Lokal wajib diisi."])]
    if not folder.exists():
        return [
            RenameResult(
                old_name="",
                old_path=str(folder),
                status="Gagal",
                notes=["Folder PDF tidak ditemukan."],
            )
        ]
    if not folder.is_dir():
        return [
            RenameResult(
                old_name=folder.name,
                old_path=str(folder),
                status="Gagal",
                notes=["Path bukan folder."],
            )
        ]

    pdf_paths = sorted(folder.rglob("*.pdf"), key=lambda path: str(path).lower())
    if not pdf_paths:
        return [
            RenameResult(
                old_name="",
                old_path=str(folder),
                status="Dilewati",
                notes=["Folder tidak berisi file PDF."],
            )
        ]

    scan_results = _scan_pdf_seps_parallel(pdf_paths, progress_callback=progress_callback)
    reserved_targets: set[Path] = set()
    results: list[RenameResult] = []
    total = len(pdf_paths)
    for completed, path in enumerate(pdf_paths, start=1):
        if progress_callback is not None:
            progress_callback(completed, total, path.name)
        scan = scan_results.get(path, SepScanResult(path=path, error="PDF belum diperiksa."))
        result = _rename_one_pdf(path, scan, reserved_targets)
        results.append(result)
    return results


def build_rename_summary(results: list[RenameResult]) -> dict[str, int]:
    return {
        "Total PDF": len(results),
        "Berhasil": sum(1 for result in results if result.status == "Berhasil"),
        "Dilewati": sum(1 for result in results if result.status == "Dilewati"),
        "Gagal": sum(1 for result in results if result.status == "Gagal"),
    }


def _scan_pdf_seps_parallel(
    pdf_paths: list[Path],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[Path, SepScanResult]:
    total = len(pdf_paths)
    worker_count = automatic_pdf_worker_count(total)
    if worker_count == 1:
        return {
            path: _scan_pdf_sep(path)
            for path in pdf_paths
        }

    results: dict[Path, SepScanResult] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(_scan_pdf_sep, path): path for path in pdf_paths}
        pending = set(futures.keys())
        completed = 0
        while pending:
            done, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
            for future in done:
                completed += 1
                path = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = SepScanResult(
                        path=path,
                        readable=False,
                        error="Pemeriksaan SEP gagal:\n" + traceback.format_exc(),
                    )
                results[path] = result
                if progress_callback is not None:
                    progress_callback(completed, total, path.name)
    return results


def _scan_pdf_sep(path: Path) -> SepScanResult:
    try:
        import fitz
    except Exception as exc:
        return SepScanResult(path=path, readable=False, error=f"PyMuPDF belum tersedia: {exc}")

    try:
        document = fitz.open(str(path))
    except Exception as exc:
        return SepScanResult(path=path, readable=False, error=f"PDF gagal dibuka: {exc}")

    try:
        for page_index in range(document.page_count):
            page_text = document.load_page(page_index).get_text("text") or ""
            sep_values = extract_sep_values(page_text)
            if sep_values:
                return SepScanResult(path=path, sep=sep_values[0], readable=True)
    except Exception as exc:
        return SepScanResult(path=path, readable=False, error=f"PDF gagal dibaca: {exc}")
    finally:
        document.close()

    return SepScanResult(path=path, readable=True, error="Nomor SEP tidak ditemukan di teks digital PDF.")


def _rename_one_pdf(path: Path, scan: SepScanResult, reserved_targets: set[Path]) -> RenameResult:
    result = RenameResult(
        old_name=path.name,
        old_path=str(path),
        sep_detected=scan.sep,
    )
    if not scan.readable:
        result.status = "Gagal"
        result.notes.append(scan.error or "PDF tidak dapat dibaca.")
        return result
    if not scan.sep:
        result.status = "Dilewati"
        result.notes.append(scan.error or "Nomor SEP tidak ditemukan di teks digital PDF.")
        return result

    expected_name = f"{scan.sep}.pdf"
    if path.name.lower() == expected_name.lower():
        result.new_name = path.name
        result.new_path = str(path)
        result.status = "Dilewati"
        result.notes.append("Nama file sudah sesuai.")
        reserved_targets.add(_normalized_path(path))
        return result

    target = _next_available_target(path.parent, scan.sep, reserved_targets)
    result.new_name = target.name
    result.new_path = str(target)
    try:
        path.rename(target)
    except Exception as exc:
        result.status = "Gagal"
        result.notes.append(f"File gagal di-rename: {exc}")
        return result

    reserved_targets.add(_normalized_path(target))
    result.status = "Berhasil"
    if target.name != expected_name:
        result.notes.append("Nama target konflik, suffix otomatis ditambahkan.")
    return result


def _next_available_target(parent: Path, sep: str, reserved_targets: set[Path]) -> Path:
    index = 1
    while True:
        suffix = "" if index == 1 else f"_{index}"
        target = parent / f"{sep}{suffix}.pdf"
        normalized = _normalized_path(target)
        if normalized not in reserved_targets and not target.exists():
            return target
        index += 1


def _normalized_path(path: Path) -> Path:
    return Path(str(path).lower())


def _unique_non_empty(values: list[object]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = "" if value is None else str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
