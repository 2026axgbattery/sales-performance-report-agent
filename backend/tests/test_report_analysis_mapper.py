"""F3 이상징후 결과 -> comment_generator.AnalysisRecord 매핑 회귀 테스트.

.docs/phase/phase_16_코멘트생성기연결.md — F7이 이제 app.services.comments(단문
사실 서술) 대신 comment_generator(서사형 문단)를 쓴다. comment_generator도 이
프로젝트의 "원인 추정 어휘 금지" 원칙을 지켜야 하므로 tests/test_comments.py와
같은 금칙어 검사를 여기서도 적용한다.
"""
from __future__ import annotations

import uuid

import pytest

from app.services.comment_generator import AccountCategory, generate_comment
from app.services.report_analysis_mapper import build_analysis_records
from app.services.thresholds import (
    METRIC_PLAN_ACHIEVEMENT,
    METRIC_PREV_MONTH,
    METRIC_PREV_YEAR,
    METRIC_PROFIT_TURN_NEGATIVE,
    METRIC_SGA_SURGE,
    METRIC_UNIT_PRICE,
)

FORBIDDEN_WORDS = ["때문", "원인", "인해", "탓"]


def _seed_batch(db, *, prev_month_available=True):
    batch_id = str(uuid.uuid4())
    db.connection.execute(
        "INSERT INTO upload_batch (batch_id, upload_date, target_year, target_month) VALUES (?, ?, ?, ?)",
        [batch_id, "2026-08-01", 2026, 8],
    )
    result_id = str(uuid.uuid4())
    db.connection.execute(
        """
        INSERT INTO aggregated_result (
            result_id, batch_id, year, month, team, product_group,
            quantity, actual_amount, profit, profit_rate, sga_amount, avg_unit_price,
            plan_amount, achievement_rate,
            prev_month_available, prev_month_amount, prev_month_profit,
            prev_month_sga_amount, prev_month_avg_unit_price,
            prev_year_month_available, prev_year_month_amount, prev_year_month_profit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            result_id, batch_id, 2026, 8, "차량대리점", "GB 소형",
            1000.0, 100_000.0, -5_000.0, -5.0, 20_000.0, 100.0,
            150_000.0, 66.7,
            prev_month_available, 120_000.0 if prev_month_available else None, 3_000.0 if prev_month_available else None,
            15_000.0 if prev_month_available else None, 90.0 if prev_month_available else None,
            False, None, None,
        ],
    )
    return batch_id, result_id


def _insert_flag(db, batch_id, result_id, *, metric_type, actual_value, threshold_value):
    flag_id = str(uuid.uuid4())
    db.connection.execute(
        """
        INSERT INTO anomaly_flag (flag_id, batch_id, result_id, team, product_group,
            metric_type, actual_value, threshold_value, impact_amount, is_confirmed_by_user)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [flag_id, batch_id, result_id, "차량대리점", "GB 소형", metric_type, actual_value, threshold_value, -20_000.0, False],
    )
    return flag_id


@pytest.mark.parametrize(
    "metric_type,actual_value,threshold_value,expected_category",
    [
        (METRIC_PREV_MONTH, -16.7, 10.0, AccountCategory.REVENUE),
        (METRIC_PREV_YEAR, 12.0, 15.0, AccountCategory.REVENUE),
        (METRIC_PLAN_ACHIEVEMENT, 66.7, 90.0, AccountCategory.REVENUE),
        (METRIC_PROFIT_TURN_NEGATIVE, -5000.0, 0.0, AccountCategory.OPERATING_PROFIT),
        (METRIC_UNIT_PRICE, 11.1, 5.0, AccountCategory.OTHER),
        (METRIC_SGA_SURGE, 33.3, 20.0, AccountCategory.SGA),
    ],
)
def test_build_analysis_records_maps_all_six_metric_types(
    test_db, metric_type, actual_value, threshold_value, expected_category
):
    batch_id, result_id = _seed_batch(test_db)
    _insert_flag(test_db, batch_id, result_id, metric_type=metric_type, actual_value=actual_value, threshold_value=threshold_value)

    records = build_analysis_records(test_db, batch_id)
    assert len(records) == 1
    flag_id, record = records[0]
    assert flag_id
    # 계획대비는 Phase 17부터 팀 단위로만 판정하므로(제품군 없이) 라벨도 팀명만 나온다.
    expected_label = "차량대리점" if metric_type == METRIC_PLAN_ACHIEVEMENT else "차량대리점 GB 소형"
    assert record.team_name == expected_label
    assert record.account_category == expected_category
    assert record.is_anomaly is True
    assert record.period_label == "2026년 8월"

    comment = generate_comment(record)
    for word in FORBIDDEN_WORDS:
        assert word not in comment, f"'{word}' 포함됨: {comment}"
    assert "차량대리점" in comment


def test_build_analysis_records_does_not_fabricate_mom_change_when_unavailable(test_db):
    # prev_month_available=False인 경우 계획대비/흑자전환처럼 전월 비교가 필요한 유형은
    # mom_change_pct가 None으로 남아야 한다(0%로 꾸며내지 않음).
    batch_id, result_id = _seed_batch(test_db, prev_month_available=False)
    _insert_flag(test_db, batch_id, result_id, metric_type=METRIC_PLAN_ACHIEVEMENT, actual_value=66.7, threshold_value=90.0)

    records = build_analysis_records(test_db, batch_id)
    _, record = records[0]
    assert record.mom_change_pct is None

    comment = generate_comment(record)
    assert "전월 비교 가능한 데이터가 없습니다" in comment
    for word in FORBIDDEN_WORDS:
        assert word not in comment


def test_prev_month_metric_never_has_none_mom_change(test_db):
    # METRIC_PREV_MONTH는 정의상 항상 전월 비교가 이미 존재해야 플래그가 생기므로
    # mom_change_pct가 actual_value 그대로 채워져야 한다.
    batch_id, result_id = _seed_batch(test_db)
    _insert_flag(test_db, batch_id, result_id, metric_type=METRIC_PREV_MONTH, actual_value=-16.7, threshold_value=10.0)

    _, record = build_analysis_records(test_db, batch_id)[0]
    assert record.mom_change_pct == pytest.approx(-16.7)


def test_unit_price_metric_fills_ytd_change_pct_from_cumulative_average(test_db):
    # Phase 20(.docs/phase/phase_20_단가변동누계평균통합.md, 사용자 확인) — 단가변동은
    # 폐지된 "누계평균대비"가 쓰던 ytd_change_pct 자리를 이어받아, F7 문장에도 연초~
    # 직전월 평균단가 대비 % 를 함께 서술해야 한다.
    batch_id, result_id = _seed_batch(test_db)
    # _seed_batch가 2026년 8월 배치를 만드므로, 연초~7월 평균단가 비교 기준이 되는
    # 직전월(7월) 행을 하나 더 심는다(같은 팀×제품군, avg_unit_price=80).
    test_db.connection.execute(
        """
        INSERT INTO aggregated_result (
            result_id, batch_id, year, month, team, product_group,
            quantity, actual_amount, profit, profit_rate, sga_amount, avg_unit_price
        ) VALUES (?, ?, 2026, 7, '차량대리점', 'GB 소형', 1000.0, 80_000.0, 0.0, 0.0, 0.0, 80.0)
        """,
        [str(uuid.uuid4()), batch_id],
    )
    _insert_flag(test_db, batch_id, result_id, metric_type=METRIC_UNIT_PRICE, actual_value=11.1, threshold_value=5.0)

    _, record = build_analysis_records(test_db, batch_id)[0]
    assert record.ytd_change_pct == pytest.approx((100.0 - 80.0) / 80.0 * 100)

    comment = generate_comment(record)
    assert "누계" in comment
    for word in FORBIDDEN_WORDS:
        assert word not in comment
