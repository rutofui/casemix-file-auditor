from __future__ import annotations

import time
import traceback

import pandas as pd
import streamlit as st

from src.eklaim_analyzer import build_eklaim_analysis
from src.eklaim_exporter import export_eklaim_analysis_to_excel
from src.parser_eklaim_txt import (
    PTD_RAWAT_INAP,
    PTD_RAWAT_JALAN,
    combine_eklaim_frames,
    read_eklaim_txt,
)
from src.ui.layout import format_elapsed, render_panel_header


def render_txt_analysis_tab() -> None:
    render_panel_header(
        "Analisis TXT E-Klaim",
        "Upload file MIX e-Klaim Rawat Inap dan/atau Rawat Jalan untuk audit tarif, coding, dan casemix index.",
        "txt-panel",
    )

    left, right = st.columns(2, gap="large")
    with left:
        ri_file = st.file_uploader(
            "TXT Rawat Inap",
            type=["txt"],
            key="eklaim_txt_ri",
        )
    with right:
        rj_file = st.file_uploader(
            "TXT Rawat Jalan",
            type=["txt"],
            key="eklaim_txt_rj",
        )

    if st.button(
        "Jalankan Analisis TXT E-Klaim",
        type="primary",
        width="stretch",
        key="run_eklaim_txt_analysis",
    ):
        run_txt_analysis(ri_file=ri_file, rj_file=rj_file)

    render_txt_analysis_results()


def run_txt_analysis(*, ri_file, rj_file) -> None:
    if ri_file is None and rj_file is None:
        st.error("Upload minimal satu file TXT Rawat Inap atau Rawat Jalan.")
        return

    try:
        started_at = time.perf_counter()
        with st.spinner("Menganalisis file TXT e-Klaim..."):
            ri_result = (
                read_eklaim_txt(
                    ri_file,
                    expected_ptd=PTD_RAWAT_INAP,
                    source_label="Rawat Inap",
                )
                if ri_file is not None
                else None
            )
            rj_result = (
                read_eklaim_txt(
                    rj_file,
                    expected_ptd=PTD_RAWAT_JALAN,
                    source_label="Rawat Jalan",
                )
                if rj_file is not None
                else None
            )
            ri_df, rj_df, warnings = combine_eklaim_frames(ri_result, rj_result)
            if ri_df.empty and rj_df.empty:
                st.error("Tidak ada data klaim yang bisa dianalisis dari file TXT.")
                return

            for warning in warnings:
                st.warning(warning)

            analysis = build_eklaim_analysis(ri_df, rj_df)
            export_bytes = export_eklaim_analysis_to_excel(analysis)

        elapsed = time.perf_counter() - started_at
        st.session_state["eklaim_analysis"] = analysis
        st.session_state["eklaim_export_bytes"] = export_bytes
        st.session_state["eklaim_analysis_duration_sec"] = elapsed
        st.success(f"Analisis TXT E-Klaim selesai ({format_elapsed(elapsed)}).")
    except Exception as exc:
        st.error(f"Analisis TXT E-Klaim gagal: {exc}")
        with st.expander("Detail teknis"):
            st.code(traceback.format_exc())


def render_txt_analysis_results() -> None:
    analysis = st.session_state.get("eklaim_analysis")
    if analysis is None:
        return

    duration_sec = st.session_state.get("eklaim_analysis_duration_sec")
    if duration_sec is not None:
        st.caption(f"Durasi analisis terakhir: **{format_elapsed(duration_sec)}**")

    st.subheader("Ringkasan")
    _render_summary_metrics(analysis.summary)
    _render_casemix_metrics(analysis.casemix_index)

    st.divider()
    right = st.columns([3, 1])[1]
    with right:
        st.download_button(
            "Export Excel",
            data=st.session_state.get("eklaim_export_bytes", b""),
            file_name="hasil_analisis_txt_eklaim.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key="eklaim_export_download",
        )

    _render_section_table(
        "Kelengkapan Kode Diagnosis dan Tindakan",
        analysis.completeness_df,
        "kelengkapan_dx_px",
    )
    _render_section_table(
        "Severity > 1 dan LOS < 5 (Rawat Inap)",
        analysis.severity_high_los_low_df,
        "severity_tinggi_los_rendah",
    )
    _render_section_table(
        "Severity 1 dan LOS > 5 (Rawat Inap)",
        analysis.severity_low_los_high_df,
        "severity_rendah_los_tinggi",
    )
    _render_section_table(
        "Pasien Rawat Intensif",
        analysis.intensive_care_df,
        "rawat_intensif",
    )
    _render_section_table(
        "Total Tarif Grouper > Tarif RS",
        analysis.grouper_gt_rs_df,
        "tarif_grouper_lebih_besar",
    )
    _render_section_table(
        "Selisih Tarif RS - Grouper > 30%",
        analysis.selisih_gt_30pct_df,
        "selisih_lebih_30pct",
    )
    _render_section_table(
        "Selisih per DPJP (Rawat Inap)",
        analysis.dpjp_ri_df,
        "selisih_dpjp_ri",
    )
    _render_section_table(
        "Selisih per DPJP (Rawat Jalan)",
        analysis.dpjp_rj_df,
        "selisih_dpjp_rj",
    )
    _render_section_table("Top 30 ICD-10", analysis.top_icd10_df, "top30_icd10")
    _render_section_table("Top 30 ICD-9-CM", analysis.top_icd9_df, "top30_icd9")


def _render_summary_metrics(summary: dict[str, object]) -> None:
    items = list(summary.items())
    for start in range(0, len(items), 3):
        cols = st.columns(3)
        for col, (label, value) in zip(cols, items[start : start + 3]):
            col.metric(label, _format_metric_value(value))


def _render_casemix_metrics(casemix_index: dict[str, object]) -> None:
    st.markdown("**Casemix Index (berbasis iDRG cost weight)**")
    cols = st.columns(2)
    for col, group_name in zip(cols, ["Rawat Inap", "Rawat Jalan"]):
        metrics = casemix_index.get(group_name, {})
        cmi = metrics.get("Casemix Index", 0)
        claim_count = metrics.get("Jumlah Klaim", 0)
        missing = metrics.get("Tanpa Cost Weight", 0)
        col.metric(f"CMI {group_name}", cmi)
        col.caption(f"{claim_count} klaim · {missing} tanpa cost weight")


def _render_section_table(title: str, frame: pd.DataFrame, key_prefix: str) -> None:
    count = 0 if frame is None else len(frame)
    with st.expander(f"{title} ({count})"):
        if frame is None or frame.empty:
            st.info("Tidak ada data untuk bagian ini.")
            return
        st.dataframe(frame, width="stretch", hide_index=True, key=f"{key_prefix}_table")


def _format_metric_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", ".")
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    return str(value)
