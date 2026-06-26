from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO
import re

import pandas as pd

from .config import CLAIM_COLUMNS, is_valid_sep, normalize_sep


@dataclass
class ExcelParseResult:
    df: pd.DataFrame
    warnings: list[str]


COLUMN_ALIASES = {
    "No SEP": ["No SEP", "No. SEP", "Nomor SEP", "SEP", "No_SEP", "NOSEP"],
    "Tanggal Registrasi": [
        "Tanggal Registrasi",
        "Tgl Registrasi",
        "Tanggal Masuk",
        "Tgl Masuk",
    ],
    "Tanggal Pulang": ["Tanggal Pulang", "Tgl Pulang", "Tanggal Keluar", "Tgl Keluar"],
    "No RM": ["No RM", "No. RM", "Nomor RM", "NRM", "Rekam Medis", "No Rekam Medis"],
    "Nama Pasien": ["Nama Pasien", "Pasien", "Nama"],
    "Instalasi": ["Instalasi", "Unit", "Jenis Rawat", "Rawat"],
    "Diagnosa": ["Diagnosa", "Diagnosis", "Diagnosa Utama", "Dx"],
    "Tindakan": ["Tindakan", "Prosedur", "Procedure", "Px"],
}


def _simplify_column_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _find_column(df: pd.DataFrame, canonical_name: str) -> str | None:
    aliases = COLUMN_ALIASES.get(canonical_name, [canonical_name])
    simplified_lookup = {_simplify_column_name(col): col for col in df.columns}
    for alias in aliases:
        match = simplified_lookup.get(_simplify_column_name(alias))
        if match is not None:
            return match
    return None


def _safe_string(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def read_claims_excel(file_obj: str | BinaryIO) -> ExcelParseResult:
    warnings: list[str] = []
    try:
        raw_df = pd.read_excel(file_obj, dtype=object)
    except Exception as exc:  # pragma: no cover - message is surfaced in Streamlit
        raise ValueError(f"Excel gagal dibaca: {exc}") from exc

    if raw_df.empty:
        warnings.append("Excel tidak berisi baris klaim.")

    output = pd.DataFrame(index=raw_df.index)
    for canonical_col in CLAIM_COLUMNS:
        source_col = _find_column(raw_df, canonical_col)
        if source_col is None:
            output[canonical_col] = ""
            if canonical_col == "No SEP":
                warnings.append("Kolom No SEP tidak ditemukan. Semua baris perlu review manual.")
        else:
            output[canonical_col] = raw_df[source_col]

    for col in CLAIM_COLUMNS:
        output[col] = output[col].map(_safe_string)

    output["_row_number"] = range(2, len(output) + 2)
    output["_no_sep_normalized"] = output["No SEP"].map(normalize_sep)
    output["_sep_valid"] = output["_no_sep_normalized"].map(is_valid_sep)

    empty_sep_count = int((output["_no_sep_normalized"] == "").sum())
    invalid_sep_count = int(
        ((output["_no_sep_normalized"] != "") & (~output["_sep_valid"])).sum()
    )
    if empty_sep_count:
        warnings.append(f"{empty_sep_count} baris memiliki SEP kosong.")
    if invalid_sep_count:
        warnings.append(f"{invalid_sep_count} baris memiliki format SEP tidak valid.")

    return ExcelParseResult(df=output, warnings=warnings)

