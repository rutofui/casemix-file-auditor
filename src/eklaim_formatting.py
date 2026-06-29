from __future__ import annotations

import pandas as pd

TARIFF_COLUMNS = {
    "TOTAL_TARIF",
    "TARIF_RS",
    "Selisih_Rp",
    "Total Tarif Grouper",
    "Total Tarif RS",
    "Selisih Rp",
}

PERCENTAGE_COLUMNS = {
    "Selisih_Pct",
    "Selisih %",
}

SUMMARY_TARIFF_KEYS = {
    "Total Tarif Grouper (TOTAL_TARIF)",
    "Total Tarif RS",
    "Selisih Total Tarif RS - Grouper",
}


def format_idr(value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)

    sign = "-" if amount < 0 else ""
    cents = round(abs(amount) * 100)
    integer, fraction = divmod(cents, 100)
    integer_part = f"{integer:,}".replace(",", ".")
    return f"{sign}Rp {integer_part},{fraction:02d}"


def format_percentage(value: object, *, decimals: int = 2) -> str:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    formatted = f"{number:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted}%"


def format_summary_value(key: str, value: object) -> str:
    if key in SUMMARY_TARIFF_KEYS:
        return format_idr(value)
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    return str(value)


def format_analysis_frame_for_display(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame

    display = frame.copy()
    for column in display.columns:
        if column in TARIFF_COLUMNS:
            display[column] = display[column].map(format_idr)
        elif column in PERCENTAGE_COLUMNS:
            display[column] = display[column].map(format_percentage)
    return display
