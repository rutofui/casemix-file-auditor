from __future__ import annotations

from pathlib import Path
import tempfile

import pandas as pd
import pytest

from src.config import PDFCheckConfig
from src.matcher import build_file_review, build_pdf_content_review
from src.parser_excel import read_claims_excel
from src.parser_file_list import build_file_entry, parse_file_list_text, scan_pdf_folder
from src.pdf_parallel import (
    MAX_OCR_PDF_WORKERS,
    automatic_pdf_worker_count,
    check_first_page_codes_parallel,
    check_lip_metadata_parallel,
    check_pdfs_parallel,
    resolve_pdf_worker_count,
)
from src.config import detect_document_titles, detect_document_titles_from_pages
from src.pdf_checker import check_first_page_codes, check_lip_metadata, check_pdf




def _write_pdf(path: Path, text: str, *, with_scan_image: bool = False) -> None:
    import fitz
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), text, fontsize=10)

    image_path = None
    if with_scan_image:
        image_path = path.with_suffix(".png")
        image = Image.new("RGB", (1600, 1000), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=42)
        y = 80
        for line in ["HASIL SCAN BERKAS KLAIM", "Dokumen scan dari rekam medis"]:
            draw.text((80, y), line, fill="black", font=font)
            y += 70
        image.save(image_path)
        page.insert_image(fitz.Rect(60, 180, 535, 520), filename=str(image_path))

    doc.save(path)
    doc.close()
    if image_path:
        image_path.unlink(missing_ok=True)


def _complete_claim_text(sep: str) -> str:
    return "\n".join(
        [
            f"Nomor SEP {sep}",
            "Berkas Klaim Individual Pasien",
            "Rincian Tagihan Barang Jasa Fasilitas Total Tarif INA-CBG",
        ]
    )


def test_file_review_and_content_review_with_scan_component() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        excel_path = root / "klaim.xlsx"
        sep_complete = "0132R0770526V001270"
        sep_missing_pdf = "0132R0770526V001271"
        sep_wrong_folder = "0132R0770526V001272"

        pd.DataFrame(
            [
                {
                    "No SEP": sep_complete,
                    "Tanggal Pulang": "2026-05-01",
                    "No RM": "RM001",
                    "Nama Pasien": "Pasien A",
                    "Diagnosa": "A00",
                },
                {
                    "No SEP": sep_missing_pdf,
                    "Tanggal Pulang": "2026-05-02",
                    "No RM": "RM002",
                    "Nama Pasien": "Pasien B",
                    "Diagnosa": "B00",
                },
                {
                    "No SEP": "",
                    "Tanggal Pulang": "2026-05-03",
                    "No RM": "RM003",
                    "Nama Pasien": "Pasien C",
                    "Diagnosa": "C00",
                },
                {
                    "No SEP": sep_wrong_folder,
                    "Tanggal Pulang": "2026-05-01",
                    "No RM": "RM004",
                    "Nama Pasien": "Pasien D",
                    "Diagnosa": "D00",
                },
            ]
        ).to_excel(excel_path, index=False)

        pdf_path = root / "Casemix" / "Pending" / "2026" / "05. Mei" / "Rawat inap" / "01" / f"{sep_complete}.pdf"
        _write_pdf(pdf_path, _complete_claim_text(sep_complete), with_scan_image=True)
        wrong_folder_pdf_path = (
            root
            / "Casemix"
            / "Pending"
            / "2026"
            / "05. Mei"
            / "Rawat inap"
            / "02"
            / f"{sep_wrong_folder}.pdf"
        )
        _write_pdf(wrong_folder_pdf_path, _complete_claim_text(sep_wrong_folder), with_scan_image=True)
        list_text = "\n".join(
            [
                str(pdf_path.parent),
                str(pdf_path),
                str(wrong_folder_pdf_path),
                str(root / "readme.txt"),
            ]
        )

        claims = read_claims_excel(str(excel_path)).df
        files = parse_file_list_text(list_text).df
        pdf_results = {
            row["source_id"]: check_pdf(
                str(row["source_id"]),
                str(row["local_path"]),
                PDFCheckConfig(),
            )
            for _, row in files.iterrows()
        }
        file_review_df, orphan_df, file_summary = build_file_review(claims, files)
        content_review_df, _, content_summary = build_pdf_content_review(files, pdf_results)

        assert file_summary["Total klaim"] == 4
        assert file_summary["Total SEP valid"] == 3
        assert file_review_df.loc[0, "Status Akhir"] == "Lengkap"
        assert file_review_df.loc[0, "Status Folder"] == "Sesuai"
        assert file_review_df.loc[1, "Status Akhir"] == "Kurang PDF"
        assert file_review_df.loc[2, "Status Akhir"] == "Perlu Review Manual"
        assert file_review_df.loc[3, "Status Akhir"] == "Salah Folder"
        assert content_summary["Total PDF"] == 2
        assert content_summary["Isi lengkap"] == 2
        assert content_summary["Hasil scan"] == 2
        assert content_review_df.loc[0, "Hasil Scan Terdeteksi"] == "Ya"
        assert content_review_df.loc[0, "Status Akhir"] == "Lengkap"
        assert orphan_df.empty


def test_content_review_requires_scan_image() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        sep = "0132R0770526V001270"
        pdf_path = root / f"{sep}.pdf"
        _write_pdf(pdf_path, _complete_claim_text(sep), with_scan_image=False)
        entry = build_file_entry(
            pdf_path.name,
            local_path=str(pdf_path),
            source="upload",
            is_index_source=False,
            is_content_source=True,
        )
        files = pd.DataFrame([entry])
        pdf_results = {
            entry["source_id"]: check_pdf(
                str(entry["source_id"]),
                str(entry["local_path"]),
                PDFCheckConfig(),
            )
        }

        review_df, _, summary = build_pdf_content_review(files, pdf_results)

        assert summary["Kurang komponen"] == 1
        assert review_df.loc[0, "Status Akhir"] == "Kurang Komponen"
        assert review_df.loc[0, "Hasil Scan Terdeteksi"] == "Tidak"
        assert "Hasil Scan Terdeteksi" in review_df.loc[0, "Catatan"]


def test_small_logo_image_is_not_treated_as_scan() -> None:
    import fitz
    from PIL import Image

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pdf_path = root / "small_logo.pdf"
        image_path = root / "logo.png"
        Image.new("RGB", (120, 120), "white").save(image_path)

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "SEP", fontsize=10)
        page.insert_image(fitz.Rect(72, 96, 132, 156), filename=str(image_path))
        doc.save(str(pdf_path))
        doc.close()

        result = check_pdf("small_logo", str(pdf_path), PDFCheckConfig())

    assert result.scan_detected is False
    assert result.scan_page_count == 0


def test_ocr_mode_uses_automatic_worker_count() -> None:
    total = 10
    ocr_count = resolve_pdf_worker_count(total, use_ocr=True)
    non_ocr_count = resolve_pdf_worker_count(total, use_ocr=False)
    expected_non_ocr = automatic_pdf_worker_count(total)
    expected_ocr = min(expected_non_ocr, MAX_OCR_PDF_WORKERS)

    assert ocr_count == expected_ocr
    assert non_ocr_count == expected_non_ocr
    if expected_ocr > 1:
        assert ocr_count > 1
    if expected_non_ocr > MAX_OCR_PDF_WORKERS:
        assert ocr_count == MAX_OCR_PDF_WORKERS


def test_parallel_pdf_check_matches_serial_results() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        sep_complete = "0132R0770526V001270"
        sep_missing_scan = "0132R0770526V001271"
        complete_pdf = root / f"{sep_complete}.pdf"
        missing_scan_pdf = root / f"{sep_missing_scan}.pdf"
        config = PDFCheckConfig()

        _write_pdf(complete_pdf, _complete_claim_text(sep_complete), with_scan_image=True)
        _write_pdf(missing_scan_pdf, _complete_claim_text(sep_missing_scan), with_scan_image=False)

        jobs = [
            ("complete", str(complete_pdf)),
            ("missing_scan", str(missing_scan_pdf)),
        ]
        serial_results = {
            source_id: check_pdf(source_id, local_path, config)
            for source_id, local_path in jobs
        }
        parallel_results = check_pdfs_parallel(jobs, config)

        assert set(parallel_results) == set(serial_results)
        for source_id in serial_results:
            assert parallel_results[source_id].readable == serial_results[source_id].readable
            assert parallel_results[source_id].sep_values == serial_results[source_id].sep_values
            assert parallel_results[source_id].lip_detected == serial_results[source_id].lip_detected
            assert parallel_results[source_id].billing_detected == serial_results[source_id].billing_detected
            assert parallel_results[source_id].scan_detected == serial_results[source_id].scan_detected


def test_file_review_can_scan_local_folder_instead_of_txt_list() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        excel_path = root / "klaim.xlsx"
        sep_complete = "0132R0770526V001270"
        sep_missing_pdf = "0132R0770526V001271"
        sep_wrong_folder = "0132R0770526V001272"

        pd.DataFrame(
            [
                {
                    "No SEP": sep_complete,
                    "Tanggal Pulang": "2026-05-01",
                    "No RM": "RM001",
                    "Nama Pasien": "Pasien A",
                    "Diagnosa": "A00",
                },
                {
                    "No SEP": sep_missing_pdf,
                    "Tanggal Pulang": "2026-05-02",
                    "No RM": "RM002",
                    "Nama Pasien": "Pasien B",
                    "Diagnosa": "B00",
                },
                {
                    "No SEP": sep_wrong_folder,
                    "Tanggal Pulang": "2026-05-01",
                    "No RM": "RM003",
                    "Nama Pasien": "Pasien C",
                    "Diagnosa": "C00",
                },
            ]
        ).to_excel(excel_path, index=False)

        pdf_root = root / "Casemix" / "Pending" / "2026" / "05. Mei" / "Rawat inap"
        complete_pdf = pdf_root / "01" / f"{sep_complete}.pdf"
        wrong_folder_pdf = pdf_root / "02" / f"{sep_wrong_folder}.pdf"
        _write_pdf(complete_pdf, _complete_claim_text(sep_complete), with_scan_image=True)
        _write_pdf(wrong_folder_pdf, _complete_claim_text(sep_wrong_folder), with_scan_image=True)

        claims = read_claims_excel(str(excel_path)).df
        folder_entries = scan_pdf_folder(str(pdf_root), source_name="folder", is_index_source=True).df
        review_df, orphan_df, summary = build_file_review(claims, folder_entries)

        assert summary["Total klaim"] == 3
        assert summary["PDF ditemukan"] == 2
        assert summary["Belum ada PDF"] == 1
        assert review_df.loc[0, "Status Akhir"] == "Lengkap"
        assert review_df.loc[1, "Status Akhir"] == "Kurang PDF"
        assert review_df.loc[2, "Status Akhir"] == "Salah Folder"
        assert orphan_df.empty


def test_detect_document_titles_from_review_text() -> None:
    text = "\n".join(
        [
            "RESUME MEDIS",
            "SURAT PERINTAH RAWAT INAP",
            "NOMOR SURAT: 0132R0770426K001487",
            "MOHON PERAWATAN DAN PENANGANAN LEBIH LANJUT",
            "HASIL PEMERIKSAAN RADIOLOGI",
        ]
    )

    assert detect_document_titles(text) == [
        "Resume Medis",
        "Surat Perintah Rawat Inap",
        "Hasil Pemeriksaan",
        "Pemeriksaan Radiologi",
    ]


def test_spri_not_detected_from_generic_rawat_inap_text() -> None:
    sep_text = "\n".join(
        [
            "SURAT ELIGIBILITAS PESERTA",
            "JENIS RAWAT INAP",
            "RUANG PERAWATAN",
            "RESUME MEDIS RINGKASAN PULANG",
        ]
    )

    assert "Surat Perintah Rawat Inap" not in detect_document_titles(sep_text)


def test_spri_detected_from_form_title_and_token() -> None:
    assert "Surat Perintah Rawat Inap" in detect_document_titles(
        "FORMULIR SPRI NO 123\nNomor Surat: 001\nMohon perawatan pasien"
    )
    assert "Surat Perintah Rawat Inap" not in detect_document_titles("DOKUMEN SPRI PASIEN")
    assert "Surat Perintah Rawat Inap" not in detect_document_titles("DESKRIPSI SPRINTER RUANGAN")


def test_spri_not_detected_when_title_and_context_on_different_pages() -> None:
    pages = [
        "SURAT PERINTAH RAWAT INAP",
        "NOMOR SURAT: 0132R0770426K001487 MOHON PERAWATAN PASIEN",
        "SURAT ELIGIBILITAS PESERTA JENIS RAWAT INAP",
    ]

    assert "Surat Perintah Rawat Inap" not in detect_document_titles_from_pages(pages)


def test_spri_detected_only_on_matching_page_in_multi_page_pdf() -> None:
    pages = [
        "SURAT ELIGIBILITAS PESERTA JENIS RAWAT INAP TANGGAL MASUK",
        """
        SURAT PERINTAH RAWAT INAP
        Nomor Surat: 0132R0770426K001487
        Mohon perawatan dan penanganan lebih lanjut untuk pasien dibawah ini:
        """,
        "RESUME MEDIS DPJP RAWAT INAP",
    ]

    titles = detect_document_titles_from_pages(pages)
    assert "Surat Perintah Rawat Inap" in titles
    assert "Resume Medis" in titles


def test_spri_detected_from_scanned_form_ocr_text() -> None:
    """Regression sample from RS DKH Sukatani SPRI scan (0132R0770426V001254)."""
    ocr_text = """
    RS DKH SUKATANI
    BPJS Kesehatan
    SURAT PERINTAH RAWAT INAP
    Nomor Surat: 0132R0770426K001487
    Mohon perawatan dan penanganan lebih lanjut untuk pasien dibawah ini:
    Jenis Ruang: Medikal (Non Infeksi)
    Rawat Inap untuk dirawat oleh:
    DPJP Rawat Inap: dr. Selvi Destaria, Sp.A
    Alasan Rawat Inap: demam tinggi + muntah berulang + dehidrasi sedang
    """

    titles = detect_document_titles(ocr_text)
    assert "Surat Perintah Rawat Inap" in titles


def test_spri_detected_from_header_only_ocr_crop() -> None:
    from src.config import detect_document_titles_on_page

    header_text = "RS CONTOH\nSURAT PERINTAH RAWAT INAP"
    assert "Surat Perintah Rawat Inap" in detect_document_titles_on_page(
        header_text,
        header_only_ocr=True,
    )
    assert "Surat Perintah Rawat Inap" not in detect_document_titles_on_page(
        header_text,
        header_only_ocr=False,
    )


def test_ocr_defaults_use_small_model_and_header_crop() -> None:
    config = PDFCheckConfig(use_ocr=True)
    assert config.ocr_render_zoom == 1.5
    assert config.ocr_crop_top_ratio == pytest.approx(1 / 3)
    assert config.ocr_detection_model_name == "PP-OCRv6_small_det"
    assert config.ocr_recognition_model_name == "PP-OCRv6_small_rec"


def test_ocr_early_stop_skips_pages_after_all_titles_found() -> None:
    """Pages after all 5 title categories are found in digital text should not be OCR'd."""
    import fitz

    all_titles_text = "\n".join([
        "RESUME MEDIS ringkasan pulang",
        "TRIAGE form triase",
        "SURAT PERINTAH RAWAT INAP",
        "Nomor Surat: ABC",
        "Mohon perawatan lebih lanjut",
        "HASIL PEMERIKSAAN LABORATORIUM",
        "PEMERIKSAAN RADIOLOGI RONTGEN",
    ])

    with tempfile.TemporaryDirectory() as d:
        pdf_path = Path(d) / "test_early_stop.pdf"
        doc = fitz.open()
        # page 0: digital text with all 5 title categories
        page0 = doc.new_page()
        page0.insert_text((50, 50), all_titles_text, fontsize=11)
        # page 1: blank scan page (no digital text) — would need OCR
        doc.new_page()
        doc.save(str(pdf_path))
        doc.close()

        from unittest.mock import patch as mock_patch

        ocr_calls: list[int] = []
        page_counter = {"i": 0}

        def counting_ocr(page, engine, config):  # noqa: ARG001
            ocr_calls.append(page_counter["i"])
            return ""

        def counting_needs_ocr(page, text, config, has_scan):  # noqa: ARG001
            from src.config import normalize_text as _norm
            page_counter["i"] += 1
            return len(_norm(text)) < config.min_page_text_chars

        from src.config import PDFCheckConfig
        from src.pdf_checker import check_pdf

        with mock_patch("src.pdf_checker._ocr_page", side_effect=counting_ocr):
            with mock_patch("src.pdf_checker._get_paddleocr_engine", return_value=object()):
                with mock_patch("src.pdf_checker._page_needs_ocr", side_effect=counting_needs_ocr):
                    cfg = PDFCheckConfig(use_ocr=True, min_page_text_chars=10)
                    r = check_pdf("early_stop", str(pdf_path), cfg)

        # Page 0 has digital text with all 5 titles → titles_found becomes full
        # Page 1 is blank → needs OCR but must be skipped due to early stop
        assert ocr_calls == [], (
            f"Expected 0 OCR calls after all titles found on page 0, got {len(ocr_calls)} calls"
        )
        assert "Resume Medis" in r.document_titles
        assert "Pemeriksaan Radiologi" in r.document_titles


def test_check_first_page_codes_finds_codes_on_first_page() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = Path(temp_dir) / "page0.pdf"
        _write_pdf(pdf_path, "DIAGNOSA: A09.9; E86\nTINDAKAN: 90.59")

        result = check_first_page_codes([str(pdf_path)], ["A09.9", "E86"], ["90.59"])

    assert result.readable is True
    assert result.icd10_missing == []
    assert result.icd9_missing == []


def test_check_first_page_codes_ignores_codes_only_on_later_pages() -> None:
    import fitz

    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = Path(temp_dir) / "multi_page.pdf"
        doc = fitz.open()
        page0 = doc.new_page(width=595, height=842)
        page0.insert_text((72, 72), "Halaman pertama tanpa kode diagnosa.", fontsize=10)
        page1 = doc.new_page(width=595, height=842)
        page1.insert_text((72, 72), "DIAGNOSA: A09.9", fontsize=10)
        doc.save(str(pdf_path))
        doc.close()

        result = check_first_page_codes([str(pdf_path)], ["A09.9"], [])

    assert result.readable is True
    assert result.icd10_missing == ["A09.9"]


def test_check_first_page_codes_unions_text_across_duplicate_paths() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        path_a = root / "a.pdf"
        path_b = root / "b.pdf"
        _write_pdf(path_a, "DIAGNOSA: A09.9")
        _write_pdf(path_b, "DIAGNOSA: E86")

        result = check_first_page_codes([str(path_a), str(path_b)], ["A09.9", "E86"], [])

    assert result.readable is True
    assert result.icd10_missing == []


def test_check_first_page_codes_nonexistent_path_is_unreadable() -> None:
    result = check_first_page_codes(["/nonexistent/path/does_not_exist.pdf"], ["A09.9"], ["90.59"])

    assert result.readable is False
    assert result.icd10_missing == ["A09.9"]
    assert result.icd9_missing == ["90.59"]
    assert result.error


def test_check_first_page_codes_parallel_matches_serial_results() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        complete_pdf = root / "complete.pdf"
        missing_pdf = root / "missing.pdf"
        _write_pdf(complete_pdf, "DIAGNOSA: A09.9; E86")
        _write_pdf(missing_pdf, "DIAGNOSA: A09.9")

        jobs = [
            ("sep_complete", [str(complete_pdf)], ["A09.9", "E86"], []),
            ("sep_missing", [str(missing_pdf)], ["A09.9", "E86"], []),
        ]
        serial_results = {
            sep: check_first_page_codes(paths, icd10, icd9) for sep, paths, icd10, icd9 in jobs
        }
        parallel_results = check_first_page_codes_parallel(jobs)

        assert set(parallel_results) == set(serial_results)
        for sep in serial_results:
            assert parallel_results[sep].readable == serial_results[sep].readable
            assert parallel_results[sep].icd10_missing == serial_results[sep].icd10_missing
            assert parallel_results[sep].icd9_missing == serial_results[sep].icd9_missing


def test_check_lip_metadata_matches_dates_and_care_class() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = Path(temp_dir) / "lip.pdf"
        _write_pdf(
            pdf_path,
            "\n".join(
                [
                    "BERKAS KLAIM INDIVIDUAL PASIEN",
                    "Tanggal Masuk : 01/06/2026",
                    "Tanggal Keluar : 05/06/2026",
                    "Kelas Perawatan : Kelas II",
                ]
            ),
        )

        result = check_lip_metadata(
            [str(pdf_path)],
            expected_tanggal_masuk="2026-06-01",
            expected_tanggal_keluar="2026-06-05",
            expected_kelas_perawatan="2",
        )

    assert result.readable is True
    assert result.tanggal_masuk_match is True
    assert result.tanggal_keluar_match is True
    assert result.kelas_perawatan_match is True


def test_check_lip_metadata_detects_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = Path(temp_dir) / "lip.pdf"
        _write_pdf(
            pdf_path,
            "Lembar Individual Pasien\nTanggal Masuk : 02/06/2026\nTanggal Keluar : 05/06/2026\nKelas : Kelas III",
        )

        result = check_lip_metadata(
            [str(pdf_path)],
            expected_tanggal_masuk="2026-06-01",
            expected_tanggal_keluar="2026-06-05",
            expected_kelas_perawatan="Kelas II",
        )

    assert result.tanggal_masuk_match is False
    assert result.tanggal_keluar_match is True
    assert result.kelas_perawatan_match is False


def test_check_lip_metadata_parallel_matches_serial_results() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        path_a = root / "a.pdf"
        path_b = root / "b.pdf"
        _write_pdf(path_a, "LIP\nTanggal Masuk : 01/06/2026\nTanggal Keluar : 05/06/2026\nKelas : 1")
        _write_pdf(path_b, "LIP\nTanggal Masuk : 02/06/2026\nTanggal Keluar : 06/06/2026\nKelas : 2")
        jobs = [
            ("sep_a", [str(path_a)], "2026-06-01", "2026-06-05", "Kelas I"),
            ("sep_b", [str(path_b)], "2026-06-02", "2026-06-06", "Kelas II"),
        ]

        serial_results = {
            sep: check_lip_metadata(paths, expected_tanggal_masuk=tm, expected_tanggal_keluar=tk, expected_kelas_perawatan=kp)
            for sep, paths, tm, tk, kp in jobs
        }
        parallel_results = check_lip_metadata_parallel(jobs)

    assert set(parallel_results) == set(serial_results)
    for sep in serial_results:
        assert parallel_results[sep].tanggal_masuk_match == serial_results[sep].tanggal_masuk_match
        assert parallel_results[sep].tanggal_keluar_match == serial_results[sep].tanggal_keluar_match
        assert parallel_results[sep].kelas_perawatan_match == serial_results[sep].kelas_perawatan_match


def test_content_review_columns_and_requirements_differ_for_ocr_mode() -> None:
    sep = "0132R0770526V001270"
    entry = build_file_entry(
        f"{sep}.pdf",
        local_path=f"C:\\dummy\\{sep}.pdf",
        source="folder",
        is_index_source=False,
        is_content_source=True,
    )
    files = pd.DataFrame([entry])
    pdf_result = {
        "readable": True,
        "sep_values": [sep],
        "lip_detected": True,
        "billing_detected": True,
        "scan_detected": True,
        "document_titles": [
            "Resume Medis",
            "Triage",
            "Surat Perintah Rawat Inap",
            "Hasil Pemeriksaan",
            "Pemeriksaan Radiologi",
        ],
        "needs_manual_review": False,
        "error": "",
        "notes": [],
    }
    pdf_results = {entry["source_id"]: pdf_result}

    non_ocr_df, _, non_ocr_summary = build_pdf_content_review(
        files,
        pdf_results,
        use_ocr=False,
    )
    ocr_df, _, ocr_summary = build_pdf_content_review(
        files,
        pdf_results,
        use_ocr=True,
    )

    assert "Hasil Scan Terdeteksi" in non_ocr_df.columns
    assert "Resume Medis" not in non_ocr_df.columns
    assert "Hasil Scan Terdeteksi" not in ocr_df.columns
    assert "Resume Medis" in ocr_df.columns
    assert non_ocr_df.loc[0, "Status Akhir"] == "Lengkap"
    assert ocr_df.loc[0, "Status Akhir"] == "Lengkap"
    assert non_ocr_summary["Hasil scan"] == 1
    assert ocr_summary["Resume Medis"] == 1
