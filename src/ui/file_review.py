from __future__ import annotations

import time
import traceback

import streamlit as st

from src.config import FILE_REVIEW_COLUMNS
from src.exporter import export_review_to_excel
from src.matcher import build_file_review
from src.parser_excel import read_claims_excel
from src.ui.file_inputs import build_file_review_entries, show_file_input_warnings
from src.ui.layout import format_elapsed, render_panel_header
from src.ui.results import empty_file_summary, render_review_panel


def run_file_review(
    *,
    excel_file,
    source_mode: str,
    file_list,
    folder_path: str,
) -> None:
    if excel_file is None:
        st.error("Upload Excel daftar klaim terlebih dahulu.")
        return
    if source_mode == "list_berkas_klaim.txt" and file_list is None:
        st.error("Upload list_berkas_klaim.txt terlebih dahulu.")
        return
    if source_mode == "Folder Berkas Lokal" and not folder_path.strip():
        st.error("Isi path Folder Berkas Lokal terlebih dahulu.")
        return

    try:
        started_at = time.perf_counter()
        duration_status = st.empty()
        duration_status.info(f"Durasi berjalan: {format_elapsed(0)}")
        with st.spinner("Mengecek jumlah berkas..."):
            excel_result = read_claims_excel(excel_file)
            file_entries = build_file_review_entries(
                source_mode=source_mode,
                file_list=file_list,
                folder_path=folder_path,
            )
            show_file_input_warnings(
                excel_result.warnings,
                source_mode=source_mode,
                file_list=file_list,
                folder_path=folder_path,
                file_entries=file_entries,
            )
            duration_status.info(
                f"Durasi berjalan: {format_elapsed(time.perf_counter() - started_at)}"
            )
            review_df, orphan_df, summary = build_file_review(excel_result.df, file_entries)
            export_bytes = export_review_to_excel(
                review_df,
                orphan_df,
                summary,
                review_sheet_name="review_jumlah_berkas",
            )

        elapsed = time.perf_counter() - started_at
        duration_status.empty()
        st.session_state["file_review_df"] = review_df
        st.session_state["file_orphan_df"] = orphan_df
        st.session_state["file_summary"] = summary
        st.session_state["file_export_bytes"] = export_bytes
        st.session_state["file_review_duration_sec"] = elapsed
        st.session_state["last_review_kind"] = "file"
        st.success(f"Review jumlah berkas selesai ({format_elapsed(elapsed)}).")
    except Exception as exc:
        st.error(f"Review jumlah berkas gagal: {exc}")
        with st.expander("Detail teknis"):
            st.code(traceback.format_exc())


def render_file_review_tab() -> None:
    render_panel_header(
        "Review Jumlah Berkas",
        "Cocokkan daftar klaim Excel dengan indeks file PDF dari TXT atau folder lokal.",
        "file-panel",
    )
    file_excel = st.file_uploader(
        "Excel daftar klaim",
        type=["xlsx", "xls"],
        key="file_review_excel",
    )
    file_source_mode = st.radio(
        "Sumber data PDF",
        ["list_berkas_klaim.txt", "Folder Berkas Lokal"],
        horizontal=True,
        key="file_review_source_mode",
    )
    file_list = None
    file_folder_path = ""
    if file_source_mode == "list_berkas_klaim.txt":
        st.caption("Command Prompt untuk membuat list berkas klaim:")
        st.code("dir /s /b > list_berkas_klaim.txt", language="bat")
        file_list = st.file_uploader(
            "list_berkas_klaim.txt",
            type=["txt"],
            key="file_review_list",
        )
    else:
        file_folder_path = st.text_input(
            "Folder Berkas Lokal",
            key="file_review_folder",
            placeholder=r"Contoh: D:\Casemix\Pending\2026",
        )
    if st.button(
        "Jalankan Review Jumlah Berkas",
        type="primary",
        width="stretch",
        key="run_file_review",
    ):
        run_file_review(
            excel_file=file_excel,
            source_mode=file_source_mode,
            file_list=file_list,
            folder_path=file_folder_path,
        )
    render_file_panel()


def render_file_panel() -> None:
    if st.session_state.get("file_review_df") is None:
        return
    st.subheader("Hasil Review Jumlah Berkas")
    render_review_panel(
        review_df=st.session_state.get("file_review_df"),
        summary=st.session_state.get("file_summary"),
        orphan_df=st.session_state.get("file_orphan_df"),
        export_bytes=st.session_state.get("file_export_bytes"),
        empty_columns=FILE_REVIEW_COLUMNS,
        empty_summary=empty_file_summary(),
        status_options=["Semua", "Lengkap", "Kurang PDF", "Salah Folder", "Duplikat", "Perlu Review Manual"],
        export_file_name="hasil_review_jumlah_berkas.xlsx",
        orphan_title="PDF di folder/list tetapi tidak ada di Excel",
        widget_prefix="file_review",
        duration_sec=st.session_state.get("file_review_duration_sec"),
    )
