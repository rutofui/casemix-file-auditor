from __future__ import annotations

import pandas as pd

TARIFF_COLUMNS = {
    "TOTAL_TARIF",
    "TARIF_RS",
    "Selisih_Rp",
    "Tarif iDRG",
    "Total Tarif Grouper",
    "Total Tarif INA-CBG",
    "Total Tarif iDRG",
    "Total Tarif RS",
    "Selisih Rp",
    "Selisih RS - INA-CBG",
    "Selisih RS - iDRG",
    "Selisih iDRG - INA-CBG",
    "Rata-rata Tarif INA-CBG",
    "Rata-rata Tarif iDRG",
    "Rata-rata Tarif RS",
    "Total Tarif Komponen",
    "Tarif Komponen per Klaim",
    "Tarif Komponen per Hari",
}

PERCENTAGE_COLUMNS = {
    "Selisih_Pct",
    "Selisih %",
}

SUMMARY_TARIFF_KEYS = {
    "Total Tarif Grouper (TOTAL_TARIF)",
    "Total Tarif INA-CBG (TOTAL_TARIF)",
    "Total Tarif RS",
    "Selisih Total Tarif RS - Grouper",
    "Selisih Total Tarif RS - INA-CBG",
    "Total Tarif iDRG (C2)",
}


def format_summary_label(key: str) -> str:
    return key.replace("Total Tarif Grouper (TOTAL_TARIF)", "Total Tarif INA-CBG (TOTAL_TARIF)").replace(
        "Tarif RS - Grouper", "Tarif RS - INA-CBG"
    )


def format_idr(value: object) -> str:
    if value is None or value == "" or pd.isna(value):
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
    if value is None or value == "" or pd.isna(value):
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
    if value is None or value == "":
        return "Tidak tersedia"
    if key.endswith("(%)"):
        return format_percentage(value)
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    return str(value)


def normalize_analysis_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame
    aliases = {
        "Total Tarif Grouper": "Total Tarif INA-CBG",
        "Selisih Rp": "Selisih RS - INA-CBG",
        "Selisih %": "Selisih RS - INA-CBG (%)",
    }
    drop = [old for old, current in aliases.items() if old in frame and current in frame]
    display = frame.drop(columns=drop).copy()
    rename = {old: current for old, current in aliases.items() if old in display and current not in display}
    return display.rename(columns=rename)


def format_analysis_frame_for_display(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame

    display = normalize_analysis_frame(frame)
    for column in display.columns:
        if (
            column in TARIFF_COLUMNS
            or column.startswith("Total Tarif ")
            or column.startswith("Rata-rata Tarif ")
            or column.endswith("Tarif Komponen per Klaim")
            or column.endswith("Tarif Komponen per Hari")
        ):
            display[column] = display[column].map(format_idr)
        elif column in PERCENTAGE_COLUMNS or column.endswith("(%)"):
            display[column] = display[column].map(format_percentage)
        elif column == "Nilai":
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else str(value))
    return display


def tariff_excel_format(key: str) -> str | None:
    if (
        key in TARIFF_COLUMNS
        or key.startswith("Total Tarif ")
        or key.startswith("Rata-rata Tarif ")
        or key.endswith("Tarif Komponen per Klaim")
        or key.endswith("Tarif Komponen per Hari")
    ):
        return '"Rp "#,##0.00;[Red]-"Rp "#,##0.00'
    if key in PERCENTAGE_COLUMNS or key.endswith("(%)"):
        return "0.00%"
    return None
