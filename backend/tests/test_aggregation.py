import uuid
from datetime import datetime

import pytest

from app.db import Database
from app.services.aggregation import compute_aggregates_for_batch


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


def _insert_refined_row(db, batch_id, year, month, team, product_group, sales_final, profit, sga_final, quantity=10.0):
    db.connection.execute(
        """
        INSERT INTO refined_sales_record (
            record_id, batch_id, file_id, year, month, team, customer_code, customer_name,
            product_code, product_desc, product_group, is_mapped,
            sales_provisional, sales_discount, sales_adjustment, sales_final_ops, sales_other,
            sales_pre_adjust, plan_adjustment, sales_final,
            raw_material_sunyeon, raw_material_gyeongyeon, raw_material_calcium,
            raw_material_nickel, raw_material_lithium, raw_material_total,
            main_material_jeonjo, main_material_kaba, main_material_gyeorimpan, main_material_total,
            cogs_pre_adjust, cogs_final, sga_pre_adjust, sga_final,
            operating_profit_pre_adjust, operating_profit_final, quantity, inventory_diff,
            is_calc_error, calc_error_reason
        ) VALUES (?, ?, 'file-1', ?, ?, ?, 'C0000001', 'test', 'P0001', 'desc', ?, true,
                   0,0,0,0,0, 0,0, ?,
                   0,0,0,0,0,0, 0,0,0,0,
                   0,0,0, ?,
                   0, ?, ?, 0,
                   false, NULL)
        """,
        [
            str(uuid.uuid4()), batch_id, year, month, team, product_group,
            sales_final,
            sga_final,
            profit,
            quantity,
        ],
    )


def test_compute_aggregates_links_previous_month_and_year(db):
    prev_year_batch = _make_batch(db, 2025, 7)
    _insert_refined_row(db, prev_year_batch, 2025, 7, "차량대리점", "GB 소형", sales_final=500000, profit=60000, sga_final=40000)
    compute_aggregates_for_batch(db, prev_year_batch)

    prev_month_batch = _make_batch(db, 2026, 6)
    _insert_refined_row(db, prev_month_batch, 2026, 6, "차량대리점", "GB 소형", sales_final=600000, profit=72000, sga_final=48000)
    compute_aggregates_for_batch(db, prev_month_batch)

    current_batch = _make_batch(db, 2026, 7)
    _insert_refined_row(db, current_batch, 2026, 7, "차량대리점", "GB 소형", sales_final=717885, profit=179989, sga_final=50000)
    # 모티브는 전년 동월 데이터가 없는 그룹 (비교 불가 확인용)
    _insert_refined_row(db, current_batch, 2026, 7, "모티브", "원자재", sales_final=50000, profit=15000, sga_final=5000)

    count = compute_aggregates_for_batch(db, current_batch)
    assert count == 2

    row = db.connection.execute(
        "SELECT prev_month_available, prev_month_amount, prev_year_month_available, prev_year_month_amount, "
        "avg_unit_price, profit_rate "
        "FROM aggregated_result WHERE batch_id = ? AND team = '차량대리점'",
        [current_batch],
    ).fetchone()
    assert row[0] is True
    assert row[1] == 600000
    assert row[2] is True
    assert row[3] == 500000
    assert row[4] == pytest.approx(717885 / 10)  # quantity=10
    assert row[5] == pytest.approx(179989 / 717885 * 100)

    motive_row = db.connection.execute(
        "SELECT prev_year_month_available FROM aggregated_result WHERE batch_id = ? AND team = '모티브'",
        [current_batch],
    ).fetchone()
    assert motive_row[0] is False  # 전년 동월 데이터 없음 -> 비교 불가


def test_compute_aggregates_joins_plan_amount(db):
    batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", "GB 소형", sales_final=717885, profit=179989, sga_final=50000)
    db.connection.execute(
        "INSERT INTO sales_plan_record (record_id, file_id, batch_id, team, year, month, planned_amount) "
        "VALUES (?, 'file-plan', ?, '차량대리점', 2026, 7, 900000)",
        [str(uuid.uuid4()), batch_id],
    )

    compute_aggregates_for_batch(db, batch_id)

    row = db.connection.execute(
        "SELECT plan_amount, achievement_rate FROM aggregated_result WHERE batch_id = ?", [batch_id]
    ).fetchone()
    assert row[0] == 900000
    assert row[1] == pytest.approx(717885 / 900000 * 100)


def test_compute_aggregates_recompute_is_idempotent(db):
    batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", "GB 소형", sales_final=100000, profit=10000, sga_final=5000)

    compute_aggregates_for_batch(db, batch_id)
    compute_aggregates_for_batch(db, batch_id)  # 재계산해도 중복 저장되지 않아야 함

    count = db.connection.execute(
        "SELECT COUNT(*) FROM aggregated_result WHERE batch_id = ?", [batch_id]
    ).fetchone()[0]
    assert count == 1
