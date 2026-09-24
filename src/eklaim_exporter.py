from __future__ import annotations

from io import BytesIO

import pandas as pd

from src.eklaim_analyzer import EklaimAnalysisResult
from src.eklaim_formatting import (
    PERCENTAGE_COLUMNS,
    format_summary_label,
    normalize_analysis_frame,
    tariff_excel_format,
)
from src.exporter import format_worksheet


def export_eklaim_analysis_to_excel(result: EklaimAnalysisResult) -> bytes:
    output = BytesIO()
    summary_rows = _summary_rows(result)
    summary_df = pd.DataFrame(summary_rows)

    cmi_rows = []
    for group_name, metrics in result.casemix_index.items():
        for metric_name, metric_value in metrics.items():
            cmi_rows.append(
                {
                    "Kelompok": group_name,
                    "Metrik": metric_name,
                    "Nilai": metric_value,
                }
            )
    cmi_df = pd.DataFrame(cmi_rows)

    sheets: list[tuple[str, pd.DataFrame]] = [
        ("ringkasan", summary_df),
        ("casemix_index", cmi_df),
        ("kualitas_data", pd.DataFrame([{"Metrik": k, "Nilai": v} for k, v in result.data_quality.items()])),
        ("metadata", _result_frame(result, "metadata_df")),
        ("metodologi", _result_frame(result, "methodology_df")),
        ("validasi_data", _result_frame(result, "validation_df", result.invalid_numeric_df)),
        ("klaim_dikarantina", _result_frame(result, "quarantine_df")),
        ("sep_duplikat", _result_frame(result, "duplicate_claims_df")),
        ("ptd_tidak_valid", result.invalid_ptd_df),
        ("angka_tidak_valid", result.invalid_numeric_df),
        ("peringatan", pd.DataFrame({"Peringatan": result.warnings})),
        ("rekonsiliasi_tarif", _result_frame(result, "tariff_comparison_df")),
        ("komponen_tarif", _result_frame(result, "components_df")),
        ("topup_tarif", _result_frame(result, "tariff_components_df")),
        ("aktivitas", _result_frame(result, "activity_df")),
        ("profil_los", _result_frame(result, "los_profile_df")),
        ("profil_casemix", _result_frame(result, "casemix_profile_df")),
        ("aktivitas_bulanan", _result_frame(result, "period_activity_df")),
        ("kunjungan_berulang", _result_frame(result, "outpatient_visits_df")),
        ("aktivitas_harian", _result_frame(result, "service_days_df")),
        ("status_pulang", _result_frame(result, "discharge_status_df")),
        ("kelengkapan_dx_px", result.completeness_df),
        ("severity_tinggi_los_rendah", result.severity_high_los_low_df),
        ("severity_rendah_los_tinggi", result.severity_low_los_high_df),
        ("rawat_intensif", result.intensive_care_df),
        ("tarif_grouper_lebih_besar", result.grouper_gt_rs_df),
        ("selisih_lebih_30pct", result.selisih_gt_30pct_df),
        ("selisih_dpjp_ri", normalize_analysis_frame(result.dpjp_ri_df)),
        ("selisih_dpjp_rj", normalize_analysis_frame(result.dpjp_rj_df)),
        ("top30_icd10_ri", result.top_icd10_ri_df),
        ("top30_icd10_rj", result.top_icd10_rj_df),
        ("top30_icd9_ri", result.top_icd9_ri_df),
        ("top30_icd9_rj", result.top_icd9_rj_df),
    ]

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in sheets:
            safe_name = sheet_name[:31]
            (frame if frame is not None else pd.DataFrame()).to_excel(writer, sheet_name=safe_name, index=False)

        for worksheet in writer.book.worksheets:
            format_worksheet(worksheet)
            metric_col = next(
                (column.column for column in worksheet[1] if column.value == "Metrik"),
                1,
            )
            for header in worksheet[1]:
                for row in worksheet.iter_rows(min_row=2, min_col=header.column, max_col=header.column):
                    cell = row[0]
                    metric = str(worksheet.cell(cell.row, metric_col).value) if header.value == "Nilai" else ""
                    percentage = header.value in PERCENTAGE_COLUMNS or str(header.value).endswith("(%)") or "(%)" in metric
                    currency = tariff_excel_format(str(header.value)) or (
                        tariff_excel_format("TOTAL_TARIF")
                        if header.value == "Nilai" and worksheet.title == "ringkasan"
                        and ("Tarif" in metric or "Grouper" in metric) else None
                    )
                    if percentage:
                        if isinstance(cell.value, (int, float)):
                            cell.value /= 100
                        cell.number_format = "0.00%"
                    elif currency:
                        cell.number_format = currency
                        if isinstance(cell.value, (int, float)):
                            dimension = worksheet.column_dimensions[header.column_letter]
                            dimension.width = max(dimension.width, len(f"Rp {cell.value:,.2f}") + 2)
            for row in worksheet.iter_rows(min_row=2):
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        cell.data_type = "s"

    return output.getvalue()

def _result_frame(result: EklaimAnalysisResult, attribute: str, fallback: pd.DataFrame | None = None) -> pd.DataFrame:
    frame = getattr(result, attribute, None)
    if frame is not None:
        return frame
    return fallback if fallback is not None else pd.DataFrame()


def _summary_rows(result: EklaimAnalysisResult) -> list[dict[str, object]]:
    rows = []
    overall = getattr(result, "tariff_comparison_df", pd.DataFrame())
    overall = overall.loc[overall["Jenis Rawat"].eq("Keseluruhan")].iloc[0] if not overall.empty else None
    coverage = {
        "Total Tarif Grouper (TOTAL_TARIF)": "Cakupan Tarif INA-CBG (%)",
        "Total Tarif RS": "Cakupan Tarif RS (%)",
        "Selisih Total Tarif RS - Grouper": "Cakupan Pasangan RS - INA-CBG (%)",
        "Total Tarif iDRG (C2)": "Cakupan Tarif iDRG (%)",
    }
    for key, value in result.summary.items():
        name = format_summary_label(key)
        coverage_key = coverage.get(key)
        if overall is not None and coverage_key and coverage_key in overall:
            pct = overall[coverage_key]
            if pd.isna(pct) or pct < 100:
                name = f"Subtotal parsial · {name}"
            rows.append({"Metrik": name, "Nilai": value})
            rows.append({"Metrik": coverage_key, "Nilai": pct})
        else:
            rows.append({"Metrik": name, "Nilai": value})
    return rows
