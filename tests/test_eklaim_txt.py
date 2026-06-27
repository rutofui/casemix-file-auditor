from __future__ import annotations

import io

import pandas as pd
import pytest

from src.eklaim_analyzer import build_eklaim_analysis
from src.parser_eklaim_txt import (
    PTD_RAWAT_INAP,
    PTD_RAWAT_JALAN,
    combine_eklaim_frames,
    extract_idrg_fields,
    parse_c2_json_objects,
    parse_inacbg_severity,
    read_eklaim_txt,
    split_codes,
)


HEADER = "\t".join(
    [
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
)


def _c2_json(cost_weight: str = "0.42", *, with_sitb_prefix: bool = False) -> str:
    claim_json = (
        '{"cara_masuk":"other","idrg":{"cost_weight":"'
        + cost_weight
        + '","total_cost_weight":"'
        + cost_weight
        + '","drg_code":"1667119","total_tarif":"2973712"}}'
    )
    if with_sitb_prefix:
        return '{"sitb_response":{"success":true}}#' + claim_json
    return "prefix###" + claim_json


def _row(
    *,
    sep: str,
    ptd: str,
    inacbg: str,
    diag: str = "A09.9",
    proc: str = "90.59",
    total_tarif: str = "1000000",
    tarif_rs: str = "1500000",
    los: str = "3",
    dpjp: str = "dr. Contoh",
    icu_ind: str = "0",
    icu_los: str = "0",
    rawat_intensif: str = "0",
    c2: str | None = None,
    name: str = "PASIEN A",
    mrn: str = "RM001",
) -> str:
    return "\t".join(
        [
            sep,
            ptd,
            inacbg,
            diag,
            proc,
            total_tarif,
            tarif_rs,
            los,
            dpjp,
            c2 or _c2_json(),
            name,
            mrn,
            icu_ind,
            icu_los,
            rawat_intensif,
        ]
    )


def _txt_content(*rows: str) -> io.BytesIO:
    content = HEADER + "\n" + "\n".join(rows)
    return io.BytesIO(content.encode("utf-8"))


def test_parse_inacbg_severity() -> None:
    assert parse_inacbg_severity("K-4-17-I") == 1
    assert parse_inacbg_severity("J-1-20-III") == 3
    assert parse_inacbg_severity("A-4-14-II") == 2
    assert parse_inacbg_severity("Q-5-44-0") == 0


def test_parse_c2_json_objects_supports_multi_json() -> None:
    text = '{"sitb_response":{"success":true}}#' + _c2_json("0.55").split("###", 1)[1]
    objects = parse_c2_json_objects(text)
    assert len(objects) == 2
    assert "sitb_response" in objects[0]
    assert extract_idrg_fields(text)["cost_weight"] == 0.55


def test_read_eklaim_txt_parses_numeric_and_idrg_fields() -> None:
    content = _txt_content(
        _row(
            sep="0132R0770626V000010",
            ptd=PTD_RAWAT_INAP,
            inacbg="K-4-17-I",
            c2=_c2_json("0.75"),
        )
    )
    result = read_eklaim_txt(content, expected_ptd=PTD_RAWAT_INAP, source_label="Rawat Inap")
    row = result.df.iloc[0]
    assert row["_total_tarif_num"] == 1_000_000
    assert row["_tarif_rs_num"] == 1_500_000
    assert row["_severity"] == 1
    assert row["_idrg_cost_weight"] == 0.75


def test_build_eklaim_analysis_summary_and_cmi() -> None:
    ri_content = _txt_content(
        _row(
            sep="0132R0770626V000011",
            ptd=PTD_RAWAT_INAP,
            inacbg="K-4-17-I",
            total_tarif="1000000",
            tarif_rs="2000000",
            los="3",
            c2=_c2_json("0.40"),
        ),
        _row(
            sep="0132R0770626V000012",
            ptd=PTD_RAWAT_INAP,
            inacbg="J-1-20-III",
            total_tarif="2000000",
            tarif_rs="1000000",
            los="2",
            c2=_c2_json("0.60"),
        ),
    )
    rj_content = _txt_content(
        _row(
            sep="0132R0770626V000020",
            ptd=PTD_RAWAT_JALAN,
            inacbg="Q-5-44-0",
            total_tarif="500000",
            tarif_rs="300000",
            los="1",
            c2=_c2_json("0.50"),
        )
    )
    ri_df = read_eklaim_txt(ri_content).df
    rj_df = read_eklaim_txt(rj_content).df
    analysis = build_eklaim_analysis(ri_df, rj_df)

    assert analysis.summary["Total Klaim Rawat Inap"] == 2
    assert analysis.summary["Total Klaim Rawat Jalan"] == 1
    assert analysis.summary["Total Klaim Keseluruhan"] == 3
    assert analysis.summary["Selisih Total Tarif RS - Grouper"] == -200_000
    assert analysis.casemix_index["Rawat Inap"]["Casemix Index"] == pytest.approx(0.5)
    assert analysis.casemix_index["Rawat Jalan"]["Casemix Index"] == pytest.approx(0.5)


def test_build_eklaim_analysis_flags() -> None:
    same_tarif = {"total_tarif": "1000000", "tarif_rs": "1000000"}
    ri_content = _txt_content(
        _row(
            sep="0132R0770626V000101",
            ptd=PTD_RAWAT_INAP,
            inacbg="J-1-20-III",
            los="3",
            name="PASIEN SEV HIGH",
            **same_tarif,
        ),
        _row(
            sep="0132R0770626V000102",
            ptd=PTD_RAWAT_INAP,
            inacbg="K-4-17-I",
            los="7",
            name="PASIEN SEV LOW",
            **same_tarif,
        ),
        _row(
            sep="0132R0770626V000103",
            ptd=PTD_RAWAT_INAP,
            inacbg="A-4-14-I",
            los="2",
            diag="-",
            proc="90.59",
            name="PASIEN KURANG DX",
            **same_tarif,
        ),
        _row(
            sep="0132R0770626V000104",
            ptd=PTD_RAWAT_INAP,
            inacbg="A-4-14-I",
            los="2",
            diag="A09.9",
            proc="-",
            name="PASIEN KURANG PX",
            **same_tarif,
        ),
        _row(
            sep="0132R0770626V000105",
            ptd=PTD_RAWAT_INAP,
            inacbg="A-4-14-I",
            los="2",
            total_tarif="2000000",
            tarif_rs="1000000",
            name="PASIEN GROUPER LEBIH",
        ),
        _row(
            sep="0132R0770626V000106",
            ptd=PTD_RAWAT_INAP,
            inacbg="A-4-14-I",
            los="2",
            total_tarif="500000",
            tarif_rs="2000000",
            name="PASIEN SELISIH 30",
        ),
        _row(
            sep="0132R0770626V000107",
            ptd=PTD_RAWAT_INAP,
            inacbg="A-4-14-I",
            los="2",
            icu_ind="1",
            name="PASIEN ICU",
            **same_tarif,
        ),
    )
    ri_df = read_eklaim_txt(ri_content).df
    analysis = build_eklaim_analysis(ri_df, pd.DataFrame())

    assert len(analysis.severity_high_los_low_df) == 1
    assert analysis.severity_high_los_low_df.iloc[0]["NAMA_PASIEN"] == "PASIEN SEV HIGH"
    assert len(analysis.severity_low_los_high_df) == 1
    assert analysis.severity_low_los_high_df.iloc[0]["NAMA_PASIEN"] == "PASIEN SEV LOW"
    assert len(analysis.completeness_df) == 2
    assert len(analysis.grouper_gt_rs_df) == 1
    assert len(analysis.selisih_gt_30pct_df) == 1
    assert len(analysis.intensive_care_df) == 1


def test_split_codes_ignores_empty_values() -> None:
    assert split_codes("A09.9;E86") == ["A09.9", "E86"]
    assert split_codes("-") == []
    assert split_codes("") == []


def test_combine_eklaim_frames_warns_duplicate_sep() -> None:
    ri = read_eklaim_txt(
        _txt_content(_row(sep="0132R0770626V000999", ptd=PTD_RAWAT_INAP, inacbg="K-4-17-I")),
        source_label="RI",
    )
    rj = read_eklaim_txt(
        _txt_content(_row(sep="0132R0770626V000999", ptd=PTD_RAWAT_JALAN, inacbg="Q-5-44-0")),
        source_label="RJ",
    )
    _, _, warnings = combine_eklaim_frames(ri, rj)
    assert any("duplikat" in warning.lower() for warning in warnings)
