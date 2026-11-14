from datetime import date

from app.services.value_parsing import (
    dates_as_iso_strings,
    extract_dates_from_text,
    find_numeric_mentions,
    parse_date_token,
    select_threshold_values,
)


def test_parse_iso_and_month_name_dates() -> None:
    assert parse_date_token("2025-08-21") == date(2025, 8, 21)
    assert parse_date_token("2025/08/21") == date(2025, 8, 21)
    assert parse_date_token("August 21, 2025") == date(2025, 8, 21)
    assert parse_date_token("Aug 21 2025") == date(2025, 8, 21)
    assert parse_date_token("21 August 2025") == date(2025, 8, 21)


def test_ambiguous_numeric_dates_are_refused() -> None:
    assert parse_date_token("03/04/2025") is None
    assert parse_date_token("3-4-25") is None
    assert parse_date_token("not-a-date") is None


def test_extract_mixed_date_formats_from_passage() -> None:
    text = "Seen August 21, 2025 and again on 2025-09-18; ignore 03/04/2025."
    assert extract_dates_from_text(text) == [date(2025, 8, 21), date(2025, 9, 18)]
    assert dates_as_iso_strings(text) == ["2025-08-21", "2025-09-18"]


def test_comma_thousands_and_unit_aliases() -> None:
    text = "Absolute eosinophil count: 1,200 cells/uL and dose 250 µg."
    mentions = find_numeric_mentions(text)
    assert any(item.value == 1200.0 and "cells" in item.unit for item in mentions)
    assert any(item.value == 250.0 and item.unit == "mcg" for item in mentions)


def test_reference_range_numbers_are_excluded_from_threshold_selection() -> None:
    text = "Absolute eosinophil count: 420 cells/µL (reference range 0–500 cells/µL)."
    values, approx, reason = select_threshold_values(
        find_numeric_mentions(text), unit_substring="cells"
    )
    assert values == [420.0]
    assert approx is False
    assert reason is None


def test_approximate_numeric_language_flags_review() -> None:
    text = "Eosinophils approximately 350 cells/µL."
    values, approx, reason = select_threshold_values(
        find_numeric_mentions(text), unit_substring="cells"
    )
    assert values == [350.0]
    assert approx is True
    assert reason is not None


def test_seed_lab_formats_still_parse() -> None:
    text = "Collection date: 2025-08-21. Absolute eosinophil count: 420 cells/µL."
    assert extract_dates_from_text(text) == [date(2025, 8, 21)]
    values, approx, _ = select_threshold_values(
        find_numeric_mentions(text), unit_substring="cells"
    )
    assert values == [420.0]
    assert approx is False
