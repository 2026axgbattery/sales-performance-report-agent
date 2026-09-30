"""F3 전(前)단계 — 팀×제품군 단위 집계 (AggregatedResult).

정제된 실적(refined_sales_record)을 팀·제품군 단위로 합산하고, 계획 데이터·
직전월/전년동월 집계 결과를 조회해 비교 기준값을 함께 저장한다.
이상징후 판정(6개 기준)은 app.services.anomaly에서 이 결과를 바탕으로 수행한다.
"""
from __future__ import annotations

import uuid


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _prev_year_month(year: int, month: int) -> tuple[int, int]:
    return year - 1, month


def compute_aggregates_for_batch(db, batch_id: str) -> int:
    period = db.batch_period(batch_id)
    if period is None:
        raise ValueError(f"존재하지 않는 batch_id 입니다: {batch_id}")
    year, month = period

    db.connection.execute("DELETE FROM aggregated_result WHERE batch_id = ?", [batch_id])

    groups = db.connection.execute(
        """
        SELECT team, product_group,
               SUM(quantity), SUM(sales_final), SUM(operating_profit_final), SUM(sga_final)
        FROM refined_sales_record
        WHERE batch_id = ?
        GROUP BY team, product_group
        """,
        [batch_id],
    ).fetchall()

    prev_y, prev_m = _prev_month(year, month)
    py_y, py_m = _prev_year_month(year, month)

    count = 0
    for team, product_group, quantity, actual_amount, profit, sga_amount in groups:
        quantity = quantity or 0.0
        actual_amount = actual_amount or 0.0
        profit = profit or 0.0
        sga_amount = sga_amount or 0.0

        avg_unit_price = (actual_amount / quantity) if quantity else None
        profit_rate = (profit / actual_amount * 100) if actual_amount else None

        # sales_plan_record는 거래처×제품군 단위로 여러 행이 있으므로(.docs/03_데이터정제.md
        # §6.1) 팀 단위로 합산해야 한다 — 단일 행 조회가 아니다.
        plan_row = db.connection.execute(
            "SELECT SUM(planned_amount) FROM sales_plan_record WHERE team = ? AND year = ? AND month = ?",
            [team, year, month],
        ).fetchone()
        plan_amount = plan_row[0] if plan_row and plan_row[0] is not None else None
        achievement_rate = (actual_amount / plan_amount * 100) if plan_amount else None

        prev_month_row = db.connection.execute(
            """
            SELECT actual_amount, profit, sga_amount, avg_unit_price FROM aggregated_result
            WHERE team = ? AND product_group IS NOT DISTINCT FROM ? AND year = ? AND month = ?
            """,
            [team, product_group, prev_y, prev_m],
        ).fetchone()
        prev_year_row = db.connection.execute(
            """
            SELECT actual_amount, profit FROM aggregated_result
            WHERE team = ? AND product_group IS NOT DISTINCT FROM ? AND year = ? AND month = ?
            """,
            [team, product_group, py_y, py_m],
        ).fetchone()

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
                result_id,
                batch_id,
                year,
                month,
                team,
                product_group,
                quantity,
                actual_amount,
                profit,
                profit_rate,
                sga_amount,
                avg_unit_price,
                plan_amount,
                achievement_rate,
                prev_month_row is not None,
                prev_month_row[0] if prev_month_row else None,
                prev_month_row[1] if prev_month_row else None,
                prev_month_row[2] if prev_month_row else None,
                prev_month_row[3] if prev_month_row else None,
                prev_year_row is not None,
                prev_year_row[0] if prev_year_row else None,
                prev_year_row[1] if prev_year_row else None,
            ],
        )
        count += 1
    return count
