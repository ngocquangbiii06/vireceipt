import unicodedata

import pytest

from vireceipt.normalize import (
    digits_only,
    levenshtein,
    norm_loose,
    norm_text,
    parse_money,
    similarity,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.234.000", 1234000),
        ("1,234,000", 1234000),
        ("1 234 000", 1234000),
        ("32.000đ", 32000),
        ("32,000 VND", 32000),
        ("32.000₫", 32000),
        ("-5.000", 5000),
        ("120k", 120000),
        ("0", 0),
        ("12,5", None),
        ("abc", None),
        ("", None),
    ],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected


def test_norm_text_composes_unicode_and_collapses_spaces():
    decomposed = unicodedata.normalize("NFD", "  Sữa   tươi ")
    assert norm_text(decomposed) == "Sữa tươi"


def test_norm_loose_drops_case_and_punctuation_but_keeps_diacritics():
    assert norm_loose("CỬA HÀNG, Minh-Anh!") == "cửa hàng minh anh"
    assert norm_loose("Cà phê") != norm_loose("Ca phe")


def test_digits_only():
    assert digits_only("028.3812 3456") == "02838123456"


def test_levenshtein_and_similarity():
    assert levenshtein("kitten", "sitting") == 3
    assert similarity("Bánh mì", "BÁNH MÌ") == 1.0
    assert similarity("", "") == 1.0
    assert 0.9 < similarity("Cà phê sữa đá", "Cà phê sữa đả") < 1.0
