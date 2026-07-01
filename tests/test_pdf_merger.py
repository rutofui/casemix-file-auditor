from __future__ import annotations

from pathlib import Path
import tempfile

from src.config import PDFCheckConfig
from src.pdf_merger import merge_pdf_folders


def _write_pdf(path: Path, page_texts: list[str]) -> None:
    import fitz

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), text, fontsize=11)
    doc.save(str(path))
    doc.close()


def _read_pdf_pages(path: Path) -> list[str]:
    import fitz

    doc = fitz.open(str(path))
    try:
        return [doc.load_page(index).get_text("text") for index in range(doc.page_count)]
    finally:
        doc.close()


def test_merge_only_processes_matching_names_and_reports_single_sided_files() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_a = root / "a"
        source_b = root / "b"
        output = root / "out"
        _write_pdf(source_a / "same.pdf", ["SURAT ELIGIBILITAS PESERTA"])
        _write_pdf(source_b / "same.pdf", ["Berkas Klaim Individual Pasien"])
        _write_pdf(source_a / "only-a.pdf", ["A"])
        _write_pdf(source_b / "only-b.pdf", ["B"])

        results = merge_pdf_folders(
            str(source_a),
            str(source_b),
            str(output),
            config=PDFCheckConfig(use_ocr=False),
        )

        status_by_name = {result.file_name: result.status for result in results}
        assert status_by_name["same.pdf"] == "Berhasil"
        assert status_by_name["only-a.pdf"] == "Dilewati"
        assert status_by_name["only-b.pdf"] == "Dilewati"
        assert (output / "same.pdf").exists()
        assert not (output / "only-a.pdf").exists()
        assert not (output / "only-b.pdf").exists()


def test_merge_skips_duplicate_basename_in_one_source() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_a = root / "a"
        source_b = root / "b"
        output = root / "out"
        _write_pdf(source_a / "x" / "same.pdf", ["A1"])
        _write_pdf(source_a / "y" / "same.pdf", ["A2"])
        _write_pdf(source_b / "same.pdf", ["B"])

        results = merge_pdf_folders(
            str(source_a),
            str(source_b),
            str(output),
            config=PDFCheckConfig(use_ocr=False),
        )

        assert len(results) == 1
        assert results[0].status == "Dilewati"
        assert "duplikat" in " ".join(results[0].notes).lower()


def test_merge_orders_pages_by_claim_document_category() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_a = root / "a"
        source_b = root / "b"
        output = root / "out"
        _write_pdf(
            source_a / "claim.pdf",
            [
                "SURAT ELIGIBILITAS PESERTA\nNomor SEP 0132R0770526V001270",
                "RESUME MEDIS\nRingkasan Pulang",
                "CATATAN LAIN",
            ],
        )
        _write_pdf(
            source_b / "claim.pdf",
            [
                "Berkas Klaim Individual Pasien",
                "PEMERIKSAAN RADIOLOGI\nRontgen Thorax",
                "HASIL PEMERIKSAAN LABORATORIUM",
                "Rincian Tagihan Barang Jasa Fasilitas",
            ],
        )

        results = merge_pdf_folders(
            str(source_a),
            str(source_b),
            str(output),
            config=PDFCheckConfig(use_ocr=False),
        )

        assert results[0].status == "Berhasil"
        output_pages = _read_pdf_pages(output / "claim.pdf")
        expected_markers = [
            "Berkas Klaim Individual Pasien",
            "SURAT ELIGIBILITAS PESERTA",
            "RESUME MEDIS",
            "HASIL PEMERIKSAAN LABORATORIUM",
            "PEMERIKSAAN RADIOLOGI",
            "Rincian Tagihan",
            "CATATAN LAIN",
        ]
        assert [marker in text for marker, text in zip(expected_markers, output_pages)] == [
            True,
            True,
            True,
            True,
            True,
            True,
            True,
        ]


def test_merge_respects_overwrite_policy() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_a = root / "a"
        source_b = root / "b"
        output = root / "out"
        _write_pdf(source_a / "same.pdf", ["SURAT ELIGIBILITAS PESERTA"])
        _write_pdf(source_b / "same.pdf", ["Berkas Klaim Individual Pasien"])
        output.mkdir()
        _write_pdf(output / "same.pdf", ["OLD"])

        skipped = merge_pdf_folders(
            str(source_a),
            str(source_b),
            str(output),
            overwrite=False,
            config=PDFCheckConfig(use_ocr=False),
        )
        overwritten = merge_pdf_folders(
            str(source_a),
            str(source_b),
            str(output),
            overwrite=True,
            config=PDFCheckConfig(use_ocr=False),
        )

        assert skipped[0].status == "Dilewati"
        assert overwritten[0].status == "Berhasil"
        output_text = "\n".join(_read_pdf_pages(output / "same.pdf"))
        assert "OLD" not in output_text
        assert "Berkas Klaim Individual Pasien" in output_text
