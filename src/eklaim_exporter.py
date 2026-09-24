from __future__ import annotations

from io import BytesIO

import pandas as pd

from src.eklaim_analyzer import EklaimAnalysisResult
from src.eklaim_formatting import PERCENTAGE_COLUMNS, tariff_excel_format
from src.exporter import format_worksheet


def export_eklaim_analysis_to_excel(result: EklaimAnalysisResult) -> bytes:
    output = BytesIO()
    summary_rows = [
        {"Metrik": key, "Nilai": value}
        for key, value in result.summary.items()
    ]
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
        ("ptd_tidak_valid", result.invalid_ptd_df),
        ("angka_tidak_valid", result.invalid_numeric_df),
        ("peringatan", pd.DataFrame({"Peringatan": result.warnings})),
        ("kelengkapan_dx_px", result.completeness_df),
        ("severity_tinggi_los_rendah", result.severity_high_los_low_df),
        ("severity_rendah_los_tinggi", result.severity_low_los_high_df),
        ("rawat_intensif", result.intensive_care_df),
        ("tarif_grouper_lebih_besar", result.grouper_gt_rs_df),
        ("selisih_lebih_30pct", result.selisih_gt_30pct_df),
        ("selisih_dpjp_ri", result.dpjp_ri_df),
        ("selisih_dpjp_rj", result.dpjp_rj_df),
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
            for header in worksheet[1]:
                for row in worksheet.iter_rows(min_row=2, min_col=header.column, max_col=header.column):
                    cell = row[0]
                    metric = str(worksheet.cell(cell.row, 1).value) if header.value == "Nilai" else ""
                    percentage = header.value in PERCENTAGE_COLUMNS or "(%)" in metric
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

    return output.getvalue()
