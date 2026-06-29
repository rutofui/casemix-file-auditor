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


def build_eklaim_analysis(
    ri_df: pd.DataFrame,
    rj_df: pd.DataFrame,
) -> EklaimAnalysisResult:
    ri = _prepare_claims(ri_df, PTD_RAWAT_INAP)
    rj = _prepare_claims(rj_df, PTD_RAWAT_JALAN)
    combined = pd.concat([ri, rj], ignore_index=True) if not ri.empty or not rj.empty else pd.DataFrame()

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


def _build_summary(ri: pd.DataFrame, rj: pd.DataFrame, combined: pd.DataFrame) -> dict[str, object]:
    total_ri = int(len(ri))
    total_rj = int(len(rj))
    total_all = int(len(combined))
    total_tarif = float(combined["_total_tarif_num"].fillna(0).sum()) if not combined.empty else 0.0
    total_rs = float(combined["_tarif_rs_num"].fillna(0).sum()) if not combined.empty else 0.0
    return {
        "Total Klaim Rawat Jalan": total_rj,
        "Total Klaim Rawat Inap": total_ri,
        "Total Klaim Keseluruhan": total_all,
        "Total Tarif Grouper (TOTAL_TARIF)": int(total_tarif),
        "Total Tarif RS": int(total_rs),
        "Selisih Total Tarif RS - Grouper": int(total_rs - total_tarif),
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
        if severity is None or los is None:
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
        if severity is None or los is None:
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
        if total_tarif is None or tarif_rs is None:
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
        if tarif_rs is None or tarif_rs <= 0 or selisih_pct is None:
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
            Total_Tarif_Grouper=("_total_tarif_num", "sum"),
            Total_Tarif_RS=("_tarif_rs_num", "sum"),
        )
        .reset_index()
    )
    grouped["Selisih Rp"] = grouped["Total_Tarif_RS"] - grouped["Total_Tarif_Grouper"]
    grouped["Selisih %"] = grouped.apply(
        lambda row: round((row["Selisih Rp"] / row["Total_Tarif_RS"]) * 100, 2)
        if row["Total_Tarif_RS"] > 0
        else 0.0,
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
    grouped["Total Tarif Grouper"] = grouped["Total Tarif Grouper"].fillna(0).astype(int)
    grouped["Total Tarif RS"] = grouped["Total Tarif RS"].fillna(0).astype(int)
    grouped["Selisih Rp"] = grouped["Selisih Rp"].fillna(0).astype(int)
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
        "Severity": claim.get("_severity"),
        "LOS": int(claim.get("_los_num")) if claim.get("_los_num") is not None else "",
        "DIAGLIST": claim.get("DIAGLIST", ""),
        "PROCLIST": claim.get("PROCLIST", ""),
        "TOTAL_TARIF": int(total_tarif) if total_tarif is not None else "",
        "TARIF_RS": int(tarif_rs) if tarif_rs is not None else "",
        "Selisih_Rp": int(selisih_rp) if selisih_rp is not None else "",
        "Selisih_Pct": round(selisih_pct, 2) if selisih_pct is not None else "",
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
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _selisih_pct(row: pd.Series) -> float | None:
    tarif_rs = row.get("_tarif_rs_num")
    if tarif_rs is None or tarif_rs <= 0:
        return None
    selisih = row.get("_selisih_rp")
    if selisih is None:
        return None
    return (selisih / tarif_rs) * 100


def _severity_from_column(value: object) -> int | None:
    from src.parser_eklaim_txt import parse_inacbg_severity

    return parse_inacbg_severity(value)
