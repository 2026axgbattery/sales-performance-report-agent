import uuid
from datetime import datetime

import pytest

from app.db import Database
from app.services.analytics import get_overview


@pytest.fixture()
def db():
    database = Database(":memory:")
    yield database
    database.close()


def _make_batch(db, year, month) -> str:
    batch_id = str(uuid.uuid4())
    db.connection.execute(
        "INSERT INTO upload_batch (batch_id, upload_date, target_year, target_month) VALUES (?, ?, ?, ?)",
        [batch_id, datetime.now(), year, month],
    )
    return batch_id


def _insert_aggregated(db, batch_id, year, month, team, *, quantity, actual_amount, profit, plan_amount):
    db.connection.execute(
        """
        INSERT INTO aggregated_result (
            result_id, batch_id, year, month, team, product_group,
            quantity, actual_amount, profit, plan_amount
        ) VALUES (?, ?, ?, ?, ?, 'GB 소형', ?, ?, ?, ?)
        """,
        [str(uuid.uuid4()), batch_id, year, month, team, quantity, actual_amount, profit, plan_amount],
    )


def _insert_plan(db, team, year, month, account_item, amount):
    db.connection.execute(
        "INSERT INTO team_pl_record (record_id, file_id, batch_id, team, account_item, year, month, amount)"
        " VALUES (?, 'file-1', 'batch-1', ?, ?, ?, ?, ?)",
        [str(uuid.uuid4()), team, account_item, year, month, amount],
    )


def _insert_sales_plan(db, team, year, month, planned_amount):
    db.connection.execute(
        "INSERT INTO sales_plan_record (record_id, file_id, batch_id, team, year, month, planned_amount)"
        " VALUES (?, 'file-1', 'batch-1', ?, ?, ?, ?)",
        [str(uuid.uuid4()), team, year, month, planned_amount],
    )


def test_team_matrix_combines_gojeong_motive_into_sanjeon_group(db):
    batch_id = _make_batch(db, 2026, 8)
    _insert_aggregated(db, batch_id, 2026, 8, "고정형", quantity=100, actual_amount=1_000_000, profit=100_000, plan_amount=900_000)
    _insert_aggregated(db, batch_id, 2026, 8, "모티브", quantity=50, actual_amount=500_000, profit=20_000, plan_amount=600_000)
    _insert_aggregated(db, batch_id, 2026, 8, "차량대리점", quantity=200, actual_amount=2_000_000, profit=150_000, plan_amount=2_500_000)
    _insert_aggregated(db, batch_id, 2026, 8, "차량OE", quantity=80, actual_amount=800_000, profit=-50_000, plan_amount=900_000)

    _insert_plan(db, "고정형", 2026, 8, "매출수량", 90)
    _insert_plan(db, "고정형", 2026, 8, "영업이익(A)", 110_000)
    _insert_plan(db, "모티브", 2026, 8, "매출수량", 60)
    _insert_plan(db, "모티브", 2026, 8, "영업이익(A)", 30_000)

    overview = get_overview(db, batch_id)
    matrix = {row["team"]: row for row in overview["team_matrix"]}

    sanjeon_mtd = matrix["산전팀"]["mtd"]
    assert sanjeon_mtd["actual_quantity"] == 150
    assert sanjeon_mtd["plan_quantity"] == 150
    assert sanjeon_mtd["quantity_achievement_rate"] == pytest.approx(100.0)
    assert sanjeon_mtd["actual_amount"] == 1_500_000
    assert sanjeon_mtd["plan_amount"] == 1_500_000
    assert sanjeon_mtd["actual_profit"] == 120_000
    assert sanjeon_mtd["plan_profit"] == 140_000
    assert sanjeon_mtd["profit_diff"] == pytest.approx(-20_000)
    assert sanjeon_mtd["profit_achievement_rate"] == pytest.approx(120_000 / 140_000 * 100)
    assert sanjeon_mtd["plan_profit_rate"] == pytest.approx(140_000 / 1_500_000 * 100)

    total_mtd = matrix["합계"]["mtd"]
    # 합계는 산전팀(고정형+모티브)을 다시 더하지 않고 4개 실팀만 더한다.
    assert total_mtd["actual_amount"] == pytest.approx(1_000_000 + 500_000 + 2_000_000 + 800_000)
    assert total_mtd["actual_profit"] == pytest.approx(100_000 + 20_000 + 150_000 - 50_000)

    # team_pl_record가 없는 팀(차량대리점/차량OE)의 목표값은 None으로 남는다 — 0으로 대체하지 않는다.
    cha_mtd = matrix["차량대리점"]["mtd"]
    assert cha_mtd["plan_quantity"] is None
    assert cha_mtd["plan_profit"] is None
    assert cha_mtd["profit_achievement_rate"] is None


def test_team_matrix_ytd_sums_target_across_months(db):
    batch_id = _make_batch(db, 2026, 8)
    for month in (7, 8):
        _insert_aggregated(db, batch_id, 2026, month, "고정형", quantity=100, actual_amount=1_000_000, profit=100_000, plan_amount=900_000)
        _insert_plan(db, "고정형", 2026, month, "매출수량", 90)
        _insert_plan(db, "고정형", 2026, month, "영업이익(A)", 110_000)

    overview = get_overview(db, batch_id)
    matrix = {row["team"]: row for row in overview["team_matrix"]}

    ytd = matrix["고정형"]["ytd"]
    assert ytd["actual_quantity"] == 200
    assert ytd["plan_quantity"] == 180
    assert ytd["actual_profit"] == 200_000
    assert ytd["plan_profit"] == 220_000


def test_cumulative_plan_amount_includes_months_without_actual_upload(db):
    # 회귀 테스트: 사용자가 실측으로 발견한 버그 — 누계 목표 매출액이 실적이 업로드된
    # 달의 목표만 반영해 실제보다 작게 나왔다. sales_plan_record(연간 판매계획)는 실적
    # 업로드 여부와 무관하게 1~12월 전체 목표를 담고 있으므로, 실적이 없는 달(7월)의
    # 목표도 누계에 반드시 포함되어야 한다.
    batch_id = _make_batch(db, 2026, 8)
    # 8월만 실적이 업로드됐다(7월은 실적 배치가 없음).
    _insert_aggregated(db, batch_id, 2026, 8, "고정형", quantity=100, actual_amount=1_000_000, profit=100_000, plan_amount=900_000)
    # 판매계획 파일은 연간 데이터라 7월·8월 목표가 모두 존재한다.
    _insert_sales_plan(db, "고정형", 2026, 7, 800_000)
    _insert_sales_plan(db, "고정형", 2026, 8, 900_000)

    overview = get_overview(db, batch_id)
    cumulative_teams = {t["team"]: t for t in overview["cumulative"]["teams"]}
    # 7월 실적 배치가 없어도 7월 목표(800,000)가 누계 목표에 더해져야 한다.
    assert cumulative_teams["고정형"]["plan_amount"] == pytest.approx(800_000 + 900_000)

    ytd = {row["team"]: row for row in overview["team_matrix"]}["고정형"]["ytd"]
    assert ytd["plan_amount"] == pytest.approx(800_000 + 900_000)
