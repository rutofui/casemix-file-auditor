from __future__ import annotations

from pathlib import Path
import tempfile

from src.pdf_renamer import build_rename_summary, rename_pdfs_by_sep


def _write_pdf(path: Path, text: str) -> None:
    import fitz

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(str(path))
    doc.close()


def test_rename_pdf_to_sep_from_digital_text() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        sep = "0132R0770526V001270"
        source = root / "random-name.pdf"
        _write_pdf(source, f"Nomor SEP {sep}")

        results = rename_pdfs_by_sep(str(root))

        assert len(results) == 1
        assert results[0].status == "Berhasil"
        assert results[0].new_name == f"{sep}.pdf"
        assert not source.exists()
        assert (root / f"{sep}.pdf").exists()


def test_rename_adds_suffix_when_sep_name_exists() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        sep = "0132R0770526V001270"
        existing = root / f"{sep}.pdf"
        source = root / "incoming.pdf"
        _write_pdf(existing, f"Nomor SEP {sep}")
        _write_pdf(source, f"Nomor SEP {sep}")

        results = rename_pdfs_by_sep(str(root))
        rows_by_old_name = {result.old_name: result for result in results}

        assert rows_by_old_name[f"{sep}.pdf"].status == "Dilewati"
        assert rows_by_old_name["incoming.pdf"].status == "Berhasil"
        assert rows_by_old_name["incoming.pdf"].new_name == f"{sep}_2.pdf"
        assert (root / f"{sep}_2.pdf").exists()


def test_rename_scans_subfolders_recursively() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        sep = "0132R0770526V001271"
        source = root / "sub" / "claim.pdf"
        _write_pdf(source, f"Surat Eligibilitas Peserta\n{sep}")

        results = rename_pdfs_by_sep(str(root))

        assert results[0].status == "Berhasil"
        assert (root / "sub" / f"{sep}.pdf").exists()


def test_rename_skips_file_already_named_sep() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        sep = "0132R0770526V001272"
        source = root / f"{sep}.pdf"
        _write_pdf(source, f"Nomor SEP {sep}")

        results = rename_pdfs_by_sep(str(root))

        assert results[0].status == "Dilewati"
        assert "sudah sesuai" in " ".join(results[0].notes).lower()
        assert source.exists()


def test_rename_skips_pdf_without_sep_text() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = root / "no-sep.pdf"
        _write_pdf(source, "Tidak ada nomor klaim di halaman ini.")

        results = rename_pdfs_by_sep(str(root))

        assert results[0].status == "Dilewati"
        assert results[0].sep_detected == ""
        assert source.exists()


def test_rename_reports_broken_pdf_as_failed() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = root / "broken.pdf"
        source.write_text("bukan pdf", encoding="utf-8")

        results = rename_pdfs_by_sep(str(root))

        assert results[0].status == "Gagal"
        assert source.exists()


def test_rename_summary_counts_statuses() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_pdf(root / "ok.pdf", "Nomor SEP 0132R0770526V001273")
        _write_pdf(root / "skip.pdf", "Tanpa SEP")
        (root / "broken.pdf").write_text("bukan pdf", encoding="utf-8")

        summary = build_rename_summary(rename_pdfs_by_sep(str(root)))

        assert summary["Total PDF"] == 3
        assert summary["Berhasil"] == 1
        assert summary["Dilewati"] == 1
        assert summary["Gagal"] == 1
