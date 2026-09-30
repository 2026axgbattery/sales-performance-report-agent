import uuid

import pytest

from app.db import Database
from app.services.anomaly import evaluate_anomalies
from app.services.thresholds import (
    METRIC_PL_ITEM_PLAN,
    METRIC_PLAN_ACHIEVEMENT,
    METRIC_PREV_MONTH,
    METRIC_PREV_YEAR,
    METRIC_PROFIT_TURN_NEGATIVE,
    METRIC_SGA_SURGE,
    METRIC_UNIT_PRICE,
)


@pytest.fixture()
def db():
    database = Database(":memory:")
    yield database
    database.close()


def _insert_result(db, batch_id="batch-1", team="차량대리점", product_group="GB 소형", **overrides):
    defaults = dict(
        result_id=str(uuid.uuid4()),
        batch_id=batch_id,
        year=2026,
        month=7,
        team=team,
        product_group=product_group,
        quantity=10.0,
        actual_amount=100000.0,
        profit=10000.0,
        profit_rate=10.0,
        sga_amount=5000.0,
        avg_unit_price=10000.0,
        plan_amount=None,
        achievement_rate=None,
        prev_month_available=False,
        prev_month_amount=None,
        prev_month_profit=None,
        prev_month_sga_amount=None,
        prev_month_avg_unit_price=None,
        prev_year_month_available=False,
        prev_year_month_amount=None,
        prev_year_month_profit=None,
    )
    defaults.update(overrides)
    columns = ", ".join(defaults.keys())
    placeholders = ", ".join(["?"] * len(defaults))
    db.connection.execute(
        f"INSERT INTO aggregated_result ({columns}) VALUES ({placeholders})",
        list(defaults.values()),
    )
    return defaults["result_id"]


def _flags_for(db, result_id):
    rows = db.connection.execute(
        "SELECT metric_type, actual_value, impact_amount FROM anomaly_flag WHERE result_id = ?",
        [result_id],
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def _seed_upload_batch(db, batch_id="batch-1", year=2026, month=7):
    # anomaly.py가 누계평균대비 계산에 db.batch_period(batch_id)로 연/월을 조회하므로,
    # 이 기준을 쓰는 테스트는 upload_batch 행이 있어야 한다(기존 테스트들은 이 값이
    # 없어도 그냥 그 판단 기준만 건너뛰므로 영향 없음).
    db.connection.execute(
        "INSERT INTO upload_batch (batch_id, upload_date, target_year, target_month) VALUES (?, ?, ?, ?)",
        [batch_id, "2026-08-01", year, month],
    )


def test_prev_month_change_over_threshold_flags(db):
    rid = _insert_result(
        db,
        actual_amount=120000.0,
        prev_month_available=True,
        prev_month_amount=100000.0,  # +20% > 10% 임계치
    )
    evaluate_anomalies(db, "batch-1")
    flags = _flags_for(db, rid)
    assert METRIC_PREV_MONTH in flags
    assert flags[METRIC_PREV_MONTH][0] == pytest.approx(20.0)


def test_prev_month_change_under_threshold_does_not_flag(db):
    rid = _insert_result(
        db,
        actual_amount=105000.0,
        prev_month_available=True,
        prev_month_amount=100000.0,  # +5% < 10% 임계치
    )
    evaluate_anomalies(db, "batch-1")
    assert METRIC_PREV_MONTH not in _flags_for(db, rid)


def test_prev_year_unavailable_is_skipped_not_flagged(db):
    rid = _insert_result(db, prev_year_month_available=False)
    evaluate_anomalies(db, "batch-1")
    assert METRIC_PREV_YEAR not in _flags_for(db, rid)


def test_prev_year_change_over_threshold_flags(db):
    rid = _insert_result(
        db,
        actual_amount=130000.0,
        prev_year_month_available=True,
        prev_year_month_amount=100000.0,  # +30% > 15% 임계치
    )
    evaluate_anomalies(db, "batch-1")
    flags = _flags_for(db, rid)
    assert METRIC_PREV_YEAR in flags
    assert flags[METRIC_PREV_YEAR][0] == pytest.approx(30.0)


def test_plan_achievement_below_low_bound_flags(db):
    rid = _insert_result(db, actual_amount=80000.0, plan_amount=100000.0, achievement_rate=80.0)
    evaluate_anomalies(db, "batch-1")
    assert METRIC_PLAN_ACHIEVEMENT in _flags_for(db, rid)


def test_plan_achievement_above_high_bound_flags(db):
    rid = _insert_result(db, actual_amount=130000.0, plan_amount=100000.0, achievement_rate=130.0)
    evaluate_anomalies(db, "batch-1")
    assert METRIC_PLAN_ACHIEVEMENT in _flags_for(db, rid)


def test_plan_achievement_within_range_does_not_flag(db):
    rid = _insert_result(db, actual_amount=100000.0, plan_amount=100000.0, achievement_rate=100.0)
    evaluate_anomalies(db, "batch-1")
    assert METRIC_PLAN_ACHIEVEMENT not in _flags_for(db, rid)


def test_profit_turn_negative_flags_only_on_actual_turn(db):
    rid = _insert_result(
        db, profit=-5000.0, prev_month_available=True, prev_month_profit=3000.0
    )
    evaluate_anomalies(db, "batch-1")
    assert METRIC_PROFIT_TURN_NEGATIVE in _flags_for(db, rid)


def test_profit_still_negative_is_not_a_new_turn(db):
    rid = _insert_result(
        db, profit=-5000.0, prev_month_available=True, prev_month_profit=-1000.0
    )
    evaluate_anomalies(db, "batch-1")
    assert METRIC_PROFIT_TURN_NEGATIVE not in _flags_for(db, rid)


def test_unit_price_change_over_threshold_flags(db):
    rid = _insert_result(
        db,
        avg_unit_price=9000.0,
        prev_month_available=True,
        prev_month_avg_unit_price=10000.0,  # -10% > 5% 임계치
    )
    evaluate_anomalies(db, "batch-1")
    assert METRIC_UNIT_PRICE in _flags_for(db, rid)


def test_sga_surge_flags_only_on_increase(db):
    rid = _insert_result(
        db,
        sga_amount=6500.0,
        prev_month_available=True,
        prev_month_sga_amount=5000.0,  # +30% >= 20% 임계치
    )
    evaluate_anomalies(db, "batch-1")
    assert METRIC_SGA_SURGE in _flags_for(db, rid)


def test_sga_decrease_does_not_flag_even_if_large(db):
    rid = _insert_result(
        db,
        sga_amount=1000.0,
        prev_month_available=True,
        prev_month_sga_amount=5000.0,  # -80% 이지만 급증 규칙은 증가 방향만 본다
    )
    evaluate_anomalies(db, "batch-1")
    assert METRIC_SGA_SURGE not in _flags_for(db, rid)


def test_evaluate_anomalies_is_idempotent_on_recompute(db):
    rid = _insert_result(
        db, actual_amount=120000.0, prev_month_available=True, prev_month_amount=100000.0
    )
    evaluate_anomalies(db, "batch-1")
    evaluate_anomalies(db, "batch-1")  # 재계산 시 중복 플래그가 쌓이지 않아야 함
    count = db.connection.execute(
        "SELECT COUNT(*) FROM anomaly_flag WHERE result_id = ?", [rid]
    ).fetchone()[0]
    assert count == 1


# ── Phase 17: 계획대비는 팀 단위로만, 누계평균대비는 팀×제품군 단위로 신설 ──
# (.docs/phase/phase_17_이상징후판정범위조정.md, 사용자 확인)


def test_plan_achievement_is_evaluated_per_team_not_per_product_group(db):
    # 팀 계획 100,000 중 GB소형 60,000 + AGM 40,000 = 팀 합계 100,000(달성률 100%, 정상
    # 범위)인데, 예전 버그처럼 제품군 단위로 "제품군 실적 ÷ 팀 전체 계획"을 계산하면
    # GB소형은 60%, AGM은 40%로 둘 다 하한(90%) 미달로 잘못 플래그된다.
    rid1 = _insert_result(
        db, product_group="GB 소형", actual_amount=60000.0, plan_amount=100000.0, achievement_rate=60.0
    )
    rid2 = _insert_result(
        db, product_group="AGM", actual_amount=40000.0, plan_amount=100000.0, achievement_rate=40.0
    )
    evaluate_anomalies(db, "batch-1")
    assert METRIC_PLAN_ACHIEVEMENT not in _flags_for(db, rid1)
    assert METRIC_PLAN_ACHIEVEMENT not in _flags_for(db, rid2)


def test_plan_achievement_team_level_flags_once_with_team_wide_rate(db):
    # 팀 합계 실적(60,000+10,000=70,000) ÷ 팀 계획(100,000) = 70% < 하한(90%) → 팀당 1건만 플래그.
    _insert_result(db, product_group="GB 소형", actual_amount=60000.0, plan_amount=100000.0)
    _insert_result(db, product_group="AGM", actual_amount=10000.0, plan_amount=100000.0)
    evaluate_anomalies(db, "batch-1")
    rows = db.connection.execute(
        "SELECT actual_value FROM anomaly_flag WHERE metric_type = ?", [METRIC_PLAN_ACHIEVEMENT]
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == pytest.approx(70.0)


# ── Phase 20: "누계평균대비" 독립 기준 폐지, "단가변동"에 전월+누계 통합 판정 ──
# (.docs/phase/phase_20_단가변동누계평균통합.md, 사용자 확인 — "누계 평균대비는 별도의
# 버튼으로 분류하지 말고... 단가 변동에서만 비교해보자")


def test_unit_price_cumulative_change_over_threshold_flags_even_when_prev_month_is_stable(db):
    _seed_upload_batch(db, year=2026, month=7)
    _insert_result(db, month=5, avg_unit_price=10000.0)
    _insert_result(db, month=6, avg_unit_price=10000.0)
    rid = _insert_result(
        db,
        month=7,
        avg_unit_price=10700.0,
        prev_month_available=True,
        prev_month_avg_unit_price=10650.0,  # 전월 대비 +0.47% (5% 임계치 미달)
    )
    evaluate_anomalies(db, "batch-1")
    # 연초~6월 평균단가(10,000) 대비로는 +7% > 5% 임계치라 플래그돼야 한다.
    assert METRIC_UNIT_PRICE in _flags_for(db, rid)


def test_unit_price_both_prev_and_cumulative_under_threshold_does_not_flag(db):
    _seed_upload_batch(db, year=2026, month=7)
    _insert_result(db, month=6, avg_unit_price=10000.0)
    rid = _insert_result(
        db,
        month=7,
        avg_unit_price=10200.0,  # 누계평균(10,000) 대비 +2%
        prev_month_available=True,
        prev_month_avg_unit_price=10100.0,  # 전월 대비 +0.99%
    )
    evaluate_anomalies(db, "batch-1")
    assert METRIC_UNIT_PRICE not in _flags_for(db, rid)


def test_unit_price_without_cumulative_data_still_uses_prev_month(db):
    # 1월(직전월 집계 자체가 없음)이라 누계평균 비교가 불가능해도, 전월 대비만으로는
    # 정상 판정해야 한다(비교 불가를 0으로 대체하지 않을 뿐 다른 비교까지 막지 않음).
    _seed_upload_batch(db, year=2026, month=1)
    rid = _insert_result(
        db, month=1, avg_unit_price=9000.0, prev_month_available=True, prev_month_avg_unit_price=10000.0
    )
    evaluate_anomalies(db, "batch-1")
    assert METRIC_UNIT_PRICE in _flags_for(db, rid)  # 전월 대비 -10% > 5%


# ── Phase 18: 손익항목계획대비 (.docs/phase/phase_18_손익항목계획대비판정.md) ──


def _insert_refined_row(db, batch_id, year, month, team, *, quantity, sales_final, cogs_final):
    db.connection.execute(
        """
        INSERT INTO refined_sales_record (
            record_id, batch_id, file_id, year, month, team, customer_code, customer_name,
            product_code, product_desc, product_group, product_group_1, product_group_2, is_mapped,
            sales_final, quantity, cogs_final, is_calc_error
        ) VALUES (?, ?, 'file-1', ?, ?, ?, 'C0000001', 'test',
                   'P0001', 'desc', 'GB 소형', 'GB', 'GB 소형계열', true,
                   ?, ?, ?, false)
        """,
        [str(uuid.uuid4()), batch_id, year, month, team, sales_final, quantity, cogs_final],
    )


def _insert_plan(db, team, year, month, account_item, amount):
    db.connection.execute(
        "INSERT INTO team_pl_record (record_id, file_id, batch_id, team, account_item, year, month, amount)"
        " VALUES (?, 'file-1', 'batch-1', ?, ?, ?, ?, ?)",
        [str(uuid.uuid4()), team, account_item, year, month, amount],
    )


def test_pl_item_plan_deviation_over_threshold_flags(db):
    _seed_upload_batch(db, year=2026, month=7)
    _insert_result(db, team="차량대리점", plan_amount=None)
    _insert_refined_row(
        db, "batch-1", 2026, 7, "차량대리점", quantity=100, sales_final=1_000_000, cogs_final=555_000
    )
    _insert_plan(db, "차량대리점", 2026, 7, "매출원가(A)Tot", 500_000)  # +11% > 10% 임계치

    evaluate_anomalies(db, "batch-1")

    rows = db.connection.execute(
        "SELECT team, product_group, actual_value, impact_amount FROM anomaly_flag "
        "WHERE metric_type = ? AND product_group = ?",
        [METRIC_PL_ITEM_PLAN, "매출원가"],
    ).fetchall()
    # 이 fixture는 material_total/labor_total/expense_total을 채우지 않아 "기타(상품구매,
    # 재고실사차이 등)"(other_cogs = cogs_final - 그 셋의 합)이 우연히 cogs_final과 같은
    # 값이 돼 같이 플래그된다 — cogs_final(매출원가)만 따로 골라 검증한다.
    assert len(rows) == 1
    team, product_group, actual_value, impact_amount = rows[0]
    assert team == "차량대리점"
    assert product_group == "매출원가"  # pl_comparison.LINE_ITEMS의 cogs_final 라벨
    assert actual_value == pytest.approx(11.0)
    assert impact_amount == pytest.approx(55_000.0)


def test_pl_item_plan_deviation_under_threshold_does_not_flag(db):
    _seed_upload_batch(db, year=2026, month=7)
    _insert_result(db, team="차량대리점", plan_amount=None)
    _insert_refined_row(
        db, "batch-1", 2026, 7, "차량대리점", quantity=100, sales_final=1_000_000, cogs_final=510_000
    )
    _insert_plan(db, "차량대리점", 2026, 7, "매출원가(A)Tot", 500_000)  # +2% < 10% 임계치

    evaluate_anomalies(db, "batch-1")

    rows = db.connection.execute(
        "SELECT COUNT(*) FROM anomaly_flag WHERE metric_type = ?", [METRIC_PL_ITEM_PLAN]
    ).fetchone()
    assert rows[0] == 0


def test_pl_item_plan_deviation_skipped_without_upload_batch(db):
    # upload_batch 행이 없어 batch_period를 못 구하는 배치(일부 단위 테스트의 lightweight
    # 시나리오)에서는 get_pl_comparison이 예외를 던지므로, 이 패스 자체를 건너뛴다
    # (다른 6개 기준과 달리 새로 추가된 패스라 회귀로 크래시나지 않는지 별도 확인).
    _insert_result(db, team="차량대리점", plan_amount=None)
    evaluate_anomalies(db, "batch-1")  # 예외 없이 끝나야 한다
    rows = db.connection.execute(
        "SELECT COUNT(*) FROM anomaly_flag WHERE metric_type = ?", [METRIC_PL_ITEM_PLAN]
    ).fetchone()
    assert rows[0] == 0
