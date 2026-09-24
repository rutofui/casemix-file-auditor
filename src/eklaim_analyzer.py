from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.parser_eklaim_txt import PTD_RAWAT_INAP, PTD_RAWAT_JALAN, codes_are_present, split_codes

FLAG_COLUMNS = [
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
    warnings: list[str] = field(default_factory=list)


def build_eklaim_analysis(
    ri_df: pd.DataFrame,
    rj_df: pd.DataFrame,
) -> EklaimAnalysisResult:
    input_frames = [df for df in (ri_df, rj_df) if df is not None and not df.empty]
    all_claims = pd.concat(input_frames, ignore_index=True) if input_frames else pd.DataFrame()
    if not all_claims.empty and "_ptd" in all_claims:
        invalid_ptd = all_claims.loc[~all_claims["_ptd"].isin([PTD_RAWAT_INAP, PTD_RAWAT_JALAN])].copy()
        ri = _prepare_claims(all_claims.loc[all_claims["_ptd"] == PTD_RAWAT_INAP], PTD_RAWAT_INAP)
        rj = _prepare_claims(all_claims.loc[all_claims["_ptd"] == PTD_RAWAT_JALAN], PTD_RAWAT_JALAN)
    else:
        invalid_ptd = pd.DataFrame()
        ri = _prepare_claims(ri_df, PTD_RAWAT_INAP)
        rj = _prepare_claims(rj_df, PTD_RAWAT_JALAN)
    combined = pd.concat([ri, rj], ignore_index=True) if not ri.empty or not rj.empty else pd.DataFrame()
    data_quality, invalid_numeric = _data_quality(all_claims)
    warnings = []
    if not combined.empty and (combined[["_total_tarif_num", "_tarif_rs_num"]].isna().any().any()):
        warnings.append("Total tarif bersifat parsial karena ada nilai TOTAL_TARIF atau TARIF_RS kosong/tidak valid; selisih total dan agregat DPJP terkait dikosongkan.")

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
    numeric = {"TOTAL_TARIF": "_total_tarif_num", "TARIF_RS": "_tarif_rs_num", "LOS": "_los_num",
               "ICU_INDIKATOR": "_icu_indikator_num", "ICU_LOS": "_icu_los_num", "RAWAT_INTENSIF": "_rawat_intensif_num"}
    issues = []
    for field, parsed in numeric.items():
        if parsed not in df:
            continue
        raw = df[field].astype(str).str.strip() if field in df else pd.Series("", index=df.index)
        missing = raw.isin(["", "-", "nan", "None"])
        invalid = ~missing & df[parsed].isna()
        for index in df.index[missing | invalid]:
            issues.append({"SEP": df.at[index, "SEP"], "Field": field, "Nilai": raw.at[index],
                           "Masalah": "Kosong" if missing.at[index] else "Format tidak valid"})
    coverage_n = int(df["_idrg_cost_weight"].notna().sum())
    count = len(df)
    detail = pd.DataFrame(issues, columns=["SEP", "Field", "Nilai", "Masalah"])
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
    out = df[[c for c in ("SEP", "NAMA_PASIEN", "MRN", "PTD") if c in df]].copy()
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
    }


def _build_casemix_index(ri: pd.DataFrame, rj: pd.DataFrame) -> dict[str, object]:
    return {
        "Rawat Inap": _cmi_for_frame(ri),
        "Rawat Jalan": _cmi_for_frame(rj),
    }


def _cmi_for_frame(df: pd.DataFrame) -> dict[str, object]:
    if df.empty:
        return {"Jumlah Klaim": 0, "Total Cost Weight": 0.0, "Casemix Index": 0.0, "Tanpa Cost Weight": 0}
    weights = df["_idrg_cost_weight"].dropna()
    missing = int(df["_idrg_cost_weight"].isna().sum())
    claim_count = int(len(weights))
    total_weight = float(weights.sum()) if claim_count else 0.0
    cmi = total_weight / claim_count if claim_count else 0.0
    return {
        "Jumlah Klaim": claim_count,
        "Total Cost Weight": round(total_weight, 4),
        "Casemix Index": round(cmi, 4),
        "Tanpa Cost Weight": missing,
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
            notes.append("Tindakan kosong")
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
    if df.empty:
        return _empty_flag_df()
    rows = []
    for _, claim in df.iterrows():
        total_tarif = claim.get("_total_tarif_num")
        tarif_rs = claim.get("_tarif_rs_num")
        if pd.isna(total_tarif) or pd.isna(tarif_rs):
            continue
        if total_tarif > tarif_rs:
            rows.append(_flag_row(claim, catatan="TOTAL_TARIF lebih besar dari TARIF_RS"))
    return _to_flag_df(rows)


def _build_selisih_gt_30pct_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_flag_df()
    rows = []
    for _, claim in df.iterrows():
        tarif_rs = claim.get("_tarif_rs_num")
        selisih_pct = claim.get("_selisih_pct")
        if pd.isna(tarif_rs) or tarif_rs <= 0 or pd.isna(selisih_pct):
            continue
        if selisih_pct > 30:
            rows.append(_flag_row(claim, catatan="Selisih tarif RS - grouper > 30%"))
    return _to_flag_df(rows)


def _build_dpjp_summary_df(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "DPJP",
        "Jumlah Klaim",
        "Total Tarif Grouper",
        "Total Tarif RS",
        "Selisih Rp",
        "Selisih %",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        df.groupby("_dpjp_normalized", dropna=False)
        .agg(
            Jumlah_Klaim=("SEP", "count"),
            Total_Tarif_Grouper=("_total_tarif_num", lambda values: values.sum(min_count=1)),
            Total_Tarif_RS=("_tarif_rs_num", lambda values: values.sum(min_count=1)),
            Grouper_Lengkap=("_total_tarif_num", lambda values: values.notna().all()),
            Tarif_RS_Lengkap=("_tarif_rs_num", lambda values: values.notna().all()),
        )
        .reset_index()
    )
    complete = grouped["Grouper_Lengkap"] & grouped["Tarif_RS_Lengkap"]
    grouped["Selisih Rp"] = (grouped["Total_Tarif_RS"] - grouped["Total_Tarif_Grouper"]).where(complete)
    grouped["Selisih %"] = grouped.apply(
        lambda row: round((row["Selisih Rp"] / row["Total_Tarif_RS"]) * 100, 2)
        if pd.notna(row["Selisih Rp"]) and row["Total_Tarif_RS"] > 0
        else None,
        axis=1,
    )
    grouped = grouped.rename(
        columns={
            "_dpjp_normalized": "DPJP",
            "Jumlah_Klaim": "Jumlah Klaim",
            "Total_Tarif_Grouper": "Total Tarif Grouper",
            "Total_Tarif_RS": "Total Tarif RS",
        }
    )
    for column in ("Total Tarif Grouper", "Total Tarif RS", "Selisih Rp"):
        grouped[column] = grouped[column].map(lambda value: _clean_number(value, integer=True))
    grouped.drop(columns=["Grouper_Lengkap", "Tarif_RS_Lengkap"], inplace=True)
    grouped = grouped.sort_values(["Jumlah Klaim", "DPJP"], ascending=[False, True])
    return grouped.reset_index(drop=True)


def _build_top_codes_df(df: pd.DataFrame, *, code_column: str, label: str) -> pd.DataFrame:
    columns = ["Kode", "Deskripsi", "Frekuensi"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    counter: dict[str, int] = {}
    for value in df[code_column].tolist():
        for code in split_codes(value):
            counter[code] = counter.get(code, 0) + 1

    if not counter:
        return pd.DataFrame(columns=columns)

    rows = [
        {"Kode": code, "Deskripsi": label, "Frekuensi": count}
        for code, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:30]
    ]
    return pd.DataFrame(rows, columns=columns)


def _flag_row(claim: pd.Series, *, catatan: str) -> dict[str, object]:
    total_tarif = claim.get("_total_tarif_num")
    tarif_rs = claim.get("_tarif_rs_num")
    selisih_rp = claim.get("_selisih_rp")
    selisih_pct = claim.get("_selisih_pct")
    return {
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
    return int(value) if integer else round(float(value), decimals)


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
