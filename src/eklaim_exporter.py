from __future__ import annotations

from io import BytesIO

import pandas as pd

from src.eklaim_analyzer import EklaimAnalysisResult
from src.eklaim_formatting import format_analysis_frame_for_display, format_summary_value
from src.exporter import format_worksheet


def export_eklaim_analysis_to_excel(result: EklaimAnalysisResult) -> bytes:
    output = BytesIO()
    summary_rows = [
        {"Metrik": key, "Nilai": format_summary_value(key, value)}
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
            if frame is None or frame.empty:
                pd.DataFrame().to_excel(writer, sheet_name=safe_name, index=False)
            else:
                format_analysis_frame_for_display(frame).to_excel(
                    writer,
                    sheet_name=safe_name,
                    index=False,
                )

        for worksheet in writer.book.worksheets:
            format_worksheet(worksheet)

    return output.getvalue()
