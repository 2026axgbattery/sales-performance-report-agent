"""get_anomalies()의 before_value/after_value 회귀 테스트.

사용자 요청("전월 얼마에서 당월 얼마로 얼마 변동, 이렇게 표현하면 좋겠어")에 따라
F5가 각 이상징후 유형이 실제로 비교한 두 원시 값을 그대로 보여줄 수 있어야 한다.
actual_value/impact_amount만으로는 유형마다 의미가 달라(예: 단가변동의 impact_amount는
매출액 차이지 단가 차이가 아님) 역산이 위험하므로, 유형별로 올바른 값을 재조회하는지
직접 검증한다.
"""
import uuid

import pytest

from app.db import Database
from app.services.analytics import get_anomalies
from app.services.anomaly import evaluate_anomalies


@pytest.fixture()
def db():
    database = Database(":memory:")
    yield database
    database.close()


def _seed_upload_batch(db, batch_id="batch-1", year=2026, month=7):
    db.connection.execute(
        "INSERT INTO upload_batch (batch_id, upload_date, target_year, target_month) VALUES (?, ?, ?, ?)",
        [batch_id, "2026-08-01", year, month],
    )


def _insert_result(db, batch_id="batch-1", team="차량대리점", product_group="GB 소형", **overrides):
    defaults = dict(
        result_id=str(uuid.uuid4()),
        batch_id=batch_id,
        year=2026,
        month=7,
        team=team,
        product_group=product_group,
        quantity=10.0,
        actual_amount=120000.0,
        profit=-5000.0,
        profit_rate=-4.2,
        sga_amount=8000.0,
        avg_unit_price=12000.0,
        plan_amount=None,
        achievement_rate=None,
        prev_month_available=True,
        prev_month_amount=100000.0,
        prev_month_profit=3000.0,
        prev_month_sga_amount=5000.0,
        prev_month_avg_unit_price=9000.0,
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


def _flags_by_metric(db, batch_id="batch-1"):
    return {a["metric_type"]: a for a in get_anomalies(db, batch_id) if a.get("product_group") == "GB 소형"}


def test_before_after_for_prev_month_prev_year_unit_price_sga_and_profit_turn(db):
    _seed_upload_batch(db)
    _insert_result(
        db,
        actual_amount=120000.0,  # +20% vs 전월 100,000 -> 전월대비 플래그
        prev_month_amount=100000.0,
        profit=-5000.0,  # 흑자(3000) -> 적자(-5000) 전환
        prev_month_profit=3000.0,
        sga_amount=8000.0,  # +60% vs 전월 5,000 -> 판관비급증 플래그
        prev_month_sga_amount=5000.0,
        avg_unit_price=12000.0,  # +33% vs 전월 9,000 -> 단가변동 플래그
        prev_month_avg_unit_price=9000.0,
        prev_year_month_available=True,
        prev_year_month_amount=80000.0,  # +50% -> 전년대비 플래그
    )
    evaluate_anomalies(db, "batch-1")
    flags = _flags_by_metric(db)

    assert flags["전월대비"]["before_value"] == pytest.approx(100000.0)
    assert flags["전월대비"]["after_value"] == pytest.approx(120000.0)

    assert flags["전년대비"]["before_value"] == pytest.approx(80000.0)
    assert flags["전년대비"]["after_value"] == pytest.approx(120000.0)

    assert flags["단가변동"]["before_value"] == pytest.approx(9000.0)
    assert flags["단가변동"]["after_value"] == pytest.approx(12000.0)

    assert flags["판관비급증"]["before_value"] == pytest.approx(5000.0)
    assert flags["판관비급증"]["after_value"] == pytest.approx(8000.0)

    assert flags["흑자전환"]["before_value"] == pytest.approx(3000.0)
    assert flags["흑자전환"]["after_value"] == pytest.approx(-5000.0)


def test_unit_price_flag_also_exposes_cumulative_before_value(db):
    # Phase 20(.docs/phase/phase_20_단가변동누계평균통합.md, 사용자 확인) — 단가변동
    # 플래그는 전월 비교(before_value/after_value)와 별도로 누계평균 비교값
    # (cumulative_before_value)도 함께 노출해야 "당월/전월/누계"를 한꺼번에 보여줄 수 있다.
    _seed_upload_batch(db, year=2026, month=7)
    _insert_result(db, month=5, avg_unit_price=10000.0, prev_month_available=False)
    _insert_result(db, month=6, avg_unit_price=10000.0, prev_month_available=False)
    _insert_result(
        db, month=7, avg_unit_price=10700.0, prev_month_available=True, prev_month_avg_unit_price=10650.0,
    )
    evaluate_anomalies(db, "batch-1")

    flags = [
        a for a in get_anomalies(db, "batch-1")
        if a["metric_type"] == "단가변동" and a["team"] == "차량대리점"
    ]
    assert len(flags) == 1
    assert flags[0]["before_value"] == pytest.approx(10650.0)  # 전월 평균단가
    assert flags[0]["after_value"] == pytest.approx(10700.0)  # 당월 평균단가
    assert flags[0]["cumulative_before_value"] == pytest.approx(10000.0)  # 연초~6월 평균단가


def test_non_unit_price_flags_have_no_cumulative_before_value(db):
    _seed_upload_batch(db)
    _insert_result(db, actual_amount=120000.0, prev_month_amount=100000.0)
    evaluate_anomalies(db, "batch-1")
    flags = _flags_by_metric(db)
    assert flags["전월대비"]["cumulative_before_value"] is None


def test_before_after_for_plan_achievement_uses_team_totals(db):
    _seed_upload_batch(db)
    _insert_result(db, product_group="GB 소형", actual_amount=60000.0, plan_amount=100000.0)
    _insert_result(db, product_group="AGM", actual_amount=10000.0, plan_amount=100000.0)
    evaluate_anomalies(db, "batch-1")

    flags = [a for a in get_anomalies(db, "batch-1") if a["metric_type"] == "계획대비"]
    assert len(flags) == 1
    assert flags[0]["before_value"] == pytest.approx(100000.0)  # 팀 계획
    assert flags[0]["after_value"] == pytest.approx(70000.0)  # 팀 실적 합계(60,000+10,000)


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


def test_before_after_for_pl_item_plan_uses_unit_price_for_sales_and_total_for_cost(db):
    # 실제로 겪은 버그: 계획(팀) 매출수량이 함께 업로드돼 있으면(=plan_unit이 모든
    # 항목에서 계산 가능해지면) 매출원가처럼 총액 기준이어야 하는 항목까지 "총액÷팀
    # 계획수량"이라는 작은 단가로 뒤바뀌어, F5 화면에 "0.0억"으로만 보이는 실제 화면
    # 오류가 있었다 — 계획 매출수량을 반드시 함께 넣어 이 케이스를 재현한다.
    _seed_upload_batch(db)
    _insert_result(db, team="차량대리점", plan_amount=None)
    _insert_refined_row(db, "batch-1", 2026, 7, "차량대리점", quantity=100, sales_final=1_000_000, cogs_final=555_000)
    _insert_plan(db, "차량대리점", 2026, 7, "매출수량", 100)
    _insert_plan(db, "차량대리점", 2026, 7, "매출원가(A)Tot", 500_000)  # +11%
    evaluate_anomalies(db, "batch-1")

    flags = {a["product_group"]: a for a in get_anomalies(db, "batch-1") if a["metric_type"] == "손익항목계획대비"}
    # 매출원가는 총액 기준(계획 500,000 vs 실적 555,000)이어야 한다 — plan_unit이
    # 있어도(5,000원 = 500,000/100) 쓰면 안 된다(사용자 확인: "단위당 매출액"만 예외).
    assert flags["매출원가"]["before_value"] == pytest.approx(500_000)
    assert flags["매출원가"]["after_value"] == pytest.approx(555_000)
