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
from src.eklaim_formatting import format_analysis_frame_for_display, format_summary_label, format_summary_value
from src.ui.layout import format_elapsed, render_panel_header
from src.ui.results import begin_review, finish_review, input_signature, render_result_context, set_current_input


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

    set_current_input("eklaim", input_signature(ri_file, rj_file))

    if st.button(
        "Jalankan Analisis TXT E-Klaim",
        type="primary",
        width="stretch",
        key="run_eklaim_txt_analysis",
    ):
        run_txt_analysis(ri_file=ri_file, rj_file=rj_file)

    render_txt_analysis_results()


def run_txt_analysis(*, ri_file, rj_file) -> None:
    signature = input_signature(ri_file, rj_file)
    begin_review("eklaim")
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
                    source_label=ri_file.name,
                )
                if ri_file is not None
                else None
            )
            rj_result = (
                read_eklaim_txt(
                    rj_file,
                    expected_ptd=PTD_RAWAT_JALAN,
                    source_label=rj_file.name,
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
            analysis.warnings = warnings + analysis.warnings
            export_bytes = export_eklaim_analysis_to_excel(analysis)

        elapsed = time.perf_counter() - started_at
        st.session_state["eklaim_analysis"] = analysis
        st.session_state["eklaim_export_bytes"] = export_bytes
        st.session_state["eklaim_analysis_duration_sec"] = elapsed
        finish_review("eklaim", signature, ", ".join(f.name for f in (ri_file, rj_file) if f is not None))
        st.success(f"Analisis TXT E-Klaim selesai ({format_elapsed(elapsed)}).")
    except Exception as exc:
        st.error(f"Analisis TXT E-Klaim gagal: {exc}")
        with st.expander("Detail teknis"):
            st.code(traceback.format_exc())


def render_txt_analysis_results() -> None:
    analysis = st.session_state.get("eklaim_analysis")
    has_results = analysis is not None

    duration_sec = st.session_state.get("eklaim_analysis_duration_sec")
    if duration_sec is not None:
        st.caption(f"Durasi analisis terakhir: **{format_elapsed(duration_sec)}**")

    if not has_results:
        return
    if not render_result_context("eklaim"):
        return

    st.subheader("Ringkasan")
    _render_summary_metrics(analysis.summary)
    _render_tariff_comparison_summary(analysis.tariff_comparison_df)
    _render_casemix_metrics(analysis.casemix_index)
    st.caption(
        "CMI dihitung dari cost weight iDRG yang tersedia. "
        "Angka ini bukan CMI resmi INA-CBG dan perlu dibaca bersama cakupan datanya."
    )
    st.markdown("**Kualitas data**")
    st.caption("Kualitas data memeriksa seluruh baris masuk; KPI hanya memakai klaim yang lolos karantina.")
    quality_items = list(analysis.data_quality.items())
    for start in range(0, len(quality_items), 4):
        for col, (label, value) in zip(st.columns(4), quality_items[start : start + 4]):
            col.metric(label, format_summary_value(label, value))
    for warning in getattr(analysis, "warnings", []):
        st.warning(warning)

    st.subheader("Kelengkapan dan validitas data")
    _render_section_table("PTD Tidak Valid", analysis.invalid_ptd_df, "ptd_tidak_valid")
    _render_optional_table(analysis, "duplicate_claims_df", "SEP Duplikat", "sep_duplikat")
    _render_optional_table(analysis, "quarantine_df", "Klaim Dikarantina", "klaim_dikarantina")
    _render_section_table("Nilai Numerik Kosong atau Tidak Valid", analysis.invalid_numeric_df, "angka_tidak_valid")
    _render_optional_table(analysis, "validation_df", "Validasi Silang Data", "validasi_nilai")

    with st.expander("Cara membaca persentase dan aturan penapisan"):
        st.markdown(
            "Selisih tarif membandingkan nilai klaim yang tersedia; cakupan baris harus dibaca di tabel rekonsiliasi. "
            "Selisih tarif bukan biaya aktual, margin, ukuran efisiensi, atau mutu klinis. "
            "Jumlah kasus DPJP menunjukkan volume aktivitas, bukan produktivitas tenaga tanpa data FTE/jadwal. "
            "Penapisan LOS/severity hanya penanda telaah, bukan kesimpulan kesalahan klaim. "
            "CMI cost weight iDRG adalah ringkasan berbasis bobot yang tersedia, bukan pembanding CMI resmi INA-CBG."
        )

    st.divider()
    left, right = st.columns([3, 1])
    with left:
        st.caption("Unduh semua tabel hasil analisis dalam satu file Excel.")
    with right:
        st.download_button(
            "Export Excel",
            data=st.session_state.get("eklaim_export_bytes", b""),
            file_name="hasil_analisis_txt_eklaim.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            disabled=not has_results,
            key="eklaim_export_download",
        )

    st.subheader("Rekonsiliasi tarif")
    _render_optional_table(analysis, "tariff_comparison_df", "Rincian Perbandingan Tarif dan Cakupan", "perbandingan_tarif")
    _render_optional_table(analysis, "components_df", "Rincian Komponen Tarif", "komponen_tarif")
    _render_optional_table(analysis, "tariff_components_df", "Komponen Tambahan Tarif", "topup_tarif")
    _render_section_table(
        "Tarif Klaim Lebih Besar dari Tarif RS (per basis tarif)",
        analysis.grouper_gt_rs_df,
        "tarif_klaim_lebih_besar",
    )
    _render_section_table(
        "Selisih Tarif RS - Tarif Klaim > 30% (per basis tarif)",
        analysis.selisih_gt_30pct_df,
        "selisih_lebih_30pct",
    )

    st.subheader("Aktivitas dan profil layanan")
    _render_optional_table(analysis, "activity_df", "Aktivitas dan Penggunaan Sumber Daya", "aktivitas")
    _render_section_table(
        "Volume dan Tarif per DPJP (Rawat Inap)",
        analysis.dpjp_ri_df,
        "selisih_dpjp_ri",
    )
    _render_section_table(
        "Volume dan Tarif per DPJP (Rawat Jalan)",
        analysis.dpjp_rj_df,
        "selisih_dpjp_rj",
    )
    st.caption("Jumlah kasus per DPJP adalah volume aktivitas; data FTE dan jadwal layanan diperlukan untuk mengukur produktivitas.")
    _render_optional_table(analysis, "service_days_df", "Kunjungan per Tanggal Layanan", "kunjungan_harian")
    _render_optional_table(analysis, "outpatient_visits_df", "Frekuensi Kunjungan Rawat Jalan", "frekuensi_kunjungan")
    _render_optional_table(analysis, "discharge_status_df", "Status Pulang (Kode Sumber)", "status_pulang")

    st.subheader("Casemix, LOS, dan coding")
    _render_optional_table(analysis, "los_profile_df", "Profil LOS", "profil_los")
    _render_optional_table(analysis, "casemix_profile_df", "Profil Casemix per Kelompok", "profil_casemix")
    _render_optional_table(analysis, "period_activity_df", "Aktivitas per Bulan", "aktivitas_periode")
    _render_section_table("Kelengkapan Kode Diagnosis dan Tindakan", analysis.completeness_df, "kelengkapan_dx_px")
    _render_section_table("Severity > 1 dan LOS < 5 (Rawat Inap)", analysis.severity_high_los_low_df, "severity_tinggi_los_rendah")
    _render_section_table("Severity 1 dan LOS > 5 (Rawat Inap)", analysis.severity_low_los_high_df, "severity_rendah_los_tinggi")
    _render_section_table("Rawat Intensif", analysis.intensive_care_df, "rawat_intensif")
    _render_section_table("Top 30 ICD-10 (Rawat Inap)", analysis.top_icd10_ri_df, "top30_icd10_ri")
    _render_section_table("Top 30 ICD-10 (Rawat Jalan)", analysis.top_icd10_rj_df, "top30_icd10_rj")
    _render_section_table("Top 30 ICD-9-CM (Rawat Inap)", analysis.top_icd9_ri_df, "top30_icd9_ri")
    _render_section_table("Top 30 ICD-9-CM (Rawat Jalan)", analysis.top_icd9_rj_df, "top30_icd9_rj")

    _render_optional_table(analysis, "metadata_df", "Metadata Analisis", "metadata_analisis")
    _render_optional_table(analysis, "methodology_df", "Definisi dan Metodologi", "metodologi_analisis")


def _render_summary_metrics(summary: dict[str, object]) -> None:
    items = [(key, value) for key, value in summary.items() if key.startswith("Total Klaim ")]
    for start in range(0, len(items), 3):
        cols = st.columns(3)
        for col, (label, value) in zip(cols, items[start : start + 3]):
            display_label = format_summary_label(label)
            col.metric(display_label, _format_metric_value(value, label))


def _render_tariff_comparison_summary(frame: pd.DataFrame) -> None:
    if frame is None or frame.empty:
        return
    columns = [
        "Jenis Rawat", "Jumlah Klaim",
        "Total Tarif RS", "Cakupan Tarif RS (%)",
        "Total Tarif INA-CBG", "Cakupan Tarif INA-CBG (%)",
        "Total Tarif iDRG", "Cakupan Tarif iDRG (%)",
        "Selisih RS - INA-CBG", "Selisih RS - iDRG",
        "Perubahan iDRG - INA-CBG", "Status Tarif",
    ]
    columns = [column for column in columns if column in frame]
    st.subheader("Ringkasan tarif dan cakupan")
    st.caption("Jumlah tarif adalah nilai valid yang terbaca; cakupan di bawah 100% berarti subtotal parsial.")
    st.dataframe(
        format_analysis_frame_for_display(frame[columns]),
        width="stretch",
        hide_index=True,
        key="perbandingan_tarif_ringkas_table",
    )


def _render_casemix_metrics(casemix_index: dict[str, object]) -> None:
    st.markdown("**Rata-rata cost weight iDRG (indikatif)**")
    cols = st.columns(2)
    for col, group_name in zip(cols, ["Rawat Inap", "Rawat Jalan"]):
        metrics = casemix_index.get(group_name, {})
        cmi = metrics.get("Casemix Index")
        total = metrics.get("Jumlah Klaim", metrics.get("Total Klaim", 0))
        available = metrics.get("Klaim dengan Cost Weight", metrics.get("Jumlah Klaim", 0))
        missing = metrics.get("Tanpa Cost Weight", max(0, total - available))
        coverage = metrics.get("Cakupan Cost Weight (%)")
        total_cw_mean = metrics.get("Rata-rata total_cost_weight")
        total_cw_coverage = metrics.get("Cakupan total_cost_weight (%)")
        weight_version = metrics.get("Versi Bobot iDRG")
        status = metrics.get("Status CMI")
        col.metric(f"Rata-rata cost_weight iDRG {group_name}", _format_weight(cmi))
        coverage_text = f" · cakupan {format_summary_value('Cakupan Cost Weight (%)', coverage)}" if coverage is not None else ""
        version_text = f" · versi bobot {weight_version}" if weight_version else ""
        status_text = f" · status: {status}" if status else ""
        col.caption(
            f"{available} dari {total} klaim memiliki cost weight · {missing} tanpa cost weight"
            f"{coverage_text}{version_text}{status_text}\n"
            f"Rata-rata total_cost_weight: {_format_weight(total_cw_mean)}"
            f" · cakupan {format_summary_value('Cakupan total_cost_weight (%)', total_cw_coverage)}"
        )


def _render_section_table(title: str, frame: pd.DataFrame, key_prefix: str) -> None:
    count = 0 if frame is None else len(frame)
    with st.expander(f"{title} ({count})"):
        if frame is None or frame.empty:
            st.info("Tidak ada data untuk bagian ini.")
            return
        st.dataframe(
            format_analysis_frame_for_display(frame),
            width="stretch",
            hide_index=True,
            key=f"{key_prefix}_table",
        )


def _render_optional_table(analysis, attribute: str, title: str, key_prefix: str) -> None:
    frame = getattr(analysis, attribute, None)
    if frame is not None:
        _render_section_table(title, frame, key_prefix)


def _format_metric_value(value: object, label: str = "") -> str:
    if value is None or value == "":
        return "—"
    if label:
        return format_summary_value(label, value)
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    return str(value)


def _format_weight(value: object) -> str:
    if value is None or value == "":
        return "—"
    return f"{float(value):.4f}".replace(".", ",")
