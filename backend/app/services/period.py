"""SAP 원본의 '기간/연도' 필드 파싱.

실제 원본 예시: "2026/007 7월 2026" (docs/03_데이터정제.md §4.1 참고)
Re-arrange 시트 수식:
  년 = RIGHT(D, 4) & "년"
  월 = TRIM(MID(D, 9, 4))
"""
from __future__ import annotations

import re


class PeriodParseError(ValueError):
    pass


def parse_period(raw: str) -> tuple[int, int]:
    """'기간/연도' 원본 문자열에서 (year, month)를 추출한다."""
    if not raw or not isinstance(raw, str):
        raise PeriodParseError(f"기간/연도 값을 파싱할 수 없습니다: {raw!r}")

    raw = raw.strip()
    if len(raw) < 12:
        raise PeriodParseError(f"기간/연도 형식이 예상과 다릅니다: {raw!r}")

    year_part = raw[-4:]
    # 1-based MID(D,9,4) == 0-based raw[8:12]
    month_part = raw[8:12].strip()

    if not year_part.isdigit():
        raise PeriodParseError(f"연도를 숫자로 해석할 수 없습니다: {raw!r}")

    month_digits = re.sub(r"\D", "", month_part)
    if not month_digits:
        raise PeriodParseError(f"월을 숫자로 해석할 수 없습니다: {raw!r}")

    year = int(year_part)
    month = int(month_digits)
    if not (1 <= month <= 12):
        raise PeriodParseError(f"월 값이 범위를 벗어났습니다({month}): {raw!r}")

    return year, month


def format_period(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"
