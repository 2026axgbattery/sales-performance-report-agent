"""공용 수치 계산 헬퍼 (F3 anomaly, F4 analytics 공통)."""
from __future__ import annotations


def pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0:
        return None
    return (current - base) / base * 100
