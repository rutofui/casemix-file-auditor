from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, TextIO

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
    "TARIF_POLI_EKS",
    "LOS",
    "ICU_INDIKATOR",
    "ICU_LOS",
    "VENT_HOUR",
    "TARIF_SUBACUTE",
    "TARIF_CHRONIC",
    "TARIF_SP",
    "TARIF_SR",
    "TARIF_SI",
    "TARIF_SD",
]

TARIFF_COMPONENTS = [
    "PROSEDUR_NON_BEDAH", "PROSEDUR_BEDAH", "KONSULTASI", "TENAGA_AHLI",
    "KEPERAWATAN", "PENUNJANG", "RADIOLOGI", "LABORATORIUM",
    "PELAYANAN_DARAH", "REHABILITASI", "KAMAR_AKOMODASI", "RAWAT_INTENSIF",
    "OBAT", "ALKES", "BMHP", "SEWA_ALAT", "OBAT_KRONIS", "OBAT_KEMO",
]
NUMERIC_COLUMNS.extend(col for col in TARIFF_COMPONENTS if col not in NUMERIC_COLUMNS)


@dataclass
class EklaimParseResult:
    df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)
    source_label: str = ""


def read_eklaim_txt(
    file_obj: str | Path | BinaryIO | TextIO,
    *,
    expected_ptd: str | None = None,
    source_label: str = "",
) -> EklaimParseResult:
    warnings: list[str] = []
    source = source_label or (Path(file_obj).name if isinstance(file_obj, (str, Path)) else str(getattr(file_obj, "name", "") or ""))
    try:
        if isinstance(file_obj, (str, Path)):
            content = Path(file_obj).read_bytes().decode("utf-8-sig")
        else:
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            content = file_obj.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8-sig")
            elif content.startswith("\ufeff"):
                content = content[1:]
        reader = csv.reader(io.StringIO(content, newline=""), delimiter="\t", strict=True)
        headers = next(reader, None)
        if headers is None:
            warnings.append(f"{source}: file tidak berisi baris klaim." if source else "File tidak berisi baris klaim.")
            return EklaimParseResult(df=_empty_eklaim_df(), warnings=warnings, source_label=source)
        if len(headers) != len(set(headers)):
            raise ValueError(f"{source}: header memiliki nama kolom duplikat (baris 1).")
        missing = [col for col in REQUIRED_COLUMNS if col not in headers]
        if missing:
            raise ValueError(f"{source}: kolom wajib tidak ditemukan: {', '.join(missing)} (baris 1).")
        records = []
        start_lines = []
        while True:
            row_start = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            if not row:
                continue
            if len(row) != len(headers):
                raise ValueError(f"{source}: jumlah field tidak sesuai header (baris {row_start}).")
            records.append(row)
            start_lines.append(row_start)
    except csv.Error as exc:
        raise ValueError(f"{source}: format CSV tidak valid (baris {reader.line_num or 1}).") from exc
    except (OSError, UnicodeError, TypeError) as exc:
        raise ValueError(f"{source}: file TXT e-Klaim gagal dibaca.") from exc

    raw_df = pd.DataFrame(records, columns=headers, dtype=str)
    if raw_df.empty:
        warnings.append(f"{source}: file tidak berisi baris klaim." if source else "File tidak berisi baris klaim.")
        return EklaimParseResult(df=_empty_eklaim_df(), warnings=warnings, source_label=source)

    df = raw_df.copy()
    df["_source"] = source
    df["_row_number"] = start_lines
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[f"_{col.lower()}_num"] = df[col].map(
                lambda value: _safe_number(
                    value,
                    non_negative=True,
                    integer_only=col in {"LOS", "ICU_LOS"},
                    allowed_values={0, 1} if col == "ICU_INDIKATOR" else None,
                )
            )

    df["_sep_normalized"] = df["SEP"].map(normalize_sep)
    df["_sep_valid"] = df["_sep_normalized"].map(is_valid_sep)
    df["_ptd"] = df["PTD"].astype(str).str.strip()
    df["_severity"] = df["INACBG"].map(parse_inacbg_severity)
    df["_dpjp_normalized"] = df["DPJP"].map(normalize_dpjp)

    c2_results = df["C2"].map(_extract_idrg_fields_with_status)
    idrg_fields = c2_results.map(lambda result: result["fields"])
    df["_idrg_cost_weight"] = idrg_fields.map(lambda item: item.get("cost_weight"))
    df["_idrg_total_cost_weight"] = idrg_fields.map(lambda item: item.get("total_cost_weight"))
    df["_idrg_drg_code"] = idrg_fields.map(lambda item: item.get("drg_code", ""))
    df["_idrg_total_tarif"] = idrg_fields.map(lambda item: item.get("total_tarif"))
    df["_idrg_grouper_version"] = idrg_fields.map(lambda item: item.get("grouper_version", ""))
    df["_idrg_logic_version"] = idrg_fields.map(lambda item: item.get("logic_version", ""))
    df["_c2_status"] = c2_results.map(lambda result: result["status"])
    df["_c2_issues"] = c2_results.map(lambda result: result["issues"])

    invalid_sep = int((~df["_sep_valid"]).sum())
    if invalid_sep:
        warnings.append(f"{source}: {invalid_sep} baris memiliki SEP kosong/tidak valid.")

    missing_weight = int(df["_idrg_cost_weight"].isna().sum())
    if missing_weight:
        warnings.append(f"{source}: {missing_weight} baris tanpa idrg.cost_weight di kolom C2.")

    if expected_ptd:
        mismatch = int((df["_ptd"] != expected_ptd).sum())
        if mismatch:
            expected_label = "Rawat Inap" if expected_ptd == PTD_RAWAT_INAP else "Rawat Jalan"
            warnings.append(
                f"{source}: {mismatch} baris tidak ber-PTD {expected_ptd} ({expected_label})."
            )

    return EklaimParseResult(df=df, warnings=warnings, source_label=source)


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
        "_source",
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
    out["_source"] = df["_source"] if "_source" in df else ""
    out["_row_number"] = df["_row_number"] if "_row_number" in df else range(2, len(out) + 2)
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
    duplicates = ri_seps & rj_seps
    if duplicates:
        warnings.append(f"Ditemukan {len(duplicates)} SEP duplikat antara file Rawat Inap dan Rawat Jalan.")

    return ri_df, rj_df, warnings


def parse_c2_json_objects(c2_text: object) -> list[dict]:
    if c2_text is None:
        return []
    text = str(c2_text)
    if not text.strip():
        return []

    objects: list[dict] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        try:
            payload, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        if isinstance(payload, dict):
            objects.append(payload)
        index = end
    return objects


def extract_idrg_fields(c2_text: object) -> dict[str, object]:
    return _extract_idrg_fields_with_status(c2_text)["fields"]


def _extract_idrg_fields_with_status(c2_text: object) -> dict[str, object]:
    text = "" if c2_text is None else str(c2_text).strip()
    if not text or text.lower() in {"none", "nan"}:
        return {"fields": {}, "status": "missing", "issues": []}
    objects = parse_c2_json_objects(text)
    if not objects:
        return {"fields": {}, "status": "invalid", "issues": ["JSON C2 tidak valid"]}
    issues: list[str] = []
    for payload in objects:
        idrg = payload.get("idrg")
        if not isinstance(idrg, dict):
            continue
        fields = {}
        for field_name in ("cost_weight", "total_cost_weight", "total_tarif"):
            value = idrg.get(field_name)
            number = _safe_number(value, non_negative=True)
            if number is not None:
                fields[field_name] = number
            else:
                problem = "tidak ditemukan" if value is None or str(value).strip() == "" else "tidak valid"
                issues.append(f"idrg.{field_name} {problem}")
        fields["drg_code"] = str(idrg.get("drg_code", "") or "")
        fields["drg_description"] = str(idrg.get("drg_description", "") or "")
        fields["grouper_version"] = str(idrg.get("grouper_version", idrg.get("version", "")) or "")
        fields["logic_version"] = str(idrg.get("logic_version", "") or "")
        return {"fields": fields, "status": "valid", "issues": issues}
    return {"fields": {}, "status": "no-idrg", "issues": []}


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


def _safe_number(
    value: object,
    *,
    non_negative: bool = False,
    integer_only: bool = False,
    allowed_values: set[int] | None = None,
) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "-"}:
        return None
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        return None
    try:
        number = float(text.replace(",", ""))
        valid = number == number and abs(number) != float("inf")
        valid = valid and (not non_negative or number >= 0)
        valid = valid and (not integer_only or number.is_integer())
        valid = valid and (allowed_values is None or number in allowed_values)
        return number if valid else None
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
        "_vent_hour_num",
        "_tarif_inacbg_num",
        *[f"_{col.lower()}_num" for col in TARIFF_COMPONENTS + ["TARIF_SUBACUTE", "TARIF_CHRONIC", "TARIF_SP", "TARIF_SR", "TARIF_SI", "TARIF_SD"]],
        "_source",
        "_row_number",
        "_sep_normalized",
        "_sep_valid",
        "_ptd",
        "_severity",
        "_dpjp_normalized",
        "_idrg_cost_weight",
        "_idrg_total_cost_weight",
        "_idrg_drg_code",
        "_idrg_total_tarif",
        "_idrg_grouper_version",
        "_idrg_logic_version",
        "_c2_status",
        "_c2_issues",
    ]
    return pd.DataFrame(columns=columns)
