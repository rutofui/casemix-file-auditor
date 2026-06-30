from __future__ import annotations

from src.config import code_present_in_text


class TestCodePresentInText:
    def test_exact_standalone_match(self):
        assert code_present_in_text("DX: E86 OTHER", "E86") is True

    def test_dotted_code_standalone_match(self):
        assert code_present_in_text("PROC 90.59 DONE", "90.59") is True

    def test_dotted_code_not_substring_of_longer_decimal(self):
        assert code_present_in_text("PROC 190.591 DONE", "90.59") is False

    def test_dotted_code_not_substring_when_trailing_digits(self):
        assert code_present_in_text("PROC 90.591 DONE", "90.59") is False

    def test_code_at_start_of_text(self):
        assert code_present_in_text("E86 OTHER", "E86") is True

    def test_code_at_end_of_text(self):
        assert code_present_in_text("OTHER E86", "E86") is True

    def test_code_not_present(self):
        assert code_present_in_text("NO MATCHING CODE HERE", "E86") is False

    def test_empty_code_returns_false(self):
        assert code_present_in_text("ANY TEXT", "") is False

    def test_case_insensitive_match(self):
        assert code_present_in_text("dx: e86 other", "E86") is True

    def test_code_not_substring_of_longer_alpha_code(self):
        assert code_present_in_text("DX: E860 OTHER", "E86") is False
