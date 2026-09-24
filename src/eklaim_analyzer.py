from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import fsum

import pandas as pd

from src.parser_eklaim_txt import (
    NUMERIC_COLUMNS, TARIFF_COMPONENTS, PTD_RAWAT_INAP, PTD_RAWAT_JALAN,
    codes_are_present, split_codes,
)

CARE_TYPES = {PTD_RAWAT_INAP: "Rawat Inap", PTD_RAWAT_JALAN: "Rawat Jalan"}
TARIFFS = {"RS": "_tarif_rs_num", "INA-CBG": "_total_tarif_num", "iDRG": "_idrg_total_tarif"}

FLAG_COLUMNS = [
    "Sumber",
    "Baris",
    "SEP",
    "NAMA_PASIEN",
    "MRN",
    "PTD",
    "INACBG",
    "Severity",
    "LOS",
    "DIAGLIST",
    "PROCLIST",
    "TOTAL_TARIF",
    "TARIF_RS",
    "Tarif iDRG",
    "Basis Tarif",
    "Selisih_Rp",
    "Selisih_Pct",
    "DPJP",
    "Catatan",
]


@dataclass
class EklaimAnalysisResult:
    summary: dict[str, object] = field(default_factory=dict)
    casemix_index: dict[str, object] = field(default_factory=dict)
    completeness_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    severity_high_los_low_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    severity_low_los_high_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    intensive_care_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    grouper_gt_rs_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    selisih_gt_30pct_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    dpjp_ri_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    dpjp_rj_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    top_icd10_ri_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    top_icd10_rj_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    top_icd9_ri_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    top_icd9_rj_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    data_quality: dict[str, object] = field(default_factory=dict)
    invalid_ptd_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    invalid_numeric_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    tariff_comparison_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    duplicate_claims_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    quarantine_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    validation_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    activity_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    los_profile_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    components_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    tariff_components_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    casemix_profile_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    outpatient_visits_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    service_days_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    period_activity_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    discharge_status_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    methodology_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    warnings: list[str] = field(default_factory=list)


def build_eklaim_analysis(
    ri_df: pd.DataFrame,
    rj_df: pd.DataFrame,
) -> EklaimAnalysisResult:
    input_frames = [df for df in (ri_df, rj_df) if df is not None and not df.empty]
    all_claims = pd.concat(input_frames, ignore_index=True) if input_frames else pd.DataFrame()
    all_claims = _enrich_claims(all_claims)
    eligible, duplicates, quarantine, duplicate_counts = _select_claims(all_claims)
    invalid_ptd = all_claims.loc[~all_claims["_ptd"].isin(CARE_TYPES)] if not all_claims.empty else all_claims
    combined = _prepare_claims(eligible, PTD_RAWAT_INAP)
    ri = combined.loc[combined["_ptd"].eq(PTD_RAWAT_INAP)] if not combined.empty else pd.DataFrame()
    rj = combined.loc[combined["_ptd"].eq(PTD_RAWAT_JALAN)] if not combined.empty else pd.DataFrame()
    data_quality, invalid_numeric = _data_quality(all_claims)
    validation = _validate_claims(all_claims)
    data_quality.update(duplicate_counts)
    data_quality.update({"Klaim Dianalisis": len(combined), "Baris Dikecualikan": len(quarantine),
                         "Temuan Validasi": len(validation)})
    warnings = []
    if not combined.empty and (combined[["_total_tarif_num", "_tarif_rs_num"]].isna().any().any()):
        warnings.append("Total tarif bersifat parsial karena ada nilai TOTAL_TARIF atau TARIF_RS kosong/tidak valid; selisih total dan agregat DPJP terkait dikosongkan.")
    if not combined.empty and combined["_idrg_total_tarif"].isna().any():
        warnings.append("Tarif iDRG parsial/tidak tersedia. Perbandingan memakai pasangan tarif valid; cakupan ditampilkan per indikator.")
    if not quarantine.empty:
        warnings.append(f"{len(quarantine)} baris dikecualikan dari seluruh KPI; lihat karantina. Konflik SEP tidak dipilih otomatis.")
    if not validation.empty:
        warnings.append(f"{len(validation)} temuan validasi perlu telaah. Nilai kosong/tidak valid tidak diubah menjadi nol.")

    groups = [(CARE_TYPES[PTD_RAWAT_INAP], ri), (CARE_TYPES[PTD_RAWAT_JALAN], rj)]

    return EklaimAnalysisResult(
        summary=_build_summary(ri, rj, combined),
        casemix_index=_build_casemix_index(ri, rj),
        completeness_df=_build_completeness_df(combined),
        severity_high_los_low_df=_build_severity_high_los_low_df(ri),
        severity_low_los_high_df=_build_severity_low_los_high_df(ri),
        intensive_care_df=_build_intensive_care_df(combined),
        grouper_gt_rs_df=_build_grouper_gt_rs_df(combined),
        selisih_gt_30pct_df=_build_selisih_gt_30pct_df(combined),
        dpjp_ri_df=_build_dpjp_summary_df(ri),
        dpjp_rj_df=_build_dpjp_summary_df(rj),
        top_icd10_ri_df=_build_top_codes_df(ri, code_column="DIAGLIST", label="ICD-10"),
        top_icd10_rj_df=_build_top_codes_df(rj, code_column="DIAGLIST", label="ICD-10"),
        top_icd9_ri_df=_build_top_codes_df(ri, code_column="PROCLIST", label="ICD-9-CM"),
        top_icd9_rj_df=_build_top_codes_df(rj, code_column="PROCLIST", label="ICD-9-CM"),
        data_quality=data_quality,
        invalid_ptd_df=_invalid_ptd_df(invalid_ptd),
        invalid_numeric_df=invalid_numeric,
        tariff_comparison_df=pd.DataFrame([
            {"Jenis Rawat": label, **_tariff_metrics(frame)} for label, frame in groups + [("Keseluruhan", combined)]
        ]),
        duplicate_claims_df=duplicates,
        quarantine_df=quarantine,
        validation_df=validation,
        activity_df=pd.DataFrame([{"Jenis Rawat": label, **_activity_metrics(frame)} for label, frame in groups]),
        los_profile_df=_los_profiles(ri),
        components_df=_component_profiles(groups, TARIFF_COMPONENTS),
        tariff_components_df=_component_profiles(groups, ["TARIF_INACBG", "TARIF_SUBACUTE", "TARIF_CHRONIC", "TARIF_SP", "TARIF_SR", "TARIF_SI", "TARIF_SD"], inacbg=True),
        casemix_profile_df=_casemix_profiles(groups),
        outpatient_visits_df=_outpatient_visits(rj),
        service_days_df=_service_days(groups),
        period_activity_df=_period_activity(groups),
        discharge_status_df=_discharge_status(groups),
        metadata_df=_metadata(all_claims, eligible),
        methodology_df=_methodology(),
        warnings=warnings,
    )


def _prepare_claims(df: pd.DataFrame, default_ptd: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    prepared = df.copy()
    if "_ptd" in prepared.columns:
        prepared["_ptd"] = prepared["_ptd"].astype(str).str.strip()
    else:
        prepared["_ptd"] = default_ptd
    if "_total_tarif_num" not in prepared.columns:
        prepared["_total_tarif_num"] = prepared.get("TOTAL_TARIF", pd.Series(dtype=object)).map(_as_number)
    if "_tarif_rs_num" not in prepared.columns:
        prepared["_tarif_rs_num"] = prepared.get("TARIF_RS", pd.Series(dtype=object)).map(_as_number)
    if "_los_num" not in prepared.columns:
        prepared["_los_num"] = prepared.get("LOS", pd.Series(dtype=object)).map(_as_number)
    if "_severity" not in prepared.columns:
        prepared["_severity"] = prepared.get("INACBG", pd.Series(dtype=object)).map(_severity_from_column)
    prepared["_selisih_rp"] = prepared["_tarif_rs_num"] - prepared["_total_tarif_num"]
    prepared["_selisih_pct"] = prepared.apply(_selisih_pct, axis=1)
    return prepared


def _data_quality(df: pd.DataFrame) -> tuple[dict[str, object], pd.DataFrame]:
    if df.empty:
        return {"Baris Klaim": 0, "SEP Unik Valid": 0, "SEP Kosong": 0, "SEP Tidak Valid": 0,
                "PTD Tidak Valid": 0, "Nilai Numerik Kosong": 0, "Nilai Numerik Tidak Valid": 0,
                "Cost Weight Tersedia": 0, "Cakupan Cost Weight (%)": 0.0}, pd.DataFrame(columns=["SEP", "Field", "Nilai", "Masalah"])
    valid = df["_sep_valid"]
    sep = df["SEP"].astype(str).str.strip()
    empty_sep = sep.eq("")
    numeric = {column: f"_{column.lower()}_num" for column in NUMERIC_COLUMNS if column in df}
    issues = []
    for field, parsed in numeric.items():
        if parsed not in df:
            continue
        raw = df[field].astype(str).str.strip() if field in df else pd.Series("", index=df.index)
        missing = raw.isin(["", "-", "nan", "None"])
        invalid = ~missing & df[parsed].isna()
        for index in df.index[missing | invalid]:
            issues.append({"Sumber": df.at[index, "_source"], "Baris": df.at[index, "_row_number"],
                           "SEP": df.at[index, "SEP"], "Field": field, "Nilai": raw.at[index],
                           "Masalah": "Kosong" if missing.at[index] else "Format tidak valid"})
    coverage_n = int(df["_idrg_cost_weight"].notna().sum())
    count = len(df)
    detail = pd.DataFrame(issues, columns=["Sumber", "Baris", "SEP", "Field", "Nilai", "Masalah"])
    return {"Baris Klaim": count, "SEP Unik Valid": int(df.loc[valid, "_sep_normalized"].nunique()),
            "SEP Kosong": int(empty_sep.sum()), "SEP Tidak Valid": int((~valid & ~empty_sep).sum()),
            "PTD Tidak Valid": int((~df["_ptd"].isin([PTD_RAWAT_INAP, PTD_RAWAT_JALAN])).sum()),
            "Nilai Numerik Kosong": int(sum(x["Masalah"] == "Kosong" for x in issues)),
            "Nilai Numerik Tidak Valid": int(sum(x["Masalah"] != "Kosong" for x in issues)),
            "Cost Weight Tersedia": coverage_n,
            "Cakupan Cost Weight (%)": round(coverage_n * 100 / count, 2) if count else 0.0}, detail


def _invalid_ptd_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["SEP", "NAMA_PASIEN", "MRN", "PTD", "Catatan"])
    out = _review_rows(df)
    out["Catatan"] = "PTD bukan 1 (Rawat Inap) atau 2 (Rawat Jalan)"
    return out


def _build_summary(ri: pd.DataFrame, rj: pd.DataFrame, combined: pd.DataFrame) -> dict[str, object]:
    total_ri = int(len(ri))
    total_rj = int(len(rj))
    total_all = int(len(combined))
    grouper_values = combined["_total_tarif_num"].dropna() if not combined.empty else pd.Series(dtype=float)
    rs_values = combined["_tarif_rs_num"].dropna() if not combined.empty else pd.Series(dtype=float)
    complete_tariffs = len(grouper_values) == total_all and len(rs_values) == total_all
    total_tarif = grouper_values.sum(min_count=1)
    total_rs = rs_values.sum(min_count=1)
    difference = total_rs - total_tarif if complete_tariffs and total_all else None
    return {
        "Total Klaim Rawat Jalan": total_rj,
        "Total Klaim Rawat Inap": total_ri,
        "Total Klaim Keseluruhan": total_all,
        "Total Tarif Grouper (TOTAL_TARIF)": _clean_number(total_tarif, integer=True),
        "Total Tarif RS": _clean_number(total_rs, integer=True),
        "Selisih Total Tarif RS - Grouper": _clean_number(difference, integer=True),
        "Total Tarif iDRG (C2)": _sum(_numbers(combined, "_idrg_total_tarif")),
    }


def _build_casemix_index(ri: pd.DataFrame, rj: pd.DataFrame) -> dict[str, object]:
    return {
        "Rawat Inap": _cmi_for_frame(ri),
        "Rawat Jalan": _cmi_for_frame(rj),
    }


def _cmi_for_frame(df: pd.DataFrame) -> dict[str, object]:
    weights = _numbers(df, "_idrg_cost_weight").dropna()
    total_weights = _numbers(df, "_idrg_total_cost_weight").dropna()
    missing = len(df) - len(weights)
    claim_count = int(len(weights))
    total_weight = _sum(weights)
    cmi = float(weights.mean()) if claim_count else None
    versions = df.get("_idrg_version", pd.Series(dtype=str)).unique().tolist()
    compatible = len(versions) <= 1
    return {
        "Jumlah Klaim": len(df),
        "Klaim dengan Cost Weight": claim_count,
        "Cakupan Cost Weight (%)": _percent(claim_count, len(df)),
        "Total Cost Weight": round(total_weight, 4) if total_weight is not None and compatible else None,
        "Casemix Index": round(cmi, 4) if cmi is not None and compatible else None,
        "Tanpa Cost Weight": missing,
        "Klaim dengan total_cost_weight": len(total_weights),
        "Cakupan total_cost_weight (%)": _percent(len(total_weights), len(df)),
        "Total total_cost_weight": round(_sum(total_weights), 4) if compatible and len(total_weights) else None,
        "Rata-rata total_cost_weight": round(float(total_weights.mean()), 4) if len(total_weights) and compatible else None,
        "Versi Bobot iDRG": "; ".join(versions),
        "Status CMI": "Versi berbeda; lihat profil per versi" if not compatible else "Bobot tersedia" if claim_count else "Tidak tersedia",
    }


def _build_completeness_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_flag_df()
    rows = []
    for _, claim in df.iterrows():
        missing_dx = not codes_are_present(claim.get("DIAGLIST"))
        missing_px = not codes_are_present(claim.get("PROCLIST"))
        if not missing_dx and not missing_px:
            continue
        notes = []
        if missing_dx:
            notes.append("Diagnosis kosong")
        if missing_px:
            notes.append("Tindakan kosong; pastikan sesuai pelayanan, bukan otomatis kesalahan coding")
        rows.append(_flag_row(claim, catatan="; ".join(notes)))
    return _to_flag_df(rows)


def _build_severity_high_los_low_df(ri: pd.DataFrame) -> pd.DataFrame:
    if ri.empty:
        return _empty_flag_df()
    rows = []
    for _, claim in ri.iterrows():
        severity = claim.get("_severity")
        los = claim.get("_los_num")
        if pd.isna(severity) or pd.isna(los):
            continue
        if severity > 1 and los < 5:
            rows.append(
                _flag_row(
                    claim,
                    catatan="Severity > 1 dengan LOS < 5 hari",
                )
            )
    return _to_flag_df(rows)


def _build_severity_low_los_high_df(ri: pd.DataFrame) -> pd.DataFrame:
    if ri.empty:
        return _empty_flag_df()
    rows = []
    for _, claim in ri.iterrows():
        severity = claim.get("_severity")
        los = claim.get("_los_num")
        if pd.isna(severity) or pd.isna(los):
            continue
        if severity == 1 and los > 5:
            rows.append(
                _flag_row(
                    claim,
                    catatan="Severity 1 dengan LOS > 5 hari",
                )
            )
    return _to_flag_df(rows)


def _build_intensive_care_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_flag_df()
    rows = []
    for _, claim in df.iterrows():
        icu_flag = _as_number(claim.get("_icu_indikator_num", claim.get("ICU_INDIKATOR"))) == 1
        icu_los = _as_number(claim.get("_icu_los_num", claim.get("ICU_LOS"))) or 0
        rawat_intensif = _as_number(claim.get("_rawat_intensif_num", claim.get("RAWAT_INTENSIF"))) or 0
        if icu_flag or icu_los > 0 or rawat_intensif > 0:
            rows.append(_flag_row(claim, catatan="Pasien rawat intensif terdeteksi"))
    return _to_flag_df(rows)


def _build_grouper_gt_rs_df(df: pd.DataFrame) -> pd.DataFrame:
    return _tariff_flags(df, gap=False)


def _build_selisih_gt_30pct_df(df: pd.DataFrame) -> pd.DataFrame:
    return _tariff_flags(df, gap=True)


def _build_dpjp_summary_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["DPJP", "Jumlah Klaim"])
    rows = []
    for name, claims in df.groupby("_dpjp_normalized", dropna=False):
        tariffs = _tariff_metrics(claims)
        complete = tariffs["Pasangan RS - INA-CBG"] == len(claims)
        rows.append({"DPJP": name or "DPJP kosong", **_activity_metrics(claims), **tariffs,
                     **_cmi_for_frame(claims), "Pangsa Klaim (%)": _percent(len(claims), len(df)),
                     "Total Tarif Grouper": tariffs["Total Tarif INA-CBG"],
                     "Selisih Rp": tariffs["Selisih RS - INA-CBG"] if complete else "",
                     "Selisih %": tariffs["Selisih RS - INA-CBG (%)"] if complete else ""})
    return pd.DataFrame(rows).sort_values(["Jumlah Klaim", "DPJP"], ascending=[False, True]).reset_index(drop=True)


def _build_top_codes_df(df: pd.DataFrame, *, code_column: str, label: str) -> pd.DataFrame:
    columns = ["Kode", "Jenis kode", "Frekuensi", "Jumlah Klaim", "Prevalensi (%)"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    counter: dict[str, int] = {}
    claims: dict[str, int] = {}
    for value in df[code_column].tolist():
        for code in split_codes(value):
            counter[code] = counter.get(code, 0) + 1
        for code in set(split_codes(value)):
            claims[code] = claims.get(code, 0) + 1

    if not counter:
        return pd.DataFrame(columns=columns)

    rows = [
        {"Kode": code, "Jenis kode": label, "Frekuensi": count,
         "Jumlah Klaim": claims[code], "Prevalensi (%)": _percent(claims[code], len(df))}
        for code, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:30]
    ]
    return pd.DataFrame(rows, columns=columns)


def _flag_row(claim: pd.Series, *, catatan: str) -> dict[str, object]:
    total_tarif = claim.get("_total_tarif_num")
    tarif_rs = claim.get("_tarif_rs_num")
    selisih_rp = claim.get("_selisih_rp")
    selisih_pct = claim.get("_selisih_pct")
    return {
        "Sumber": claim.get("_source", ""),
        "Baris": claim.get("_row_number", ""),
        "SEP": claim.get("SEP", ""),
        "NAMA_PASIEN": claim.get("NAMA_PASIEN", ""),
        "MRN": claim.get("MRN", ""),
        "PTD": claim.get("_ptd", claim.get("PTD", "")),
        "INACBG": claim.get("INACBG", ""),
        "Severity": _clean_number(claim.get("_severity")),
        "LOS": _clean_number(claim.get("_los_num"), integer=True),
        "DIAGLIST": claim.get("DIAGLIST", ""),
        "PROCLIST": claim.get("PROCLIST", ""),
        "TOTAL_TARIF": _clean_number(total_tarif, integer=True),
        "TARIF_RS": _clean_number(tarif_rs, integer=True),
        "Tarif iDRG": _clean_number(claim.get("_idrg_total_tarif"), integer=True),
        "Basis Tarif": "INA-CBG",
        "Selisih_Rp": _clean_number(selisih_rp, integer=True),
        "Selisih_Pct": _clean_number(selisih_pct, decimals=2),
        "DPJP": claim.get("DPJP", ""),
        "Catatan": catatan,
    }


def _to_flag_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return _empty_flag_df()
    return pd.DataFrame(rows, columns=FLAG_COLUMNS)


def _empty_flag_df() -> pd.DataFrame:
    return pd.DataFrame(columns=FLAG_COLUMNS)


def _as_number(value: object) -> float | None:
    if value is None or value == "" or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_number(value: object, *, integer: bool = False, decimals: int = 2):
    if value is None or pd.isna(value):
        return ""
    return int(value) if integer and float(value).is_integer() else round(float(value), decimals)


def _selisih_pct(row: pd.Series) -> float | None:
    tarif_rs = row.get("_tarif_rs_num")
    if pd.isna(tarif_rs) or tarif_rs <= 0:
        return None
    selisih = row.get("_selisih_rp")
    if pd.isna(selisih):
        return None
    return (selisih / tarif_rs) * 100


def _severity_from_column(value: object) -> int | None:
    from src.parser_eklaim_txt import parse_inacbg_severity

    return parse_inacbg_severity(value)


def _numbers(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df.get(column, pd.Series(float("nan"), index=df.index)), errors="coerce")


def _sum(values: pd.Series) -> float | None:
    valid = values.dropna()
    return fsum(valid) if len(valid) else None


def _percent(numerator: float, denominator: float) -> float | None:
    return numerator * 100 / denominator if denominator > 0 else None


def _text(value: object) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _date(value: object):
    text = _text(value)
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return pd.Timestamp(datetime.strptime(text, pattern))
        except ValueError:
            pass
    return pd.NaT


def _enrich_claims(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    if "_source" not in df:
        df["_source"] = "TXT"
    if "_row_number" not in df:
        df["_row_number"] = range(2, len(df) + 2)
    for column in ("_idrg_total_tarif", "_idrg_cost_weight", "_idrg_total_cost_weight"):
        df[column] = _numbers(df, column)
    for raw, parsed in (("ADMISSION_DATE", "_admitted"), ("DISCHARGE_DATE", "_discharged")):
        df[parsed] = pd.to_datetime(df.get(raw, pd.Series("", index=df.index)).map(_date), errors="coerce")
    df["_date_order_valid"] = df["_admitted"].isna() | df["_discharged"].isna() | df["_discharged"].ge(df["_admitted"])
    for prefix, fields in (("idrg", ("_idrg_grouper_version", "_idrg_logic_version")),
                           ("ina", ("VERSI_GROUPER", "VERSI_INACBG"))):
        df[f"_{prefix}_version"] = df.apply(
            lambda row: " / ".join(_text(row.get(c)) or "Tidak tersedia" for c in fields), axis=1)
    # ponytail: satu skema identitas per batch; perlu master pasien untuk menghubungkan skema berbeda.
    identity = "NOKARTU" if "NOKARTU" in df and df["NOKARTU"].map(_text).ne("").any() else "MRN"
    df["_patient_key"] = df.get(identity, pd.Series("", index=df.index)).map(_text)
    df["_patient_basis"] = identity
    positive = (_numbers(df, "_icu_indikator_num").eq(1) | _numbers(df, "_icu_los_num").gt(0)
                | _numbers(df, "_rawat_intensif_num").gt(0))
    known = positive | pd.concat([_numbers(df, c).eq(0) for c in
                                 ("_icu_indikator_num", "_icu_los_num", "_rawat_intensif_num")], axis=1).all(axis=1)
    df["_icu_status"] = positive.astype(float).where(known)
    return df


def _review_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df.reindex(columns=["_source", "_row_number", "SEP", "NAMA_PASIEN", "MRN", "PTD"]).rename(
        columns={"_source": "Sumber", "_row_number": "Baris"}).copy()


def _select_claims(df: pd.DataFrame):
    duplicates = _review_rows(df)
    duplicates["Catatan"] = ""
    if df.empty:
        return df, duplicates, duplicates.copy(), {"Salinan Duplikat Identik": 0, "SEP Konflik": 0}
    reasons = pd.Series("", index=df.index)
    reasons.loc[~df["_sep_valid"]] = "SEP kosong/tidak valid"
    bad_ptd = ~df["_ptd"].isin(CARE_TYPES)
    reasons.loc[bad_ptd] += "; PTD bukan 1/2"
    repeated = df["_sep_valid"] & df["_sep_normalized"].duplicated(keep=False)
    raw_columns = [c for c in df.columns if not c.startswith("_")]
    duplicate_notes = pd.Series("", index=df.index)
    copies = conflicts = 0
    for _, group in df.loc[repeated].groupby("_sep_normalized", sort=False):
        rows = group[raw_columns].fillna("").astype(str)
        if len(rows.drop_duplicates()) == 1:
            duplicate_notes.loc[group.index[0]] = "Duplikat identik; baris pertama dipakai"
            duplicate_notes.loc[group.index[1:]] = "Duplikat identik; salinan dikecualikan"
            reasons.loc[group.index[1:]] += "; Salinan duplikat identik"
            copies += len(group) - 1
        else:
            fields = ", ".join(column for column in raw_columns if rows[column].nunique(dropna=False) > 1)
            duplicate_notes.loc[group.index] = f"Konflik SEP ({fields}); seluruh baris dikecualikan sampai dikoreksi"
            reasons.loc[group.index] += "; Konflik SEP"
            conflicts += 1
    duplicates = _review_rows(df.loc[repeated])
    duplicates["Catatan"] = duplicate_notes.loc[repeated]
    excluded = reasons.ne("")
    quarantine = _review_rows(df.loc[excluded])
    quarantine["Catatan"] = reasons.loc[excluded].str.strip("; ")
    return df.loc[~excluded].copy(), duplicates, quarantine, {"Salinan Duplikat Identik": copies, "SEP Konflik": conflicts}


def _validate_claims(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["Sumber", "Baris", "SEP", "Field", "Nilai", "Masalah"]
    issues = []
    for _, row in df.iterrows():
        def issue(field, problem, value=None):
            issues.append({"Sumber": row["_source"], "Baris": row["_row_number"], "SEP": row["SEP"],
                           "Field": field, "Nilai": _text(row.get(field)) if value is None else value, "Masalah": problem})
        for name in ("MRN", "DPJP", "NOKARTU"):
            if name in df and not _text(row.get(name)):
                issue(name, "Kosong")
        for raw, parsed in (("ADMISSION_DATE", "_admitted"), ("DISCHARGE_DATE", "_discharged")):
            if raw in df and pd.isna(row[parsed]):
                issue(raw, "Kosong" if not _text(row[raw]) else "Format tanggal tidak valid")
        admitted, discharged = row["_admitted"], row["_discharged"]
        los = row.get("_los_num")
        if pd.notna(admitted) and pd.notna(discharged):
            if discharged < admitted:
                issue("DISCHARGE_DATE", "Tanggal pulang mendahului tanggal masuk")
            elif pd.notna(los) and los != (discharged.date() - admitted.date()).days + 1:
                issue("LOS", "Berbeda dari selisih tanggal + 1; konfirmasi definisi LOS ekspor")
        icu_los = row.get("_icu_los_num")
        if pd.notna(icu_los) and pd.notna(los) and icu_los > los:
            issue("ICU_LOS", "Melebihi LOS; konfirmasi satuan dan pencatatan")
        if row.get("_icu_indikator_num") == 0 and pd.notna(icu_los) and icu_los > 0:
            issue("ICU_INDIKATOR", "Bernilai 0 tetapi ICU_LOS positif")
        if row.get("_icu_status") == 1 and row.get("_rawat_intensif_num") == 0:
            issue("RAWAT_INTENSIF", "Tarif intensif nol pada episode ICU; telaah alokasi tarif")
        if _text(row.get("_c2_status")) not in ("", "valid"):
            issue("C2", f"Status iDRG: {row['_c2_status']}", "")
        for problem in row.get("_c2_issues", []) if isinstance(row.get("_c2_issues"), list) else []:
            issue("C2.idrg", problem, "")
        if pd.isna(row.get("_severity")):
            issue("INACBG", "Severity INA-CBG tidak dikenali")
        for raw in ("DIAGLIST", "PROCLIST"):
            codes = split_codes(row.get(raw))
            if len(codes) != len(set(codes)):
                issue(raw, "Kode berulang dalam satu klaim; prevalensi dihitung sekali")
        for parts, target in ((TARIFF_COMPONENTS, "TARIF_RS"),
                              (["TARIF_INACBG", "TARIF_SUBACUTE", "TARIF_CHRONIC", "TARIF_SP", "TARIF_SR", "TARIF_SI", "TARIF_SD"], "TOTAL_TARIF")):
            values = [row.get(f"_{part.lower()}_num") for part in parts]
            total = row.get(f"_{target.lower()}_num")
            if all(pd.notna(value) for value in values) and pd.notna(total) and abs(sum(values) - total) > 0.01:
                issue(target, "Jumlah komponen tarif berbeda dari total")
    return pd.DataFrame(issues, columns=columns)


def _tariff_metrics(df: pd.DataFrame) -> dict[str, object]:
    out = {"Jumlah Klaim": len(df)}
    for label, column in TARIFFS.items():
        values = _numbers(df, column)
        count = int(values.notna().sum())
        out.update({f"Total Tarif {label}": _sum(values), f"Klaim Tarif {label}": count,
                    f"Cakupan Tarif {label} (%)": _percent(count, len(df)),
                    f"Rata-rata Tarif {label}": float(values.mean()) if count else None})
    for left, right in (("RS", "INA-CBG"), ("RS", "iDRG"), ("iDRG", "INA-CBG")):
        label = f"{left} - {right}"
        a, b = _numbers(df, TARIFFS[left]), _numbers(df, TARIFFS[right])
        valid = a.notna() & b.notna()
        difference = _sum(a.loc[valid] - b.loc[valid])
        denominator = _sum((a if left == "RS" else b).loc[valid])
        out.update({f"Pasangan {label}": int(valid.sum()), f"Cakupan Pasangan {label} (%)": _percent(int(valid.sum()), len(df)),
                    f"Selisih {label}": difference,
                    f"{'Selisih' if left == 'RS' else 'Perubahan'} {label} (%)":
                        _percent(difference, denominator) if difference is not None and denominator is not None else None})
    out["Status Tarif"] = "Lengkap" if len(df) and all(out[f"Klaim Tarif {label}"] == len(df) for label in TARIFFS) else "Parsial / tidak tersedia"
    return out


def _activity_metrics(df: pd.DataFrame) -> dict[str, object]:
    patient = df.get("_patient_key", pd.Series(dtype=str))
    patient = patient[patient.ne("")]
    ri = df.loc[df["_ptd"].eq(PTD_RAWAT_INAP)] if not df.empty else df
    los = _numbers(ri, "_los_num").dropna()
    icu = _numbers(df, "_icu_status").dropna()
    icu_los = _numbers(df, "_icu_los_num").dropna()
    vent = _numbers(df, "_vent_hour_num").dropna()
    return {"Jumlah Klaim": len(df), "Pasien Unik": int(patient.nunique()) if len(patient) else None,
            "Dasar Identitas": df["_patient_basis"].iloc[0] if not df.empty else "",
            "Klaim dengan Identitas": len(patient), "Cakupan Identitas (%)": _percent(len(patient), len(df)),
            "Klaim dengan LOS": len(los), "Cakupan LOS RI (%)": _percent(len(los), len(ri)),
            "Total LOS": _sum(los), "ALOS": float(los.mean()) if len(los) else None,
            "Median LOS": float(los.median()) if len(los) else None,
            "P90 LOS": float(los.quantile(0.9)) if len(los) else None,
            "Klaim ICU": int(icu.eq(1).sum()) if len(icu) else None,
            "Klaim dengan Status ICU": len(icu), "Cakupan Status ICU (%)": _percent(len(icu), len(df)),
            "Proporsi ICU (%)": _percent(int(icu.eq(1).sum()), len(icu)),
            "Total ICU LOS": _sum(icu_los), "Klaim dengan ICU LOS": len(icu_los),
            "Median ICU LOS": float(icu_los.loc[icu_los.gt(0)].median()) if icu_los.gt(0).any() else None,
            "Klaim Ventilator": int(vent.gt(0).sum()) if len(vent) else None,
            "Klaim dengan VENT_HOUR": len(vent), "Total VENT_HOUR": _sum(vent)}


def _tariff_flags(df: pd.DataFrame, *, gap: bool) -> pd.DataFrame:
    rows = []
    rs = _numbers(df, "_tarif_rs_num")
    for label in ("INA-CBG", "iDRG"):
        tariff = _numbers(df, TARIFFS[label])
        difference = rs - tariff
        percent = difference.div(rs.where(rs.gt(0))) * 100
        mask = percent.gt(30) if gap else tariff.gt(rs)
        for index, claim in df.loc[mask].iterrows():
            note = f"(Tarif RS - {label}) / Tarif RS > 30%" if gap else f"Tarif {label} lebih besar dari Tarif RS"
            row = _flag_row(claim, catatan=note)
            row.update({"Basis Tarif": label, "Selisih_Rp": _clean_number(difference.loc[index], integer=True),
                        "Selisih_Pct": _clean_number(percent.loc[index])})
            rows.append(row)
    return _to_flag_df(rows)


def _los_profiles(ri: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dimensions = {"DPJP": "_dpjp_normalized", "INA-CBG": "INACBG", "iDRG": "_idrg_drg_code",
                  "Severity INA-CBG": "_severity", "Kelas rawat": "KELAS_RAWAT", "Status pulang (kode)": "DISCHARGE_STATUS"}
    for dimension, column in dimensions.items():
        if column not in ri:
            continue
        for group, claims in ri.groupby(column, dropna=False):
            metrics = _activity_metrics(claims)
            rows.append({"Dimensi": dimension, "Kelompok": _text(group) or "Tidak tersedia",
                         **{key: metrics[key] for key in ("Jumlah Klaim", "Klaim dengan LOS", "Cakupan LOS RI (%)", "Total LOS", "ALOS", "Median LOS", "P90 LOS")}})
    return pd.DataFrame(rows)


def _component_profiles(groups, components, *, inacbg=False) -> pd.DataFrame:
    rows = []
    for label, df in groups:
        rs = _numbers(df, "_total_tarif_num" if inacbg else "_tarif_rs_num")
        los = _numbers(df, "_los_num") if label == "Rawat Inap" else pd.Series(float("nan"), index=df.index)
        for component in components:
            values = _numbers(df, f"_{component.lower()}_num")
            available = values.notna()
            paired = available & rs.notna()
            days = available & los.gt(0)
            denominator = _sum(rs.loc[paired])
            rows.append({"Jenis Rawat": label, "Basis Tarif": "INA-CBG" if inacbg else "RS", "Komponen": component,
                         "Total Tarif Komponen": _sum(values), "Klaim dengan Komponen": int(available.sum()),
                         "Cakupan Komponen (%)": _percent(int(available.sum()), len(df)),
                         "Pasangan Komponen - Total": int(paired.sum()),
                         f"Porsi Tarif {'INA-CBG' if inacbg else 'RS'} (%)":
                             _percent(_sum(values.loc[paired]), denominator) if denominator is not None else None,
                         "Tarif Komponen per Klaim": float(values.mean()) if available.any() else None,
                         "Pasangan Komponen - LOS": int(days.sum()),
                         "Tarif Komponen per Hari": float(values.loc[days].sum() / los.loc[days].sum()) if days.any() else None})
    return pd.DataFrame(rows)


def _casemix_profiles(groups) -> pd.DataFrame:
    rows = []
    for label, df in groups:
        for system, column, version in (("INA-CBG", "INACBG", "_ina_version"),
                                         ("iDRG", "_idrg_drg_code", "_idrg_version"),
                                         ("Severity INA-CBG", "_severity", "_ina_version"),
                                         ("Kelas rawat", "KELAS_RAWAT", "_ina_version")):
            if df.empty or column not in df:
                continue
            for (code, version_name), claims in df.groupby([column, version], dropna=False):
                rows.append({"Jenis Rawat": label, "Sistem": system, "Kode": _text(code) or "Tidak tersedia",
                             "Versi Grouper": version_name, "Pangsa Klaim (%)": _percent(len(claims), len(df)),
                             **_tariff_metrics(claims), **_activity_metrics(claims), **_cmi_for_frame(claims)})
    return pd.DataFrame(rows)


def _outpatient_visits(rj: pd.DataFrame) -> pd.DataFrame:
    patient = rj.get("_patient_key", pd.Series(dtype=str))
    counts = patient.loc[patient.ne("")].value_counts()
    return pd.DataFrame([{"Jumlah Klaim": len(rj), "Klaim dengan Identitas": int(counts.sum()),
                          "Dasar Identitas": rj["_patient_basis"].iloc[0] if not rj.empty else "",
                          "Pasien Unik": len(counts) if len(counts) else None,
                          "Pasien Kunjungan Berulang": int(counts.gt(1).sum()) if len(counts) else None,
                          "Kunjungan per Pasien": float(counts.sum() / len(counts)) if len(counts) else None,
                          "Cakupan Identitas (%)": _percent(int(counts.sum()), len(rj))}])


def _service_days(groups) -> pd.DataFrame:
    rows = []
    for label, df in groups:
        if df.empty:
            continue
        column = "_admitted" if label == "Rawat Jalan" else "_discharged"
        for date, claims in df.loc[df[column].notna() & df["_date_order_valid"]].groupby(df[column].dt.date):
            rows.append({"Jenis Rawat": label, "Tanggal": date.isoformat(),
                         "Dasar Tanggal": "Tanggal masuk" if label == "Rawat Jalan" else "Tanggal pulang",
                         **_tariff_metrics(claims), **_activity_metrics(claims)})
    return pd.DataFrame(rows)


def _period_activity(groups) -> pd.DataFrame:
    rows = []
    for label, df in groups:
        if df.empty:
            continue
        column = "_admitted" if label == "Rawat Jalan" else "_discharged"
        previous_period = None
        previous_count = 0
        for period, claims in df.loc[df[column].notna() & df["_date_order_valid"]].groupby(df[column].dt.to_period("M")):
            consecutive = previous_period is not None and period.ordinal == previous_period.ordinal + 1
            rows.append({"Jenis Rawat": label, "Periode": str(period),
                         "Dasar Tanggal": "Tanggal masuk" if label == "Rawat Jalan" else "Tanggal pulang",
                         **_tariff_metrics(claims), **_activity_metrics(claims),
                         "Perubahan Klaim (%)": _percent(len(claims) - previous_count, previous_count) if consecutive else None,
                         "Keterangan Periode": "Dibanding bulan sebelumnya dalam file" if consecutive else "Tidak ada bulan sebelumnya yang berurutan"})
            previous_period, previous_count = period, len(claims)
    return pd.DataFrame(rows)


def _discharge_status(groups) -> pd.DataFrame:
    rows = []
    for label, df in groups:
        if df.empty:
            continue
        status = df.get("DISCHARGE_STATUS", pd.Series("", index=df.index)).map(_text).replace("", "Tidak tersedia")
        for code, count in status.value_counts().items():
            rows.append({"Jenis Rawat": label, "Kode Status Pulang": code, "Jumlah Klaim": int(count),
                         "Pangsa Klaim (%)": _percent(int(count), len(df))})
    return pd.DataFrame(rows)


def _metadata(all_claims: pd.DataFrame, eligible: pd.DataFrame) -> pd.DataFrame:
    rows = [{"Metrik": "Waktu proses", "Nilai": datetime.now().astimezone().isoformat(timespec="seconds")},
            {"Metrik": "Populasi", "Nilai": "Hanya file yang diunggah; bukan bukti cakupan seluruh pelayanan RS"},
            {"Metrik": "Baris masuk", "Nilai": len(all_claims)},
            {"Metrik": "Klaim dianalisis", "Nilai": len(eligible)},
            {"Metrik": "Baris dikecualikan", "Nilai": len(all_claims) - len(eligible)}]
    if not all_claims.empty:
        for source, claims in all_claims.groupby("_source", dropna=False):
            rows.append({"Metrik": f"Sumber: {source}", "Nilai": f"{len(claims)} baris; nomor baris merujuk file asli"})
        for ptd, label in CARE_TYPES.items():
            frame = eligible.loc[eligible["_ptd"].eq(ptd)]
            rows.append({"Metrik": f"{label}: dasar identitas", "Nilai": frame["_patient_basis"].iloc[0] if len(frame) else "Tidak tersedia"})
            for raw, column in (("Tanggal masuk", "_admitted"), ("Tanggal pulang", "_discharged")):
                valid = frame.loc[frame["_date_order_valid"], column].dropna()
                period = f"{valid.min().date()} s.d. {valid.max().date()}" if len(valid) else "Tidak tersedia"
                rows.append({"Metrik": f"{label}: {raw}", "Nilai": f"{period}; {len(valid)}/{len(frame)} tanggal valid"})
            for prefix in ("ina", "idrg"):
                versions = sorted(frame[f"_{prefix}_version"].unique())
                rows.append({"Metrik": f"{label}: versi {prefix}", "Nilai": "; ".join(versions) or "Tidak tersedia"})
        absent = [c for c in ["ADMISSION_DATE", "DISCHARGE_DATE", "DISCHARGE_STATUS", *TARIFF_COMPONENTS] if c not in all_claims]
        if absent:
            rows.append({"Metrik": "Kolom opsional tidak tersedia", "Nilai": ", ".join(absent)})
    return pd.DataFrame(rows)


def _methodology() -> pd.DataFrame:
    return pd.DataFrame([
        ("Populasi KPI", "SEP dan PTD valid. Duplikat identik dihitung sekali; semua baris SEP konflik dikarantina. Temuan antarbagian dapat tumpang tindih."),
        ("Tarif", "INA-CBG memakai TOTAL_TARIF; iDRG memakai C2.idrg.total_tarif; RS memakai TARIF_RS. Nilai file bukan bukti pembayaran, biaya aktual, atau laba/rugi."),
        ("Subtotal dan cakupan", "Total tarif adalah jumlah nilai valid; cakupan <100% berarti subtotal parsial. Kosong/tidak valid tidak diubah menjadi nol."),
        ("Selisih RS - grouper", "Jumlah (RS - grouper) dari pasangan valid; persen = jumlah selisih / jumlah RS pasangan itu x 100. Tarif RS nol tidak memiliki persen per klaim. Tabel menampilkan jumlah dan cakupan pasangan."),
        ("Perubahan iDRG - INA-CBG", "Jumlah (iDRG - INA-CBG) dari pasangan valid; persen dibagi jumlah INA-CBG pada pasangan yang sama. Penyebut nol berarti tidak tersedia."),
        ("CMI iDRG", "Rata-rata cost_weight valid; jumlah klaim berbobot dan cakupan ditampilkan. Tanpa bobot valid atau versi iDRG berbeda, CMI tidak tersedia; profil kasus dipisah per versi."),
        ("Bobot lain", "Rata-rata total_cost_weight ditampilkan terpisah dan tidak disebut CMI resmi. CMI INA-CBG tidak tersedia tanpa referensi bobot INA-CBG. CMI RI/RJ tidak otomatis sebanding."),
        ("Aktivitas DPJP", "Episode unik, pasien unik, tarif, LOS dan bobot dari klaim yang memenuhi syarat. Nama dinormalisasi kapital/spasi tanpa penggabungan samar. Produktivitas per jam/FTE memerlukan jadwal kerja."),
        ("Identitas pasien", "Gunakan NOKARTU jika tersedia pada batch, selain itu MRN. Identitas kosong dikecualikan dari jumlah pasien; tidak ditebak dari nama. Pasien unik per DPJP tidak bersifat aditif."),
        ("LOS", "ALOS = total field LOS valid / episode RI dengan LOS valid; median/P90 memakai populasi sama. LOS tetap nilai ekspor; perbedaan dengan selisih tanggal + 1 perlu telaah dan tidak dikoreksi otomatis."),
        ("Penapisan severity", "Severity berasal dari suffix INA-CBG. Severity >1 dengan LOS <5 atau severity I dengan LOS >5 hanya penanda telaah, bukan bukti salah coding/inefisiensi."),
        ("Komponen tarif", "Porsi komponen = jumlah komponen / total tarif pada pasangan valid. Per klaim dibagi klaim dengan komponen valid; per hari dibagi total LOS RI positif pada pasangan komponen-LOS. Bukan biaya aktual."),
        ("ICU dan ventilator", "ICU positif bila indikator=1, ICU_LOS>0, atau tarif intensif>0. Negatif diketahui jika ketiganya nol; selain itu status tidak tersedia. Proporsi memakai episode dengan status diketahui. Median ICU_LOS memakai nilai >0. VENT_HOUR hanya tersedia jika field valid."),
        ("Kode dan status pulang", "Top ICD menghitung semua kode tanpa mengasumsikan diagnosis utama. Frekuensi adalah kemunculan; jumlah klaim/prevalensi menghitung kode sekali per episode. Status pulang ditampilkan sebagai kode asli, tanpa asumsi mortalitas."),
        ("Pola waktu", "RAJAL memakai tanggal masuk; RANAP memakai tanggal pulang. Tanggal tidak valid dikecualikan. Kunjungan berulang dalam batch bukan readmission terverifikasi; hari dengan klaim bukan seluruh hari kerja."),
        ("Perubahan bulanan", "Perubahan klaim hanya dihitung untuk bulan kalender berurutan dalam file: (N bulan ini - N bulan lalu) / N bulan lalu x 100. Kelengkapan bulan tidak dijamin; bulan tanpa baris bukan otomatis nol aktivitas."),
        ("Data tambahan diperlukan", "BOR/BTO/TOI perlu kapasitas tempat tidur dan sensus lengkap; indeks efisiensi LOS perlu LOS harapan per kasus; margin perlu biaya aktual dan pendapatan; readmission perlu episode lintas periode; indikator mutu perlu definisi status dan penyesuaian risiko."),
    ], columns=["Indikator", "Definisi dan batas penggunaan"])
