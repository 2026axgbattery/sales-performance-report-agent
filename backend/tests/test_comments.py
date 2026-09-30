import pytest

from app.services.comments import generate_comment
from app.services.thresholds import (
    METRIC_PLAN_ACHIEVEMENT,
    METRIC_PREV_MONTH,
    METRIC_PREV_YEAR,
    METRIC_PROFIT_TURN_NEGATIVE,
    METRIC_SGA_SURGE,
    METRIC_UNIT_PRICE,
)

FORBIDDEN_WORDS = ["때문", "원인", "인해", "탓", "추정", "으로 보임", "것으로 판단"]


def _flag(**overrides):
    base = {
        "team": "차량대리점",
        "product_group": "GB 소형",
        "metric_type": METRIC_PREV_MONTH,
        "actual_value": -18.0,
        "threshold_value": 10.0,
        "impact_amount": -127885.0,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "metric_type,actual_value",
    [
        (METRIC_PREV_MONTH, -18.0),
        (METRIC_PREV_YEAR, 12.0),
        (METRIC_PLAN_ACHIEVEMENT, 82.0),
        (METRIC_PROFIT_TURN_NEGATIVE, -5000.0),
        (METRIC_UNIT_PRICE, 7.5),
        (METRIC_SGA_SURGE, 25.0),
    ],
)
def test_comment_contains_no_cause_inference_wording(metric_type, actual_value):
    comment = generate_comment(_flag(metric_type=metric_type, actual_value=actual_value))
    for word in FORBIDDEN_WORDS:
        assert word not in comment, f"'{word}' 포함됨: {comment}"


def test_comment_states_team_and_numeric_fact():
    comment = generate_comment(_flag(metric_type=METRIC_PLAN_ACHIEVEMENT, actual_value=82.0))
    assert "차량대리점" in comment
    assert "82.0%" in comment


def test_comment_handles_unmapped_product_group():
    comment = generate_comment(_flag(product_group=None))
    assert "미매핑" in comment
