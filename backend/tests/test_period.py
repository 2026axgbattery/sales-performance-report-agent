import pytest

from app.services.period import PeriodParseError, format_period, parse_period


def test_parse_period_matches_verified_excel_example():
    # docs/03_데이터정제.md §4.1 실제 검증 예시
    year, month = parse_period("2026/007 7월 2026")
    assert (year, month) == (2026, 7)


def test_parse_period_double_digit_month():
    year, month = parse_period("2025/012 12월 2025")
    assert (year, month) == (2025, 12)


def test_parse_period_invalid_raises():
    with pytest.raises(PeriodParseError):
        parse_period("bad")


def test_format_period():
    assert format_period(2026, 7) == "2026-07"
