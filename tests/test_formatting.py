"""Test dei moduli puri di formattazione."""

from datetime import timedelta

import pytest

from calliope.transcription.formatting import format_timedelta, split_message


class TestSplitMessage:
    def test_empty(self):
        assert split_message("", 4096) == []

    def test_short_single_part(self):
        assert split_message("ciao mondo", 4096) == ["ciao mondo"]

    def test_exact_boundary(self):
        text = "a" * 4096
        parts = split_message(text, 4096)
        assert len(parts) == 1
        assert parts[0] == text

    def test_over_boundary_splits(self):
        text = "word " * 2000  # 10000 caratteri
        parts = split_message(text, 4096)
        assert len(parts) > 1
        assert all(len(p) <= 4096 for p in parts)
        # ricostruzione senza perdita di parole
        assert " ".join(parts).split() == text.split()

    def test_no_spaces_long_word(self):
        text = "x" * 5000
        parts = split_message(text, 4096)
        assert len(parts) == 2
        assert all(len(p) <= 4096 for p in parts)
        assert "".join(parts) == text

    def test_unicode_preserved(self):
        text = "àèìòù " * 1000
        parts = split_message(text, 4096)
        assert "".join("".join(parts).split()) == "".join(text.split())


class TestFormatTimedelta:
    @pytest.mark.parametrize(
        "seconds, expected",
        [
            (0, "0s"),
            (-5, "0s"),
            (5, "5s"),
            (65, "1m 5s"),
            (3600, "1h"),
            (3661, "1h 1m 1s"),
            (90061, "1d 1h 1m 1s"),
        ],
    )
    def test_format(self, seconds, expected):
        assert format_timedelta(timedelta(seconds=seconds)) == expected
