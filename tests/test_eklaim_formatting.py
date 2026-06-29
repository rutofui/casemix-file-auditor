from __future__ import annotations

import pandas as pd

from src.eklaim_formatting import (
    format_analysis_frame_for_display,
    format_idr,
    format_percentage,
    format_summary_value,
)


def test_format_idr_uses_indonesian_rupiah_format() -> None:
    assert format_idr(1_000_000) == "Rp 1.000.000,00"
    assert format_idr(-2500.5) == "-Rp 2.500,50"


def test_format_percentage_appends_percent_suffix() -> None:
    assert format_percentage(30) == "30,00%"
    assert format_percentage(12.345) == "12,35%"


def test_format_summary_value_formats_tariff_metrics() -> None:
    assert format_summary_value("Total Tarif RS", 2_500_000) == "Rp 2.500.000,00"
    assert format_summary_value("Total Klaim Rawat Inap", 12) == "12"


def test_format_analysis_frame_for_display_formats_tariff_and_percent_columns() -> None:
    frame = pd.DataFrame(
        [
            {
                "TOTAL_TARIF": 1_000_000,
                "TARIF_RS": 1_500_000,
                "Selisih_Rp": 500_000,
                "Selisih_Pct": 33.33,
            }
        ]
    )
    display = format_analysis_frame_for_display(frame)
    assert display.iloc[0]["TOTAL_TARIF"] == "Rp 1.000.000,00"
    assert display.iloc[0]["Selisih_Pct"] == "33,33%"
