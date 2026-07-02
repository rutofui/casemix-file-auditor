from __future__ import annotations

import time
import traceback

import pandas as pd
import streamlit as st

from src.exporter import export_table_to_excel
from src.pdf_renamer import RENAME_RESULT_COLUMNS, build_rename_summary, rename_pdfs_by_sep
from src.ui.layout import format_elapsed, render_panel_header


def run_pdf_rename(*, folder_path: str) -> None:
    if not folder_path.strip():
        st.error("Isi path Folder PDF Lokal terlebih dahulu.")
        return

    started_at = time.perf_counter()
    progress = st.progress(0)
    status = st.empty()

    def update_progress(completed: int, total: int, file_name: str) -> None:
        if total:
            progress.progress(completed / total)
        status.text(
            f"Memproses PDF {completed}/{total}: {file_name} · Durasi: "
            f"{format_elapsed(time.perf_counter() - started_at)}"
        )

    try:
        with st.spinner("Mengubah nama PDF berdasarkan nomor SEP..."):
            results = rename_pdfs_by_sep(
                folder_path,
                progress_callback=update_progress,
            )
    except Exception as exc:
        progress.empty()
        status.empty()
        st.error(f"Rename PDF gagal: {exc}")
        with st.expander("Detail teknis"):
            st.code(traceback.format_exc())
        return

    progress.empty()
    status.empty()
    elapsed = time.perf_counter() - started_at
    result_df = pd.DataFrame([result.to_row() for result in results], columns=RENAME_RESULT_COLUMNS)
    summary = build_rename_summary(results)
    export_bytes = export_table_to_excel(result_df, summary, sheet_name="rename_pdf_sep")

    st.session_state["rename_pdf_df"] = result_df
    st.session_state["rename_pdf_summary"] = summary
    st.session_state["rename_pdf_export_bytes"] = export_bytes
    st.session_state["rename_pdf_duration_sec"] = elapsed
    st.session_state["last_review_kind"] = "rename"
    st.success(f"Rename PDF selesai ({format_elapsed(elapsed)}).")


def render_pdf_rename_tab() -> None:
    render_panel_header(
        "Rename PDF SEP",
        "Ubah nama banyak PDF berdasarkan nomor SEP yang terbaca dari teks digital file.",
        "rename-panel",
    )
    folder_path = st.text_input(
        "Folder PDF Lokal",
        key="rename_pdf_folder",
        placeholder=r"Contoh: D:\Casemix\Berkas Klaim",
    )
    st.caption(
        "File akan di-rename langsung di folder asal. PDF scan tanpa teks digital tidak memakai OCR "
        "dan akan dilewati atau ditandai gagal bila tidak dapat dibaca."
    )
    if st.button(
        "Jalankan Rename PDF",
        type="primary",
        width="stretch",
        key="run_rename_pdf",
    ):
        run_pdf_rename(folder_path=folder_path)
    render_pdf_rename_panel()


def render_pdf_rename_panel() -> None:
    if st.session_state.get("rename_pdf_df") is None:
        return

    duration_sec = st.session_state.get("rename_pdf_duration_sec")
    if duration_sec is not None:
        st.caption(f"Durasi rename terakhir: **{format_elapsed(duration_sec)}**")

    summary = st.session_state.get("rename_pdf_summary") or {}
    summary_items = list(summary.items())
    for start in range(0, len(summary_items), 4):
        metric_cols = st.columns(4)
        for col, (label, value) in zip(metric_cols, summary_items[start : start + 4]):
            col.metric(label, value)

    st.divider()
    st.subheader("Hasil Rename PDF")
    left, right = st.columns([3, 1])
    with left:
        selected_status = st.selectbox(
            "Filter Status",
            ["Semua", "Berhasil", "Dilewati", "Gagal"],
            key="rename_pdf_status_filter",
        )
    result_df = st.session_state.get("rename_pdf_df")
    filtered_df = result_df
    if selected_status != "Semua":
        filtered_df = result_df[result_df["Status"] == selected_status]
    with right:
        st.download_button(
            "Export Excel",
            data=st.session_state.get("rename_pdf_export_bytes") or b"",
            file_name="hasil_rename_pdf_sep.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key="rename_pdf_export",
        )
    st.dataframe(filtered_df, width="stretch", hide_index=True)
