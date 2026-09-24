from io import BytesIO
from unittest.mock import patch

import fitz
import pandas as pd
from streamlit.testing.v1 import AppTest

from src.ui.follow_up import build_follow_up
from src.ui.results import begin_review, finish_review, input_signature, review_is_current, set_current_input
from src.parser_eklaim_txt import REQUIRED_COLUMNS


def test_result_identity_and_failed_rerun():
    first = BytesIO(b"old")
    first.name = "claims.txt"
    second = BytesIO(b"new")
    second.name = first.name
    old_signature = input_signature(first, "folder", ["SEP"])
    assert old_signature != input_signature(second, "folder", ["SEP"])
    assert old_signature != input_signature(first, "other folder", ["SEP"])
    assert old_signature != input_signature(first, "folder", ["LIP"])
    with patch("src.ui.results.st.session_state", {}):
        finish_review("content", old_signature, first.name)
        assert review_is_current("content")
        set_current_input("content", input_signature(second))
        assert not review_is_current("content")
        finish_review("content", old_signature, first.name)
        begin_review("content")
        assert not review_is_current("content")


def test_stale_content_results_are_hidden_and_presets_work():
    app = AppTest.from_string("from src.ui.content_review import render_content_review_tab\nrender_content_review_tab()")
    app.run()
    assert not app.exception
    assert app.multiselect[0].value == ["Resume Medis", "Surat Perintah Rawat Inap"]
    app.selectbox(key="content_profile").select("Rawat jalan").run()
    assert app.multiselect[0].value == []
    signature = input_signature([], "", False, "Rawat jalan", [
        "SEP Terdeteksi Dalam PDF", "LIP Terdeteksi", "Rincian Tagihan Terdeteksi",
    ])
    app.session_state["content_review_df"] = pd.DataFrame([{"Status Akhir": "Lengkap", "No SEP": "OLD"}])
    app.session_state["content_orphan_df"] = pd.DataFrame()
    app.session_state["content_summary"] = {"Total PDF": 1}
    app.session_state["content_result_context"] = {"signature": signature, "source": "old.pdf", "time": "test"}
    app.run()
    assert len(app.dataframe) == 1
    app.text_input(key="content_review_folder").set_value("changed-folder").run()
    assert not app.exception
    assert not app.dataframe
    assert any("kedaluwarsa" in warning.value for warning in app.warning)
    assert not app.get("download_button")


def test_follow_up_groups_valid_sep_and_preserves_multiple_findings():
    sep = "0132R0770626V000001"
    result = build_follow_up([
        ("TXT", pd.DataFrame([{"SEP": sep, "Field": "LOS", "Masalah": "Kosong"}])),
        ("Isi", pd.DataFrame([
            {"No SEP": sep, "Status Akhir": "Perlu Review Manual", "Catatan": "SEP berbeda"},
            {"No SEP": "0132R0770626V000002", "Status Akhir": "Lengkap", "Catatan": ""},
        ])),
    ])
    assert len(result) == 1
    assert "LOS: Kosong" in result.iloc[0]["Temuan"]
    assert "SEP berbeda" in result.iloc[0]["Temuan"]
    assert result.iloc[0]["Status tindak lanjut"] == "Belum ditinjau"


def test_content_folder_review_exports_current_checklist(tmp_path):
    sep = "0132R0770626V000001"
    path = tmp_path / f"{sep}.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), f"Berkas Klaim Individual Pasien\nNomor SEP: {sep}\nTanggal Masuk: 01/06/2026\nTanggal Keluar: 03/06/2026\nKelas Perawatan: 1")
        page = document.new_page()
        page.insert_text((40, 40), "Rincian Tagihan\nPelayanan dokter dan pemeriksaan pasien\nTotal Biaya: 100000")
        document.save(path)
    app = AppTest.from_string("from src.ui.content_review import render_content_review_tab\nrender_content_review_tab()")
    app.run()
    app.text_input(key="content_review_folder").set_value(str(tmp_path))
    app.selectbox(key="content_profile").select("Rawat jalan").run()
    app.button(key="run_content_review").click().run()
    assert not app.exception
    assert not app.error
    result = app.session_state["content_review_df"].iloc[0]
    assert result["Status Akhir"] == "Lengkap"
    assert result["Resume Medis"] == "Tidak berlaku"
    assert result["Hasil Scan Terdeteksi"] == "Tidak berlaku"
    assert "Rincian Tagihan Terdeteksi: 2" in result["Bukti Halaman"]
    assert app.session_state["content_export_bytes"].startswith(b"PK")
    app.selectbox(key="content_profile").select("Rawat inap").run()
    assert any("kedaluwarsa" in warning.value for warning in app.warning)
    assert not app.get("download_button")


def test_follow_up_notes_survive_leaving_tab_and_reset_for_changed_findings():
    app = AppTest.from_string(
        "import streamlit as st\nfrom src.ui.follow_up import render_follow_up_tab\n"
        "if st.checkbox('Show', value=True):\n    render_follow_up_tab()"
    )
    frame = pd.DataFrame([{
        "No SEP": "0132R0770626V000001", "Status Akhir": "Perlu Review Manual", "Catatan": "SEP berbeda",
    }])
    context = {"signature": "current", "source": "test.pdf", "time": "test"}
    app.session_state["content_review_df"] = frame
    app.session_state["content_result_context"] = context
    app.session_state["content_current_input"] = "current"
    app.run()
    editor_key = "follow_up_editor_" + app.session_state["follow_up_revision"]
    app.session_state[editor_key] = {
        "edited_rows": {0: {"Petugas": "Petugas uji", "Catatan koreksi": "Diperiksa", "Status tindak lanjut": "Selesai"}},
        "added_rows": [], "deleted_rows": [],
    }
    app.run()
    app.checkbox[0].uncheck().run()
    app.checkbox[0].check().run()
    assert not app.exception
    assert app.dataframe[0].value.iloc[0]["Petugas"] == "Petugas uji"
    assert app.dataframe[0].value.iloc[0]["Status tindak lanjut"] == "Selesai"
    frame.loc[0, "Catatan"] = "Tagihan belum terdeteksi"
    app.session_state["content_review_df"] = frame
    app.session_state["content_result_context"] = {**context, "time": "new review"}
    app.run()
    assert app.dataframe[0].value.iloc[0]["Status tindak lanjut"] == "Belum ditinjau"


def test_txt_upload_mixed_types_and_missing_values_can_render_and_export():
    first = dict.fromkeys(REQUIRED_COLUMNS, "0")
    first.update(SEP="0132R0770626V000001", PTD="1", INACBG="K-4-17-I", DIAGLIST="A09.9", PROCLIST="90.59",
                 TOTAL_TARIF="1000000", TARIF_RS="1500000", LOS="3", DPJP="Dokter uji",
                 C2='{"idrg":{"cost_weight":0.5}}', NAMA_PASIEN="Uji", MRN="Uji")
    second = {**first, "SEP": "0132R0770626V000002", "PTD": "2", "TOTAL_TARIF": "", "LOS": "", "PROCLIST": ""}
    content = pd.DataFrame([first, second]).to_csv(sep="\t", index=False).encode()
    app = AppTest.from_string("from src.ui.txt_analysis import render_txt_analysis_tab\nrender_txt_analysis_tab()")
    app.run()
    app.file_uploader(key="eklaim_txt_ri").upload("test.txt", content, "text/plain").run()
    app.button(key="run_eklaim_txt_analysis").click().run()
    assert not app.exception
    assert not app.error
    analysis = app.session_state["eklaim_analysis"]
    assert analysis.summary["Total Klaim Rawat Jalan"] == 1
    assert analysis.summary["Total Klaim Rawat Inap"] == 1
    assert analysis.summary["Selisih Total Tarif RS - Grouper"] == ""
    assert any("parsial" in warning.value for warning in app.warning)
    assert app.session_state["eklaim_export_bytes"].startswith(b"PK")
    app.file_uploader(key="eklaim_txt_ri").upload("other.txt", content, "text/plain").run()
    assert not app.get("download_button")
    assert any("kedaluwarsa" in warning.value for warning in app.warning)


def test_txt_all_quarantined_input_renders_without_exception():
    row = dict.fromkeys(REQUIRED_COLUMNS, "0")
    row.update(SEP="not-a-sep", PTD="1", INACBG="K-4-17-I", DIAGLIST="A09.9", PROCLIST="90.59",
               TOTAL_TARIF="1000", TARIF_RS="1200", LOS="2", DPJP="Dokter uji",
               C2='{"idrg":{"cost_weight":0.5,"total_tarif":1100}}', NAMA_PASIEN="Uji", MRN="RM001")
    content = pd.DataFrame([row]).to_csv(sep="\t", index=False).encode()
    app = AppTest.from_string("from src.ui.txt_analysis import render_txt_analysis_tab\nrender_txt_analysis_tab()")
    app.run()
    app.file_uploader(key="eklaim_txt_ri").upload("invalid.txt", content, "text/plain").run()
    app.button(key="run_eklaim_txt_analysis").click().run()

    assert not app.exception
    assert not app.error
    assert app.session_state["eklaim_analysis"].summary["Total Klaim Keseluruhan"] == 0
    assert len(app.session_state["eklaim_analysis"].quarantine_df) == 1


def test_txt_cmi_metric_displays_four_decimal_places():
    row = dict.fromkeys(REQUIRED_COLUMNS, "0")
    row.update(SEP="0132R0770626V000001", PTD="1", INACBG="K-4-17-I", DIAGLIST="A09.9", PROCLIST="90.59",
               TOTAL_TARIF="1000", TARIF_RS="1200", LOS="2", DPJP="Dokter uji",
               C2='{"idrg":{"cost_weight":0.4927,"total_tarif":1100}}', NAMA_PASIEN="Uji", MRN="RM001")
    content = pd.DataFrame([row]).to_csv(sep="\t", index=False).encode()
    app = AppTest.from_string("from src.ui.txt_analysis import render_txt_analysis_tab\nrender_txt_analysis_tab()")
    app.run()
    app.file_uploader(key="eklaim_txt_ri").upload("valid.txt", content, "text/plain").run()
    app.button(key="run_eklaim_txt_analysis").click().run()

    assert not app.exception
    assert any(metric.value == "0,4927" for metric in app.metric)


def test_file_review_input_change_hides_old_export():
    sep = "0132R0770626V000001"
    excel = BytesIO()
    pd.DataFrame([{"No SEP": sep, "Tanggal Pulang": "2026-06-03"}]).to_excel(excel, index=False)
    app = AppTest.from_string("from src.ui.file_review import render_file_review_tab\nrender_file_review_tab()")
    app.run()
    app.file_uploader(key="file_review_excel").upload("claims.xlsx", excel.getvalue()).run()
    app.file_uploader(key="file_review_list").upload("list.txt", f"D:\\Klaim\\03\\{sep}.pdf".encode()).run()
    app.button(key="run_file_review").click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["file_review_df"].iloc[0]["Status Akhir"] == "Lengkap"
    app.radio(key="file_review_source_mode").set_value("Folder Berkas Lokal").run()
    assert not app.get("download_button")
    assert any("kedaluwarsa" in warning.value for warning in app.warning)
