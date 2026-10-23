"""Text and money normalisation shared by labelling, extraction and evaluation."""

import re
import unicodedata

_WS = re.compile(r"\s+")
_CURRENCY = re.compile(r"(vnđ|vnd|đồng|dong|đ|₫|d)$")


def norm_text(s: str) -> str:
    """NFC-normalise, trim and collapse whitespace. Case and punctuation are kept."""
    return _WS.sub(" ", unicodedata.normalize("NFC", s)).strip()


def norm_loose(s: str) -> str:
    """Like `norm_text`, then casefold and drop punctuation. Vietnamese diacritics are kept."""
    s = norm_text(s).casefold()
    s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
    return _WS.sub(" ", s).strip()


def digits_only(s: str) -> str:
    """Keep only the digits of `s` (phone numbers, tax codes)."""
    return "".join(ch for ch in s if ch.isdigit())


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def similarity(a: str, b: str) -> float:
    """1 - normalised edit distance between the loose forms of `a` and `b`, in [0, 1]."""
    a, b = norm_loose(a), norm_loose(b)
    if not a and not b:
        return 1.0
    return 1.0 - levenshtein(a, b) / max(len(a), len(b))


def parse_money(s: str) -> int | None:
    """Parse a printed VND amount such as '1.234.000đ', '32,000 VND' or '120k'.

    Dots, commas and spaces are thousands separators (the dong has no minor unit).
    A leading minus sign is ignored: discounts are stored as positive numbers.
    Returns None when the text is not an amount.
    """
    t = norm_text(s).casefold().replace(" ", "").lstrip("-+")
    t = _CURRENCY.sub("", t)
    multiplier = 1
    if t.endswith("k"):
        multiplier, t = 1000, t[:-1]
    if not t or not re.fullmatch(r"\d+([.,]\d{3})*", t):
        return None
    return int(re.sub(r"[.,]", "", t)) * multiplier
