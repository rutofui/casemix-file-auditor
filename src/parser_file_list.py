from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import re

import pandas as pd

from .config import extract_sep_values, is_valid_sep


FILE_ENTRY_COLUMNS = [
    "source_id",
    "display_path",
    "local_path",
    "file_name",
    "no_sep",
    "sep_valid",
    "tanggal_folder",
    "tanggal_folder_raw",
    "source",
    "is_index_source",
    "is_content_source",
    "note",
]


@dataclass
class FileListParseResult:
    df: pd.DataFrame
    warnings: list[str]
    total_lines: int = 0
    pdf_lines: int = 0


def empty_file_entries() -> pd.DataFrame:
    return pd.DataFrame(columns=FILE_ENTRY_COLUMNS)


def _clean_path_line(line: object) -> str:
    text = "" if line is None else str(line)
    return text.strip().strip('"').strip("'").strip()


def _split_any_path(path_text: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", path_text) if part]


def _file_name_from_path(path_text: str) -> str:
    parts = _split_any_path(path_text)
    return parts[-1] if parts else path_text


def _date_folder_from_path(path_text: str) -> tuple[str, str]:
    parts = _split_any_path(path_text)
    if len(parts) < 2:
        return "", ""
    raw = parts[-2].strip()
    if re.fullmatch(r"\d{1,2}", raw):
        day = int(raw)
        if 1 <= day <= 31:
            return f"{day:02d}", raw
    return "", raw


def _make_source_id(source: str, display_path: str, local_path: str | None) -> str:
    payload = f"{source}|{display_path}|{local_path or ''}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload).hexdigest()[:16]


def build_file_entry(
    display_path: str,
    *,
    local_path: str | None = None,
    source: str = "list",
    is_index_source: bool = True,
    is_content_source: bool = False,
    note: str = "",
) -> dict[str, object]:
    display_path = _clean_path_line(display_path)
    file_name = _file_name_from_path(display_path)
    sep_values = extract_sep_values(file_name)
    if not sep_values:
        sep_values = extract_sep_values(display_path)
    no_sep = sep_values[0] if sep_values else ""
    tanggal_folder, tanggal_folder_raw = _date_folder_from_path(display_path)

    return {
        "source_id": _make_source_id(source, display_path, local_path),
        "display_path": display_path,
        "local_path": local_path or "",
        "file_name": file_name,
        "no_sep": no_sep,
        "sep_valid": is_valid_sep(no_sep),
        "tanggal_folder": tanggal_folder,
        "tanggal_folder_raw": tanggal_folder_raw,
        "source": source,
        "is_index_source": bool(is_index_source),
        "is_content_source": bool(is_content_source),
        "note": note,
    }


def parse_file_list_text(text: str, source_name: str = "list_berkas_klaim.txt") -> FileListParseResult:
    warnings: list[str] = []
    rows: list[dict[str, object]] = []
    lines = text.splitlines()
    pdf_lines = 0

    for line in lines:
        clean = _clean_path_line(line)
        if not clean:
            continue
        if not clean.lower().endswith(".pdf"):
            continue
        pdf_lines += 1
        local_path = clean if os.path.exists(clean) else ""
        rows.append(
            build_file_entry(
                clean,
                local_path=local_path,
                source=source_name,
                is_index_source=True,
                is_content_source=bool(local_path),
                note="" if local_path else "Path dari list tidak dapat diakses langsung.",
            )
        )

    df = pd.DataFrame(rows, columns=FILE_ENTRY_COLUMNS) if rows else empty_file_entries()
    df = drop_exact_duplicate_paths(df)

    if not pdf_lines:
        warnings.append("Tidak ada baris file PDF yang terdeteksi di list_berkas_klaim.txt.")
    missing_sep = int((df["no_sep"] == "").sum()) if not df.empty else 0
    if missing_sep:
        warnings.append(f"{missing_sep} file PDF tidak memiliki nomor SEP valid pada nama/path.")

    return FileListParseResult(df=df, warnings=warnings, total_lines=len(lines), pdf_lines=pdf_lines)


def scan_pdf_folder(
    folder_path: str,
    *,
    source_name: str = "folder",
    is_index_source: bool = True,
) -> FileListParseResult:
    warnings: list[str] = []
    folder = Path(folder_path).expanduser()
    if not folder_path.strip():
        return FileListParseResult(df=empty_file_entries(), warnings=warnings)
    if not folder.exists():
        warnings.append(f"Folder PDF tidak ditemukan: {folder}")
        return FileListParseResult(df=empty_file_entries(), warnings=warnings)
    if not folder.is_dir():
        warnings.append(f"Path PDF bukan folder: {folder}")
        return FileListParseResult(df=empty_file_entries(), warnings=warnings)

    rows: list[dict[str, object]] = []
    try:
        for pdf_path in folder.rglob("*.pdf"):
            rows.append(
                build_file_entry(
                    str(pdf_path),
                    local_path=str(pdf_path),
                    source=source_name,
                    is_index_source=is_index_source,
                    is_content_source=True,
                )
            )
    except Exception as exc:
        warnings.append(f"Folder PDF gagal dibaca: {exc}")

    df = pd.DataFrame(rows, columns=FILE_ENTRY_COLUMNS) if rows else empty_file_entries()
    df = drop_exact_duplicate_paths(df)
    return FileListParseResult(df=df, warnings=warnings, pdf_lines=len(df))


def combine_file_entries(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable_frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not usable_frames:
        return empty_file_entries()
    combined = pd.concat(usable_frames, ignore_index=True)
    return drop_exact_duplicate_paths(combined)


def drop_exact_duplicate_paths(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return empty_file_entries()
    deduped = df.drop_duplicates(subset=["source", "display_path", "local_path"]).copy()
    return deduped.reset_index(drop=True)

