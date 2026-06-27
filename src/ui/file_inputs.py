from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.parser_file_list import (
    build_file_entry,
    empty_file_entries,
    parse_file_list_text,
    scan_pdf_folder,
)


def show_file_input_warnings(
    excel_warnings: list[str],
    *,
    source_mode: str,
    file_list,
    folder_path: str,
    file_entries: pd.DataFrame,
) -> None:
    for warning in excel_warnings:
        st.warning(warning)
    if source_mode == "list_berkas_klaim.txt" and file_list is not None and file_entries.empty:
        st.warning("list_berkas_klaim.txt tidak menghasilkan data PDF.")
    if source_mode == "Folder Berkas Lokal" and folder_path.strip() and file_entries.empty:
        st.warning("Folder Berkas Lokal tidak menghasilkan data PDF.")


def build_file_review_entries(
    *,
    source_mode: str,
    file_list,
    folder_path: str,
) -> pd.DataFrame:
    if source_mode == "Folder Berkas Lokal":
        return scan_folder_entries(
            folder_path=folder_path,
            is_index_source=True,
        )
    return parse_uploaded_file_list(file_list)


def parse_uploaded_file_list(file_list) -> pd.DataFrame:
    if file_list is None:
        return empty_file_entries()
    raw_text = file_list.getvalue().decode("utf-8", errors="ignore")
    result = parse_file_list_text(raw_text, source_name=file_list.name)
    for warning in result.warnings:
        st.warning(warning)
    return result.df


def save_uploaded_pdfs(uploaded_pdfs, *, temp_dir: str, is_index_source: bool) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    temp_root = Path(temp_dir)
    for index, uploaded_pdf in enumerate(uploaded_pdfs):
        display_path = uploaded_pdf.name
        safe_name = Path(display_path.replace("\\", "/")).name or f"uploaded_{index}.pdf"
        local_path = temp_root / f"{index:04d}_{safe_name}"
        local_path.write_bytes(uploaded_pdf.getvalue())
        rows.append(
            build_file_entry(
                display_path,
                local_path=str(local_path),
                source="upload",
                is_index_source=is_index_source,
                is_content_source=True,
                note="PDF upload.",
            )
        )
    if not rows:
        return empty_file_entries()
    return pd.DataFrame(rows)


def scan_folder_entries(folder_path: str, *, is_index_source: bool) -> pd.DataFrame:
    result = scan_pdf_folder(
        folder_path.strip(),
        source_name="folder",
        is_index_source=is_index_source,
    )
    for warning in result.warnings:
        st.warning(warning)
    return result.df
