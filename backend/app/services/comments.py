"""F7. 이상징후별 자동 코멘트 생성기.

PRD F7: "코멘트는 수치 기반 사실 서술에 한정하고, 원인 추정은 하지 않는다
(원인 파악은 담당자의 몫 — F8)". 그래서 이 모듈은 anomaly_flag의 실제값·
임계값·영향 금액만으로 문장을 조립하고, 원인을 암시하는 표현(때문에/원인/
인해/탓 등)을 쓰지 않는다.
"""
from __future__ import annotations

from app.services.thresholds import (
    METRIC_PLAN_ACHIEVEMENT,
    METRIC_PREV_MONTH,
    METRIC_PREV_YEAR,
    METRIC_PROFIT_TURN_NEGATIVE,
    METRIC_SGA_SURGE,
    METRIC_UNIT_PRICE,
)


def _label(team: str, product_group: str | None) -> str:
    return f"{team} {product_group}" if product_group else f"{team}(미매핑)"


def _pct(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def generate_comment(flag: dict) -> str:
    """anomaly_flag 1건(dict: team, product_group, metric_type, actual_value,
    threshold_value, impact_amount)을 받아 사실 서술 문장 하나를 반환한다."""
    team = flag["team"]
    group = flag.get("product_group")
    metric_type = flag["metric_type"]
    actual_value = flag.get("actual_value")
    impact_amount = flag.get("impact_amount")
    label = _label(team, group)

    if metric_type == METRIC_PREV_MONTH:
        return f"{label} 매출 전월 대비 {_pct(actual_value)} 변동 (영향 금액 {impact_amount:,.0f}원)"
    if metric_type == METRIC_PREV_YEAR:
        return f"{label} 매출 전년 동월 대비 {_pct(actual_value)} 변동 (영향 금액 {impact_amount:,.0f}원)"
    if metric_type == METRIC_PLAN_ACHIEVEMENT:
        return f"{label} 매출 계획 대비 {actual_value:.1f}% 달성"
    if metric_type == METRIC_PROFIT_TURN_NEGATIVE:
        return f"{label} 영업이익이 흑자에서 적자로 전환 ({actual_value:,.0f}원)"
    if metric_type == METRIC_UNIT_PRICE:
        return f"{label} 평균단가 전월 대비 {_pct(actual_value)} 변동"
    if metric_type == METRIC_SGA_SURGE:
        return f"{label} 판관비 전월 대비 {_pct(actual_value)} 증가"
    return f"{label} {metric_type} {_pct(actual_value)}"
