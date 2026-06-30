from __future__ import annotations

import time
import traceback

import streamlit as st

from src.config import FILE_REVIEW_COLUMNS, FILE_REVIEW_ICD_COLUMNS
from src.exporter import export_review_to_excel
from src.matcher import build_file_review
from src.parser_eklaim_txt import build_file_review_claims, read_eklaim_txt
from src.parser_excel import read_claims_excel
from src.ui.file_inputs import build_file_review_entries, show_file_input_warnings
from src.ui.layout import format_elapsed, render_panel_header
from src.ui.pdf_jobs import check_all_first_page_codes
from src.ui.results import empty_file_icd_summary, empty_file_summary, render_review_panel

REFERENCE_MODE_EXCEL = "Excel"
REFERENCE_MODE_TXT = "TXT E-Klaim"
SOURCE_MODE_FOLDER = "Folder Berkas Lokal"


def run_file_review(
    *,
    reference_mode: str,
    excel_file,
    txt_file,
    source_mode: str,
    file_list,
    folder_path: str,
) -> None:
    if reference_mode == REFERENCE_MODE_EXCEL and excel_file is None:
        st.error("Upload Excel daftar klaim terlebih dahulu.")
        return
    if reference_mode == REFERENCE_MODE_TXT and txt_file is None:
        st.error("Upload TXT E-Klaim (format MIX) terlebih dahulu.")
        return
    if source_mode == "list_berkas_klaim.txt" and file_list is None:
        st.error("Upload list_berkas_klaim.txt terlebih dahulu.")
        return
    if source_mode == SOURCE_MODE_FOLDER and not folder_path.strip():
        st.error("Isi path Folder Berkas Lokal terlebih dahulu.")
        return

    try:
        started_at = time.perf_counter()
        duration_status = st.empty()
        duration_status.info(f"Durasi berjalan: {format_elapsed(0)}")
        with st.spinner("Mengecek jumlah berkas..."):
            if reference_mode == REFERENCE_MODE_EXCEL:
                claims_result = read_claims_excel(excel_file)
                claims_df = claims_result.df
                claims_warnings = claims_result.warnings
            else:
                eklaim_result = read_eklaim_txt(
                    txt_file,
                    expected_ptd=None,
                    source_label=getattr(txt_file, "name", "TXT E-Klaim"),
                )
                claims_df = build_file_review_claims(eklaim_result.df)
                claims_warnings = eklaim_result.warnings

            file_entries = build_file_review_entries(
                source_mode=source_mode,
                file_list=file_list,
                folder_path=folder_path,
            )
            show_file_input_warnings(
                claims_warnings,
                source_mode=source_mode,
                file_list=file_list,
                folder_path=folder_path,
                file_entries=file_entries,
            )
            duration_status.info(
                f"Durasi berjalan: {format_elapsed(time.perf_counter() - started_at)}"
            )

            run_icd_check = reference_mode == REFERENCE_MODE_TXT and source_mode == SOURCE_MODE_FOLDER
            icd_results = (
                check_all_first_page_codes(
                    claims_df=claims_df,
                    file_entries=file_entries,
                    started_at=started_at,
                    duration_status=duration_status,
                )
                if run_icd_check
                else None
            )

            review_df, orphan_df, summary = build_file_review(claims_df, file_entries, icd_check_results=icd_results)
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
        st.session_state["file_review_icd_check"] = icd_results is not None
        st.session_state["last_review_kind"] = "file"
        st.success(f"Review jumlah berkas selesai ({format_elapsed(elapsed)}).")
    except Exception as exc:
        st.error(f"Review jumlah berkas gagal: {exc}")
        with st.expander("Detail teknis"):
            st.code(traceback.format_exc())


def render_file_review_tab() -> None:
    render_panel_header(
        "Review Jumlah Berkas",
        "Cocokkan daftar klaim Excel/TXT dengan indeks file PDF dari TXT atau folder lokal.",
        "file-panel",
    )
    file_reference_mode = st.radio(
        "Sumber Acuan Klaim",
        [REFERENCE_MODE_EXCEL, REFERENCE_MODE_TXT],
        horizontal=True,
        key="file_review_reference_mode",
    )
    file_excel = None
    file_txt = None
    if file_reference_mode == REFERENCE_MODE_TXT:
        file_txt = st.file_uploader(
            "TXT E-Klaim (format MIX)",
            type=["txt"],
            key="file_review_txt",
        )
    else:
        file_excel = st.file_uploader(
            "Excel daftar klaim",
            type=["xlsx", "xls"],
            key="file_review_excel",
        )
    file_source_mode = st.radio(
        "Sumber data PDF",
        ["list_berkas_klaim.txt", SOURCE_MODE_FOLDER],
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
    if file_reference_mode == REFERENCE_MODE_TXT and file_source_mode == SOURCE_MODE_FOLDER:
        st.caption(
            "Mode ini juga otomatis memeriksa apakah kode ICD-10 dan ICD-9-CM di TXT "
            "tercantum di halaman pertama PDF yang cocok."
        )
    if st.button(
        "Jalankan Review Jumlah Berkas",
        type="primary",
        width="stretch",
        key="run_file_review",
    ):
        run_file_review(
            reference_mode=file_reference_mode,
            excel_file=file_excel,
            txt_file=file_txt,
            source_mode=file_source_mode,
            file_list=file_list,
            folder_path=file_folder_path,
        )
    render_file_panel()


def render_file_panel() -> None:
    if st.session_state.get("file_review_df") is None:
        return
    icd_check = bool(st.session_state.get("file_review_icd_check", False))
    status_options = ["Semua", "Lengkap", "Kurang PDF", "Salah Folder", "Duplikat", "Perlu Review Manual"]
    if icd_check:
        status_options.append("Kode ICD Tidak Sesuai")
    render_review_panel(
        review_df=st.session_state.get("file_review_df"),
        summary=st.session_state.get("file_summary"),
        orphan_df=st.session_state.get("file_orphan_df"),
        export_bytes=st.session_state.get("file_export_bytes"),
        empty_columns=FILE_REVIEW_ICD_COLUMNS if icd_check else FILE_REVIEW_COLUMNS,
        empty_summary=empty_file_icd_summary() if icd_check else empty_file_summary(),
        status_options=status_options,
        export_file_name="hasil_review_jumlah_berkas.xlsx",
        orphan_title="PDF di folder/list tetapi tidak ada di Excel",
        widget_prefix="file_review",
        section_title="Hasil Review Jumlah Berkas",
        duration_sec=st.session_state.get("file_review_duration_sec"),
    )
