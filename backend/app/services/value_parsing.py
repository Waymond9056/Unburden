"""Deterministic date and numeric extraction for Milestone 3.

Shared by retrieval (detail capture) and verification (threshold / window math).
Ambiguous or approximate values are refused rather than guessed — callers route
those cases to NEEDS_REVIEW. NLI/BERT must not perform these comparisons.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

# --- Dates -----------------------------------------------------------------

# Unambiguous formats only. Never accept bare MM/DD/YYYY or DD/MM/YYYY.
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_YMD_SLASH_RE = re.compile(r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b")
_MONTH_NAME_RE = re.compile(
    r"\b("
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"
    r"|"
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+("
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r")\s+(\d{4})\b",
    flags=re.IGNORECASE,
)

# Ambiguous numeric slash/dash dates — detect so we can refuse them.
_AMBIGUOUS_NUMERIC_DATE_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
)

_MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date_token(token: str) -> date | None:
    """Parse a single date token. Returns None for unparsable/ambiguous input."""
    text = (token or "").strip()
    if not text:
        return None

    iso = _ISO_DATE_RE.fullmatch(text)
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))

    ymd = _YMD_SLASH_RE.fullmatch(text)
    if ymd:
        return _safe_date(int(ymd.group(1)), int(ymd.group(2)), int(ymd.group(3)))

    # Reject ambiguous numeric dates instead of guessing locale order.
    if _AMBIGUOUS_NUMERIC_DATE_RE.fullmatch(text):
        return None

    month_match = _MONTH_NAME_RE.fullmatch(text)
    if month_match:
        if month_match.group(1):
            month = _MONTH_ALIASES.get(month_match.group(1).lower())
            day = int(month_match.group(2))
            year = int(month_match.group(3))
        else:
            day = int(month_match.group(4))
            month = _MONTH_ALIASES.get(month_match.group(5).lower())
            year = int(month_match.group(6))
        if month is None:
            return None
        return _safe_date(year, month, day)

    # Last-resort allow-list via strptime for a few exact shapes.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def extract_dates_from_text(text: str) -> list[date]:
    """Return unique parseable dates found in text, in appearance order."""
    if not text:
        return []

    spans: list[tuple[int, int, date]] = []

    for match in _ISO_DATE_RE.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed:
            spans.append((match.start(), match.end(), parsed))

    for match in _YMD_SLASH_RE.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed:
            spans.append((match.start(), match.end(), parsed))

    for match in _MONTH_NAME_RE.finditer(text):
        parsed = parse_date_token(match.group(0))
        if parsed:
            spans.append((match.start(), match.end(), parsed))

    spans.sort(key=lambda item: item[0])
    ordered: list[date] = []
    seen: set[date] = set()
    for _, _, parsed in spans:
        if parsed not in seen:
            seen.add(parsed)
            ordered.append(parsed)
    return ordered


def text_contains_parseable_date(text: str) -> bool:
    return bool(extract_dates_from_text(text))


def dates_as_iso_strings(text: str) -> list[str]:
    return [item.isoformat() for item in extract_dates_from_text(text)]


# --- Numbers / units -------------------------------------------------------

_UNIT_PATTERN = (
    r"(?P<unit>"
    r"cells/(?:µL|uL|ul)|"
    r"mcg|µg|ug|"
    r"mg|"
    r"IU|"
    r"mL|ml|"
    r"%"
    r")"
)

_NUMBER_CORE = r"(?P<value>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"

# Optional dose pair like 500/50 before the unit.
NUMBER_WITH_UNITS_PATTERN = re.compile(
    rf"\b{_NUMBER_CORE}(?:/(?P<alt>\d+(?:\.\d+)?))?\s*{_UNIT_PATTERN}\b",
    flags=re.IGNORECASE,
)

_APPROX_PREFIX_RE = re.compile(
    r"(?:"
    r"~|≈|approximately|approx\.?|about|around|roughly|"
    r">=|<=|≥|≤|>|<|"
    r"greater\s+than|more\s+than|at\s+least|no\s+less\s+than|"
    r"less\s+than|under|below|up\s+to"
    r")\s*$",
    flags=re.IGNORECASE,
)

_REFERENCE_RANGE_RE = re.compile(
    r"\b(?:reference|ref(?:erence)?|normal)\s+ranges?\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class NumericMention:
    value: float
    unit: str
    raw: str
    start: int
    end: int
    approximate: bool
    in_reference_range: bool


def _parse_number_token(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _normalize_unit(unit: str) -> str:
    lowered = unit.strip().lower().replace("µ", "u")
    aliases = {
        "ug": "mcg",
        "μg": "mcg",
        "cells/ul": "cells/ul",
        "ml": "ml",
        "iu": "iu",
        "%": "%",
        "mg": "mg",
        "mcg": "mcg",
    }
    return aliases.get(lowered, lowered)


def _reference_range_windows(text: str) -> list[tuple[int, int]]:
    """Character spans that follow a reference/normal-range label."""
    windows: list[tuple[int, int]] = []
    for match in _REFERENCE_RANGE_RE.finditer(text):
        windows.append((match.start(), min(len(text), match.end() + 48)))
    return windows


def find_numeric_mentions(text: str) -> list[NumericMention]:
    if not text:
        return []

    reference_windows = _reference_range_windows(text)
    mentions: list[NumericMention] = []
    for match in NUMBER_WITH_UNITS_PATTERN.finditer(text):
        value = _parse_number_token(match.group("value"))
        if value is None:
            continue
        unit = _normalize_unit(match.group("unit"))
        prefix = text[max(0, match.start() - 24) : match.start()]
        approximate = bool(_APPROX_PREFIX_RE.search(prefix.rstrip()))
        in_reference = any(
            start <= match.start() < end for start, end in reference_windows
        )
        mentions.append(
            NumericMention(
                value=value,
                unit=unit,
                raw=match.group(0),
                start=match.start(),
                end=match.end(),
                approximate=approximate,
                in_reference_range=in_reference,
            )
        )
    return mentions


def unit_matches(unit: str, unit_substring: str) -> bool:
    return unit_substring.lower() in unit.lower()


def select_threshold_values(
    mentions: list[NumericMention],
    unit_substring: str,
) -> tuple[list[float], bool, str | None]:
    """Pick numeric values for a ≥ threshold check.

    Returns (values, had_approximate_only, review_reason).
    Reference-range numbers are excluded. Approximate-only evidence is not
    auto-accepted or auto-rejected.
    """
    matched = [
        item
        for item in mentions
        if unit_matches(item.unit, unit_substring) and not item.in_reference_range
    ]
    if not matched:
        # Fall back: allow reference-range exclusion to empty the list even if
        # raw mentions existed — caller treats empty as needs_review.
        return [], False, None

    exact = [item for item in matched if not item.approximate]
    approx = [item for item in matched if item.approximate]
    if exact:
        return [item.value for item in exact], False, None
    if approx:
        return [item.value for item in approx], True, (
            "Only approximate numeric language was found; exact quantitative "
            "comparison needs clinician review."
        )
    return [], False, None


def format_numeric_mention_strings(text: str) -> list[str]:
    """Raw mention strings for retrieval detail capture (stable for citations)."""
    return list(dict.fromkeys(item.raw for item in find_numeric_mentions(text)))
