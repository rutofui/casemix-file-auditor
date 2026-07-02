from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import BinaryIO

import pandas as pd

from src.config import is_valid_sep, normalize_sep

PTD_RAWAT_INAP = "1"
PTD_RAWAT_JALAN = "2"

REQUIRED_COLUMNS = [
    "SEP",
    "PTD",
    "INACBG",
    "DIAGLIST",
    "PROCLIST",
    "TOTAL_TARIF",
    "TARIF_RS",
    "LOS",
    "DPJP",
    "C2",
    "NAMA_PASIEN",
    "MRN",
    "ICU_INDIKATOR",
    "ICU_LOS",
    "RAWAT_INTENSIF",
]

NUMERIC_COLUMNS = [
    "TOTAL_TARIF",
    "TARIF_RS",
    "TARIF_INACBG",
    "LOS",
    "ICU_INDIKATOR",
    "ICU_LOS",
    "RAWAT_INTENSIF",
    "VENT_HOUR",
]


@dataclass
class EklaimParseResult:
    df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)
    source_label: str = ""


def read_eklaim_txt(
    file_obj: str | BinaryIO,
    *,
    expected_ptd: str | None = None,
    source_label: str = "",
) -> EklaimParseResult:
    warnings: list[str] = []
    try:
        raw_df = pd.read_csv(file_obj, sep="\t", dtype=str, keep_default_na=False)
    except Exception as exc:
        raise ValueError(f"File TXT e-Klaim gagal dibaca: {exc}") from exc

    if raw_df.empty:
        warnings.append(f"{source_label}: file tidak berisi baris klaim." if source_label else "File tidak berisi baris klaim.")
        return EklaimParseResult(df=_empty_eklaim_df(), warnings=warnings, source_label=source_label)

    missing = [col for col in REQUIRED_COLUMNS if col not in raw_df.columns]
    if missing:
        raise ValueError(f"Kolom wajib tidak ditemukan: {', '.join(missing)}")

    df = raw_df.copy()
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[f"_{col.lower()}_num"] = df[col].map(_safe_number)

    df["_sep_normalized"] = df["SEP"].map(normalize_sep)
    df["_sep_valid"] = df["_sep_normalized"].map(is_valid_sep)
    df["_ptd"] = df["PTD"].astype(str).str.strip()
    df["_severity"] = df["INACBG"].map(parse_inacbg_severity)
    df["_dpjp_normalized"] = df["DPJP"].map(normalize_dpjp)

    idrg_fields = df["C2"].map(extract_idrg_fields)
    df["_idrg_cost_weight"] = idrg_fields.map(lambda item: item.get("cost_weight"))
    df["_idrg_drg_code"] = idrg_fields.map(lambda item: item.get("drg_code", ""))
    df["_idrg_total_tarif"] = idrg_fields.map(lambda item: item.get("total_tarif"))

    invalid_sep = int((~df["_sep_valid"]).sum())
    if invalid_sep:
        warnings.append(f"{source_label}: {invalid_sep} baris memiliki SEP kosong/tidak valid.")

    missing_weight = int(df["_idrg_cost_weight"].isna().sum())
    if missing_weight:
        warnings.append(f"{source_label}: {missing_weight} baris tanpa idrg.cost_weight di kolom C2.")

    if expected_ptd:
        mismatch = int((df["_ptd"] != expected_ptd).sum())
        if mismatch:
            expected_label = "Rawat Inap" if expected_ptd == PTD_RAWAT_INAP else "Rawat Jalan"
            warnings.append(
                f"{source_label}: {mismatch} baris tidak ber-PTD {expected_ptd} ({expected_label})."
            )

    return EklaimParseResult(df=df, warnings=warnings, source_label=source_label)


def build_file_review_claims(df: pd.DataFrame) -> pd.DataFrame:
    """Adapt an e-Klaim MIX TXT DataFrame into the claims shape used by
    ``matcher.build_file_review`` (same canonical column names produced by
    ``parser_excel.read_claims_excel``), plus the parsed ICD-10/ICD-9-CM code
    lists needed for the first-page code check.
    """
    columns = [
        "No SEP",
        "Tanggal Masuk",
        "Tanggal Pulang",
        "Kelas Perawatan",
        "No RM",
        "Nama Pasien",
        "Diagnosa",
        "_row_number",
        "_no_sep_normalized",
        "_sep_valid",
        "_icd10_codes",
        "_icd9_codes",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)

    out = pd.DataFrame(index=df.index)
    out["No SEP"] = df["SEP"].map(_safe_string)
    out["Tanggal Masuk"] = _optional_series(df, ["ADMISSION_DATE", "TANGGAL_MASUK", "TGL_MASUK", "TANGGAL_REGISTRASI"])
    out["Tanggal Pulang"] = _optional_series(df, ["DISCHARGE_DATE", "TANGGAL_KELUAR", "TGL_KELUAR", "TANGGAL_PULANG", "TGL_PULANG"])
    out["Kelas Perawatan"] = _optional_series(df, ["KELAS_RAWAT", "KELAS_PERAWATAN", "KELAS", "KELAS_RS", "HAK_KELAS"])
    out["No RM"] = df["MRN"].map(_safe_string)
    out["Nama Pasien"] = df["NAMA_PASIEN"].map(_safe_string)
    out["Diagnosa"] = df["DIAGLIST"].map(_safe_string)
    out["_row_number"] = range(2, len(out) + 2)
    out["_no_sep_normalized"] = df["_sep_normalized"]
    out["_sep_valid"] = df["_sep_valid"]
    out["_icd10_codes"] = df["DIAGLIST"].map(split_codes)
    out["_icd9_codes"] = df["PROCLIST"].map(split_codes)
    return out[columns]


def _optional_series(df: pd.DataFrame, aliases: list[str]) -> pd.Series:
    for column in aliases:
        if column in df.columns:
            return df[column].map(_safe_string)
    return pd.Series([""] * len(df), index=df.index)


def _safe_string(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    return text


def combine_eklaim_frames(
    ri_result: EklaimParseResult | None,
    rj_result: EklaimParseResult | None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    warnings: list[str] = []
    ri_df = ri_result.df if ri_result is not None and not ri_result.df.empty else _empty_eklaim_df()
    rj_df = rj_result.df if rj_result is not None and not rj_result.df.empty else _empty_eklaim_df()

    if ri_result is not None:
        warnings.extend(ri_result.warnings)
    if rj_result is not None:
        warnings.extend(rj_result.warnings)

    if ri_df.empty and rj_df.empty:
        return ri_df, rj_df, warnings

    ri_seps = set(ri_df.loc[ri_df["_sep_valid"], "_sep_normalized"].astype(str))
    rj_seps = set(rj_df.loc[rj_df["_sep_valid"], "_sep_normalized"].astype(str))
    duplicate_seps = sorted(ri_seps & rj_seps)
    if duplicate_seps:
        warnings.append(f"Ditemukan {len(duplicate_seps)} SEP duplikat antara file Rawat Inap dan Rawat Jalan.")

    return ri_df, rj_df, warnings


def parse_c2_json_objects(c2_text: object) -> list[dict]:
    if c2_text is None:
        return []
    text = str(c2_text)
    if not text.strip():
        return []

    objects: list[dict] = []
    index = 0
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        depth = 0
        start = index
        for position in range(index, len(text)):
            char = text[position]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start : position + 1]
                    try:
                        payload = json.loads(chunk)
                    except json.JSONDecodeError:
                        payload = None
                    if isinstance(payload, dict):
                        objects.append(payload)
                    index = position + 1
                    break
        else:
            break
    return objects


def extract_idrg_fields(c2_text: object) -> dict[str, object]:
    for payload in parse_c2_json_objects(c2_text):
        idrg = payload.get("idrg")
        if not isinstance(idrg, dict):
            continue
        cost_weight = _safe_number(idrg.get("cost_weight"))
        if cost_weight is None:
            continue
        return {
            "cost_weight": cost_weight,
            "total_cost_weight": _safe_number(idrg.get("total_cost_weight")),
            "drg_code": str(idrg.get("drg_code", "") or ""),
            "drg_description": str(idrg.get("drg_description", "") or ""),
            "total_tarif": _safe_number(idrg.get("total_tarif")),
        }
    return {}


def parse_inacbg_severity(inacbg_code: object) -> int | None:
    if inacbg_code is None:
        return None
    code = str(inacbg_code).strip().upper()
    if not code:
        return None
    suffix = code.rsplit("-", 1)[-1]
    if suffix == "III":
        return 3
    if suffix == "II":
        return 2
    if suffix == "I":
        return 1
    if suffix == "0":
        return 0
    return None


def split_codes(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text or text == "-":
        return []
    codes = [part.strip().upper() for part in text.split(";")]
    return [code for code in codes if code and code != "-"]


def codes_are_present(value: object) -> bool:
    return bool(split_codes(value))


def normalize_dpjp(value: object) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value).strip().upper())
    return text


def _safe_number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "-"}:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", text.replace(",", ""))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _empty_eklaim_df() -> pd.DataFrame:
    columns = list(REQUIRED_COLUMNS) + [
        "_total_tarif_num",
        "_tarif_rs_num",
        "_los_num",
        "_icu_indikator_num",
        "_icu_los_num",
        "_rawat_intensif_num",
        "_sep_normalized",
        "_sep_valid",
        "_ptd",
        "_severity",
        "_dpjp_normalized",
        "_idrg_cost_weight",
        "_idrg_drg_code",
        "_idrg_total_tarif",
    ]
    return pd.DataFrame(columns=columns)
