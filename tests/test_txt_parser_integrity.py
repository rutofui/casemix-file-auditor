from __future__ import annotations

import io
import csv
from pathlib import Path

import pytest

from src.parser_eklaim_txt import (
    NUMERIC_COLUMNS,
    REQUIRED_COLUMNS,
    TARIFF_COMPONENTS,
    PTD_RAWAT_INAP,
    build_file_review_claims,
    extract_idrg_fields,
    parse_c2_json_objects,
    read_eklaim_txt,
)


def _row(**updates: str) -> list[str]:
    values = {
        "SEP": "0132R0770626V000777",
        "PTD": PTD_RAWAT_INAP,
        "INACBG": "K-4-17-I",
        "DIAGLIST": "A09.9",
        "PROCLIST": "90.59",
        "TOTAL_TARIF": "1000000",
        "TARIF_RS": "1500000",
        "LOS": "3",
        "DPJP": "DR CONTOH",
        "C2": '{"idrg":{"cost_weight":"0.5","total_cost_weight":"0.6","total_tarif":"900000"}}',
        "NAMA_PASIEN": "PASIEN",
        "MRN": "RM1",
        "ICU_INDIKATOR": "0",
        "ICU_LOS": "0",
        "RAWAT_INTENSIF": "0",
    }
    values.update(updates)
    return [values[col] for col in REQUIRED_COLUMNS]


def _txt(row: list[str], header: list[str] | None = None) -> io.BytesIO:
    cols = header or REQUIRED_COLUMNS
    return io.BytesIO(("\t".join(cols) + "\n" + "\t".join(row) + "\n").encode("utf-8-sig"))


@pytest.mark.parametrize("width", [14, 16])
def test_rejects_rows_with_wrong_field_count_without_echoing_row(width: int) -> None:
    row = _row()
    row = row[:width] if width < len(row) else row + ["PRIVATE EXTRA"]
    with pytest.raises(ValueError, match=r"baris 2") as error:
        read_eklaim_txt(io.BytesIO(("\t".join(REQUIRED_COLUMNS) + "\n" + "\t".join(row)).encode()))
    assert "PRIVATE EXTRA" not in str(error.value)


def test_rejects_duplicate_headers_and_keeps_source_in_error() -> None:
    header = REQUIRED_COLUMNS.copy()
    header[-1] = header[0]
    with pytest.raises(ValueError, match="contoh.txt.*duplikat"):
        read_eklaim_txt(io.BytesIO(("\t".join(header) + "\n").encode()), source_label="contoh.txt")


def test_reads_repeated_binary_stream_and_preserves_source_row_metadata() -> None:
    content = io.BytesIO(("\ufeff" + "\t".join(REQUIRED_COLUMNS) + "\n\n" + "\t".join(_row())).encode())
    first = read_eklaim_txt(content, source_label="input.txt").df
    second = read_eklaim_txt(content, source_label="input.txt").df
    assert first.equals(second)
    assert first.iloc[0]["_source"] == "input.txt"
    assert first.iloc[0]["_row_number"] == 3
    assert build_file_review_claims(first).iloc[0]["_row_number"] == 3


def test_tracks_physical_start_line_for_multiline_records_and_accepts_text_stream() -> None:
    rows = _row(C2='{"idrg":{"drg_description":"line one\nline two","cost_weight":"0.5"}}')
    following = _row(SEP="0132R0770626V000778")
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(REQUIRED_COLUMNS)
    writer.writerow(rows)
    writer.writerow(following)
    content = output.getvalue()
    df = read_eklaim_txt(io.StringIO(content)).df
    assert df["_row_number"].tolist() == [2, 4]


def test_path_input_uses_basename_as_source(tmp_path: Path) -> None:
    path = tmp_path / "claims.txt"
    path.write_text("\t".join(REQUIRED_COLUMNS) + "\n" + "\t".join(_row()), encoding="utf-8")
    result = read_eklaim_txt(path)
    assert result.source_label == "claims.txt"
    assert result.df.iloc[0]["_source"] == "claims.txt"


def test_decoder_handles_braces_inside_json_strings_and_extracts_fields_independently() -> None:
    c2 = 'prefix##{"idrg":{"drg_description":"brace } and { text","total_tarif":"900000"}}'
    objects = parse_c2_json_objects(c2)
    fields = extract_idrg_fields(c2)
    assert len(objects) == 1
    assert fields["total_tarif"] == 900000
    assert "cost_weight" not in fields
    row = read_eklaim_txt(_txt(_row(C2=c2))).df.iloc[0]
    assert row["_idrg_total_tarif"] == 900000
    assert row["_c2_status"] == "valid"
    assert "idrg.cost_weight tidak ditemukan" in row["_c2_issues"]


def test_c2_status_distinguishes_missing_invalid_no_idrg_and_valid() -> None:
    rows = [
        _row(C2=""),
        _row(C2="{broken"),
        _row(C2='{"cara_masuk":"other"}'),
        _row(),
    ]
    content = "\t".join(REQUIRED_COLUMNS) + "\n" + "\n".join("\t".join(r) for r in rows)
    df = read_eklaim_txt(io.BytesIO(content.encode())).df
    assert df["_c2_status"].tolist() == ["missing", "invalid", "no-idrg", "valid"]


def test_numeric_domain_validation_covers_money_weights_and_unit_fields() -> None:
    row = _row(TOTAL_TARIF="-10", LOS="2.5", ICU_INDIKATOR="2", ICU_LOS="-1")
    row[REQUIRED_COLUMNS.index("C2")] = '{"idrg":{"cost_weight":"-0.1","total_tarif":"-2"}}'
    df = read_eklaim_txt(_txt(row)).df.iloc[0]
    assert df["_total_tarif_num"] is None
    assert df["_los_num"] is None
    assert df["_icu_indikator_num"] is None
    assert df["_icu_los_num"] is None
    assert df["_idrg_cost_weight"] is None
    assert df["_idrg_total_tarif"] is None
    assert "VENT_HOUR" in NUMERIC_COLUMNS
    assert set(TARIFF_COMPONENTS).issubset(NUMERIC_COLUMNS)


def test_optional_tariff_fields_are_parsed_and_empty_schema_has_metadata() -> None:
    header = REQUIRED_COLUMNS + ["OBAT", "TARIF_SP", "TARIF_POLI_EKS"]
    row = _row() + ["1234", "5678", "90"]
    parsed = read_eklaim_txt(_txt(row, header)).df.iloc[0]
    assert parsed["_obat_num"] == 1234
    assert parsed["_tarif_sp_num"] == 5678
    assert parsed["_tarif_poli_eks_num"] == 90
    empty = read_eklaim_txt(io.BytesIO(b"")).df
    assert {"_source", "_row_number", "_idrg_total_cost_weight", "_c2_status"}.issubset(empty.columns)
