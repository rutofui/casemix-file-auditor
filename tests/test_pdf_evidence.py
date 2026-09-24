import fitz

from src.config import PDFCheckConfig
from src.pdf_checker import (
    _select_lip_text,
    check_first_page_codes,
    check_lip_metadata,
    check_pdf,
    detect_pdf_components,
)


def test_billing_and_lip_need_document_evidence():
    components = detect_pdf_components(
        "Resume Medis INA-CBG untuk evaluasi\nBerkas Klaim Individual Pasien\n"
        "Total Tarif: Rp 10.000\nTarif Rumah Sakit: Rp 10.000"
    )
    assert components["billing_detected"] is False
    assert components["lip_detected"] is True
    assert _select_lip_text(["Resume pasien dan tanggal masuk 01/01/2025"]) == ""


def test_random_mention_does_not_count_as_lip_or_billing():
    components = detect_pdf_components(
        "Resume Medis membahas Total Tarif dan Tarif Rumah Sakit. INA-CBG"
    )
    assert components["billing_detected"] is False
    assert components["lip_detected"] is False


def test_component_page_evidence_is_one_based():
    components = detect_pdf_components(
        "", page_texts=["", "Berkas Klaim Individual Pasien\nRincian Tagihan"]
    )
    assert components["component_pages"]["LIP Terdeteksi"] == [2]
    assert components["component_pages"]["Rincian Tagihan Terdeteksi"] == [2]


def test_lip_metadata_searches_entire_pdf_and_never_uses_non_lip_page(tmp_path):
    path = tmp_path / "claim.pdf"
    doc = fitz.open()
    for text in ["Resume Medis", "", "Lampiran", "Berkas Klaim Individual Pasien\nTanggal Masuk: 01/06/2026"]:
        page = doc.new_page()
        if text:
            page.insert_text((40, 40), text)
    doc.save(path)
    doc.close()

    lip = check_lip_metadata([str(path)], expected_tanggal_masuk="2026-06-01")
    assert lip.readable is True
    assert lip.lip_page_number == 4
    assert lip.tanggal_masuk_match is True
    assert any("claim.pdf, halaman 4" in note for note in lip.notes)

def test_dates_on_non_lip_page_do_not_count_as_lip(tmp_path):
    path = tmp_path / "resume.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 40), "Resume Medis\nTanggal Masuk: 01/06/2026")
    doc.save(path)
    doc.close()

    result = check_lip_metadata([str(path)], expected_tanggal_masuk="2026-06-01")
    assert result.readable is False
    assert result.tanggal_masuk_lip == ""


def test_blank_first_page_is_unreadable_for_icd_check(tmp_path):
    path = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()

    result = check_first_page_codes([str(path)], ["A09"], [])
    assert result.readable is False
    assert result.icd10_missing == ["A09"]


def test_ocr_failure_keeps_prior_pdf_evidence_and_marks_manual(tmp_path, monkeypatch):
    path = tmp_path / "claim.pdf"
    doc = fitz.open()
    for text in ["SEP 0132R0770526V001270", "second page"]:
        page = doc.new_page()
        page.insert_text((40, 40), text)
    doc.save(path)
    doc.close()
    calls = 0

    def ocr_page(*_args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ""
        raise RuntimeError("synthetic OCR failure")

    monkeypatch.setattr("src.pdf_checker._page_has_scan", lambda *_args: True)
    monkeypatch.setattr("src.pdf_checker._page_needs_ocr", lambda *_args: True)
    monkeypatch.setattr("src.pdf_checker._get_paddleocr_engine", lambda *_args: object())
    monkeypatch.setattr("src.pdf_checker._ocr_page", ocr_page)

    result = check_pdf("source", str(path), PDFCheckConfig(use_ocr=True))
    assert result.needs_manual_review is True
    assert result.sep_values == ["0132R0770526V001270"]
    assert "OCR gagal pada halaman 2" in " ".join(result.notes)
