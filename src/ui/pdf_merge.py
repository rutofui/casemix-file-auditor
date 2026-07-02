from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from src.exporter import export_table_to_excel
from src.pdf_merger import (
    MERGE_RESULT_COLUMNS,
    build_merge_summary,
    merge_pdf_folders,
)
from src.ui.layout import format_elapsed, render_panel_header


def run_pdf_merge(
    *,
    source_a: str,
    source_b: str,
    output_folder: str,
    overwrite: bool,
) -> None:
    if not source_a.strip() or not source_b.strip() or not output_folder.strip():
        st.error("Folder Sumber A, Folder Sumber B, dan Folder Output wajib diisi.")
        return

    started_at = time.perf_counter()
    progress = st.progress(0)
    status = st.empty()

    def update_progress(completed: int, total: int, file_name: str) -> None:
        if total:
            progress.progress(completed / total)
        status.text(
            f"Merge PDF {completed}/{total}: {file_name} · Durasi: "
            f"{format_elapsed(time.perf_counter() - started_at)}"
        )

    with st.spinner("Menggabungkan PDF..."):
        results = merge_pdf_folders(
            source_a,
            source_b,
            output_folder,
            overwrite=overwrite,
            progress_callback=update_progress,
        )

    progress.empty()
    status.empty()
    elapsed = time.perf_counter() - started_at
    rows = [result.to_row() for result in results]
    result_df = pd.DataFrame(rows, columns=MERGE_RESULT_COLUMNS)
    summary = build_merge_summary(results)
    export_bytes = export_table_to_excel(result_df, summary, sheet_name="merge_pdf")

    st.session_state["merge_pdf_df"] = result_df
    st.session_state["merge_pdf_summary"] = summary
    st.session_state["merge_pdf_export_bytes"] = export_bytes
    st.session_state["merge_pdf_duration_sec"] = elapsed
    st.session_state["last_review_kind"] = "merge"
    st.success(f"Merge PDF selesai ({format_elapsed(elapsed)}).")


def render_pdf_merge_tab() -> None:
    render_panel_header(
        "Merge PDF Berkas",
        "Gabungkan PDF bernama sama dari dua folder tanpa mengubah urutan halaman.",
        "merge-panel",
    )
    source_a = st.text_input(
        "Folder Sumber A",
        key="merge_pdf_source_a",
        placeholder=r"Contoh: D:\Casemix\SumberA",
    )
    source_b = st.text_input(
        "Folder Sumber B",
        key="merge_pdf_source_b",
        placeholder=r"Contoh: D:\Casemix\SumberB",
    )
    output_folder = st.text_input(
        "Folder Output",
        key="merge_pdf_output_folder",
        placeholder=r"Contoh: D:\Casemix\Output Merge",
    )
    overwrite = st.checkbox(
        "Timpa file output jika sudah ada",
        value=False,
        key="merge_pdf_overwrite",
    )
    if st.button(
        "Jalankan Merge PDF",
        type="primary",
        width="stretch",
        key="run_merge_pdf",
    ):
        run_pdf_merge(
            source_a=source_a,
            source_b=source_b,
            output_folder=output_folder,
            overwrite=overwrite,
        )
    render_pdf_merge_panel()


def render_pdf_merge_panel() -> None:
    if st.session_state.get("merge_pdf_df") is None:
        return

    duration_sec = st.session_state.get("merge_pdf_duration_sec")
    if duration_sec is not None:
        st.caption(f"Durasi merge terakhir: **{format_elapsed(duration_sec)}**")

    summary = st.session_state.get("merge_pdf_summary") or {}
    summary_items = list(summary.items())
    for start in range(0, len(summary_items), 4):
        metric_cols = st.columns(4)
        for col, (label, value) in zip(metric_cols, summary_items[start : start + 4]):
            col.metric(label, value)

    st.divider()
    st.subheader("Hasil Merge PDF")
    left, right = st.columns([3, 1])
    with left:
        selected_status = st.selectbox(
            "Filter Status",
            ["Semua", "Berhasil", "Dilewati", "Gagal"],
            key="merge_pdf_status_filter",
        )
    result_df = st.session_state.get("merge_pdf_df")
    filtered_df = result_df
    if selected_status != "Semua":
        filtered_df = result_df[result_df["Status"] == selected_status]
    with right:
        st.download_button(
            "Export Excel",
            data=st.session_state.get("merge_pdf_export_bytes") or b"",
            file_name="hasil_merge_pdf.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key="merge_pdf_export",
        )
    st.dataframe(filtered_df, width="stretch", hide_index=True)
