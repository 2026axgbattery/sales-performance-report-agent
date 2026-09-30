"""F4 Overview / F5 이상징후 하이라이트가 사용하는 조회 전용 쿼리.

F3(app.services.aggregation, anomaly)가 이미 계산·저장한 aggregated_result /
anomaly_flag 테이블을 읽기만 한다 — 여기서 새로 계산하지 않는다.
"""
from __future__ import annotations

from app.services.anomaly import cumulative_prior_average
from app.services.metrics import pct_change
from app.services.pl_item_analysis import UNIT_BASIS_KEYS, find_team_item_deviation
from app.services.thresholds import (
    METRIC_PL_ITEM_PLAN,
    METRIC_PLAN_ACHIEVEMENT,
    METRIC_PREV_MONTH,
    METRIC_PREV_YEAR,
    METRIC_PROFIT_TURN_NEGATIVE,
    METRIC_SGA_SURGE,
    METRIC_UNIT_PRICE,
)

TEAM_ROLLUP_SQL = """
    SELECT
        team,
        SUM(quantity) AS quantity,
        SUM(actual_amount) AS actual_amount,
        SUM(profit) AS profit,
        SUM(sga_amount) AS sga_amount,
        -- plan_amount is a team-level value duplicated onto every product_group row of
        -- that team, so it must be taken once (MAX), never summed across the rows.
        MAX(plan_amount) AS plan_amount,
        BOOL_OR(prev_month_available) AS prev_month_available,
        SUM(CASE WHEN prev_month_available THEN prev_month_amount ELSE 0 END) AS prev_month_amount,
        SUM(CASE WHEN prev_month_available THEN prev_month_profit ELSE 0 END) AS prev_month_profit,
        BOOL_OR(prev_year_month_available) AS prev_year_month_available,
        SUM(CASE WHEN prev_year_month_available THEN prev_year_month_amount ELSE 0 END) AS prev_year_month_amount,
        SUM(CASE WHEN prev_year_month_available THEN prev_year_month_profit ELSE 0 END) AS prev_year_month_profit
    FROM aggregated_result
    WHERE batch_id = ?
    GROUP BY team
"""


def _team_row_to_dict(row) -> dict:
    (
        team,
        quantity,
        actual_amount,
        profit,
        sga_amount,
        plan_amount,
        prev_month_available,
        prev_month_amount,
        prev_month_profit,
        prev_year_month_available,
        prev_year_month_amount,
        prev_year_month_profit,
    ) = row

    return {
        "team": team,
        "quantity": quantity or 0.0,
        "actual_amount": actual_amount or 0.0,
        "profit": profit or 0.0,
        "profit_rate": (profit / actual_amount * 100) if actual_amount else None,
        "sga_amount": sga_amount or 0.0,
        "plan_amount": plan_amount,
        "achievement_rate": (actual_amount / plan_amount * 100) if (plan_amount and actual_amount is not None) else None,
        "prev_month_available": bool(prev_month_available),
        "prev_month_amount": prev_month_amount if prev_month_available else None,
        "prev_month_profit": prev_month_profit if prev_month_available else None,
        "prev_month_change_pct": pct_change(actual_amount, prev_month_amount) if prev_month_available else None,
        "prev_month_profit_change_pct": pct_change(profit, prev_month_profit) if prev_month_available else None,
        "prev_year_month_available": bool(prev_year_month_available),
        "prev_year_month_amount": prev_year_month_amount if prev_year_month_available else None,
        "prev_year_change_pct": pct_change(actual_amount, prev_year_month_amount) if prev_year_month_available else None,
    }


def get_overview(db, batch_id: str) -> dict | None:
    period = db.batch_period(batch_id)
    if period is None:
        return None
    year, month = period

    team_rows = db.connection.execute(TEAM_ROLLUP_SQL, [batch_id]).fetchall()
    teams = [_team_row_to_dict(r) for r in team_rows]
    teams.sort(key=lambda t: t["actual_amount"], reverse=True)
    cumulative = get_cumulative_teams(db, year, month)

    total_quantity = sum(t["quantity"] for t in teams)
    total_actual = sum(t["actual_amount"] for t in teams)
    total_profit = sum(t["profit"] for t in teams)
    total_plan = sum(t["plan_amount"] for t in teams if t["plan_amount"] is not None) or None
    prev_month_total = sum(
        t["prev_month_amount"] for t in teams if t["prev_month_available"] and t["prev_month_amount"] is not None
    )
    prev_month_profit_total = sum(
        t["prev_month_profit"] for t in teams if t["prev_month_available"] and t["prev_month_profit"] is not None
    )
    any_prev_month = any(t["prev_month_available"] for t in teams)
    prev_year_total = sum(
        t["prev_year_month_amount"]
        for t in teams
        if t["prev_year_month_available"] and t["prev_year_month_amount"] is not None
    )
    any_prev_year = any(t["prev_year_month_available"] for t in teams)

    summary = {
        "total_quantity": total_quantity,
        "total_actual_amount": total_actual,
        "total_profit": total_profit,
        "total_profit_rate": (total_profit / total_actual * 100) if total_actual else None,
        "total_plan_amount": total_plan,
        "total_achievement_rate": (total_actual / total_plan * 100) if total_plan else None,
        "prev_month_change_pct": pct_change(total_actual, prev_month_total) if any_prev_month else None,
        "prev_year_change_pct": pct_change(total_actual, prev_year_total) if any_prev_year else None,
        "prev_month_available": any_prev_month,
        "prev_month_total_amount": prev_month_total if any_prev_month else None,
        "prev_month_total_profit": prev_month_profit_total if any_prev_month else None,
        "prev_month_total_profit_rate": (
            (prev_month_profit_total / prev_month_total * 100) if any_prev_month and prev_month_total else None
        ),
    }

    return {
        "batch_id": batch_id,
        "year": year,
        "month": month,
        "summary": summary,
        "teams": teams,
        "cumulative": cumulative,
        "team_matrix": get_team_matrix(db, year, month, teams, cumulative["teams"]),
    }


# ── 팀별 목표·실적·대비 통합 매트릭스 (당월 + 누계, 수량·매출액·영업이익) ──
# 사용자 확인: 목표 수량·목표 영업이익은 team_pl_record(손익계산서 업로드)의
# "매출수량"·"영업이익(A)" 계정과목 금액을 사용한다(app.services.pl_comparison의
# PLAN_ITEM_GROUPS와 동일한 계정과목명 — 이 값이 실제 파일에서 검증된 이름이다).
# 목표 매출액은 기존 aggregated_result.plan_amount(sales_plan_record 근거)를 그대로 쓴다.
PLAN_TARGET_TEAMS = ["고정형", "모티브", "차량대리점", "차량OE"]
PLAN_TARGET_ACCOUNT_ITEMS = {"quantity": "매출수량", "profit": "영업이익(A)"}

# "산전팀"은 실적 데이터(aggregated_result.team)에는 존재하지 않는 합성 그룹이다
# (PRD F4 ③ 제품군별 분석 — 차량대리점/차량OE/산전(모티브+고정형 통합) 3그룹 체계와
# 일치, 사용자 확인). 개별 팀 행 다음에 합산 행으로 표시한다.
TEAM_MATRIX_GROUPS: list[tuple[str, list[str], bool]] = [
    ("고정형", ["고정형"], False),
    ("모티브", ["모티브"], False),
    ("산전팀", ["모티브", "고정형"], True),
    ("차량대리점", ["차량대리점"], False),
    ("차량OE", ["차량OE"], False),
]


def _team_pl_targets(db, year: int, months: list[int]) -> dict[str, dict[str, float | None]]:
    month_placeholders = ", ".join(["?"] * len(months))
    rows = db.connection.execute(
        f"""
        SELECT team, account_item, SUM(amount) FROM team_pl_record
        WHERE year = ? AND month IN ({month_placeholders}) AND account_item IN (?, ?)
        GROUP BY team, account_item
        """,
        [
            year,
            *months,
            PLAN_TARGET_ACCOUNT_ITEMS["quantity"],
            PLAN_TARGET_ACCOUNT_ITEMS["profit"],
        ],
    ).fetchall()
    targets: dict[str, dict[str, float | None]] = {
        team: {"quantity": None, "profit": None} for team in PLAN_TARGET_TEAMS
    }
    for team, account_item, amount in rows:
        if team not in targets:
            continue
        if account_item == PLAN_TARGET_ACCOUNT_ITEMS["quantity"]:
            targets[team]["quantity"] = amount
        elif account_item == PLAN_TARGET_ACCOUNT_ITEMS["profit"]:
            targets[team]["profit"] = amount
    return targets


def _build_group_metrics(
    team_names: list[str],
    actual_by_team: dict[str, dict],
    plan_targets: dict[str, dict[str, float | None]],
) -> dict:
    quantity = sum(actual_by_team[t]["quantity"] for t in team_names)
    actual_amount = sum(actual_by_team[t]["actual_amount"] for t in team_names)
    profit = sum(actual_by_team[t]["profit"] for t in team_names)

    plan_amounts = [actual_by_team[t]["plan_amount"] for t in team_names]
    plan_amount = sum(p for p in plan_amounts if p is not None) if any(p is not None for p in plan_amounts) else None

    plan_quantities = [plan_targets[t]["quantity"] for t in team_names]
    plan_quantity = (
        sum(p for p in plan_quantities if p is not None) if any(p is not None for p in plan_quantities) else None
    )

    plan_profits = [plan_targets[t]["profit"] for t in team_names]
    plan_profit = sum(p for p in plan_profits if p is not None) if any(p is not None for p in plan_profits) else None

    return {
        "plan_quantity": plan_quantity,
        "actual_quantity": quantity,
        "quantity_achievement_rate": (quantity / plan_quantity * 100) if plan_quantity else None,
        "plan_amount": plan_amount,
        "actual_amount": actual_amount,
        "amount_achievement_rate": (actual_amount / plan_amount * 100) if plan_amount else None,
        "plan_profit": plan_profit,
        "actual_profit": profit,
        "plan_profit_rate": (plan_profit / plan_amount * 100) if plan_amount and plan_profit is not None else None,
        "actual_profit_rate": (profit / actual_amount * 100) if actual_amount else None,
        "profit_diff": (profit - plan_profit) if plan_profit is not None else None,
        "profit_achievement_rate": (profit / plan_profit * 100) if plan_profit else None,
    }


def get_team_matrix(db, year: int, month: int, mtd_teams: list[dict], ytd_teams: list[dict]) -> list[dict]:
    mtd_by_team = {t["team"]: t for t in mtd_teams}
    ytd_by_team = {t["team"]: t for t in ytd_teams}
    # 해당 배치에 실적이 아예 없는 팀도 0으로 채워야 그룹(산전팀·합계) 합산이 깨지지 않는다.
    for name in PLAN_TARGET_TEAMS:
        mtd_by_team.setdefault(name, {"quantity": 0.0, "actual_amount": 0.0, "profit": 0.0, "plan_amount": None})
        ytd_by_team.setdefault(name, {"quantity": 0.0, "actual_amount": 0.0, "profit": 0.0, "plan_amount": None})

    mtd_targets = _team_pl_targets(db, year, [month])
    ytd_targets = _team_pl_targets(db, year, list(range(1, month + 1)))

    rows = [
        {
            "team": name,
            "is_synthetic": synthetic,
            "mtd": _build_group_metrics(members, mtd_by_team, mtd_targets),
            "ytd": _build_group_metrics(members, ytd_by_team, ytd_targets),
        }
        for name, members, synthetic in TEAM_MATRIX_GROUPS
    ]
    rows.append(
        {
            "team": "합계",
            "is_synthetic": False,
            "mtd": _build_group_metrics(PLAN_TARGET_TEAMS, mtd_by_team, mtd_targets),
            "ytd": _build_group_metrics(PLAN_TARGET_TEAMS, ytd_by_team, ytd_targets),
        }
    )
    return rows


# 팀별 목표 대비 실적 표 옆의 "누계 실적" — 해당 연도 1월부터 선택월까지 aggregated_result를
# 팀 단위로 합산한다(사용자 요청, CLAUDE.md에 기록된 "MTD만 저장하며 YTD는 저장하지 않는다 —
# 여러 배치를 조회해 계산할 예정"이 가리키던 바로 그 기능). 실적(수량·매출액·영업이익)은
# 실제로 업로드된 배치가 있는 달만 존재하므로 그대로 합산한다.
CUMULATIVE_TEAM_SQL = """
    WITH monthly AS (
        SELECT team, month,
               SUM(quantity) AS quantity,
               SUM(actual_amount) AS actual_amount,
               SUM(profit) AS profit
        FROM aggregated_result
        WHERE year = ? AND month <= ?
        GROUP BY team, month
    )
    SELECT team,
           SUM(quantity) AS quantity,
           SUM(actual_amount) AS actual_amount,
           SUM(profit) AS profit
    FROM monthly
    GROUP BY team
"""


def _cumulative_plan_amount_by_team(db, year: int, up_to_month: int) -> dict[str, float]:
    # 목표 매출액(plan_amount)은 aggregated_result가 아니라 sales_plan_record(연간 판매계획
    # 파일)에서 직접 월 범위로 합산한다. aggregated_result의 plan_amount는 실적이 업로드된
    # 달의 행에만 존재하므로(팀 단위 값이 제품군 행마다 중복 저장), 그 값을 그대로 합치면
    # "실적이 없는 달의 목표"가 통째로 누락되어 누계 목표가 실제보다 작게 나오는 문제가
    # 있었다(사용자가 실측으로 발견) — sales_plan_record는 실적 업로드 여부와 무관하게
    # 연간 전체 월의 목표를 담고 있으므로 이걸 직접 합산해야 누계 목표가 정확하다.
    months = list(range(1, up_to_month + 1))
    placeholders = ", ".join(["?"] * len(months))
    rows = db.connection.execute(
        f"""
        SELECT team, SUM(planned_amount) FROM sales_plan_record
        WHERE year = ? AND month IN ({placeholders})
        GROUP BY team
        """,
        [year, *months],
    ).fetchall()
    return {team: amount for team, amount in rows if amount is not None}


def get_cumulative_teams(db, year: int, up_to_month: int) -> dict:
    rows = db.connection.execute(CUMULATIVE_TEAM_SQL, [year, up_to_month]).fetchall()
    plan_by_team = _cumulative_plan_amount_by_team(db, year, up_to_month)
    teams = []
    for team, quantity, actual_amount, profit in rows:
        quantity = quantity or 0.0
        actual_amount = actual_amount or 0.0
        profit = profit or 0.0
        plan_amount = plan_by_team.get(team)
        teams.append(
            {
                "team": team,
                "quantity": quantity,
                "actual_amount": actual_amount,
                "profit": profit,
                "profit_rate": (profit / actual_amount * 100) if actual_amount else None,
                "plan_amount": plan_amount,
                "achievement_rate": (actual_amount / plan_amount * 100) if plan_amount else None,
            }
        )
    teams.sort(key=lambda t: t["actual_amount"], reverse=True)

    total_quantity = sum(t["quantity"] for t in teams)
    total_actual = sum(t["actual_amount"] for t in teams)
    total_profit = sum(t["profit"] for t in teams)
    total_plan = sum(t["plan_amount"] for t in teams if t["plan_amount"] is not None) or None

    total = {
        "quantity": total_quantity,
        "actual_amount": total_actual,
        "profit": total_profit,
        "profit_rate": (total_profit / total_actual * 100) if total_actual else None,
        "plan_amount": total_plan,
        "achievement_rate": (total_actual / total_plan * 100) if total_plan else None,
    }

    return {"up_to_month": up_to_month, "teams": teams, "total": total}


def get_trend(db, team: str, year: int, up_to_month: int) -> dict:
    rows = db.connection.execute(
        """
        SELECT month, SUM(quantity), SUM(actual_amount), SUM(profit), SUM(sga_amount)
        FROM aggregated_result
        WHERE team = ? AND year = ? AND month <= ?
        GROUP BY month
        ORDER BY month
        """,
        [team, year, up_to_month],
    ).fetchall()
    by_month = {
        m: {
            "month": m,
            "quantity": q or 0.0,
            "actual_amount": a or 0.0,
            "profit": p or 0.0,
            "sga_amount": s or 0.0,
        }
        for m, q, a, p, s in rows
    }
    months = [by_month.get(m, {"month": m, "quantity": None, "actual_amount": None, "profit": None, "sga_amount": None}) for m in range(1, 13)]
    return {"team": team, "year": year, "months": months}


_AGG_COLUMNS_FOR_BEFORE_AFTER = """
    year, month, actual_amount, profit, sga_amount, avg_unit_price,
    prev_month_amount, prev_month_profit, prev_month_sga_amount, prev_month_avg_unit_price,
    prev_year_month_amount
"""


def _before_after_for_flag(
    db, batch_id: str, result_id: str, team: str, product_group: str | None, metric_type: str
) -> tuple[float | None, float | None]:
    """F5 화면에 "전월 X에서 당월 Y로 변동" 식으로 표시하기 위한 (전/후) 원시 값을
    유형별로 정확히 골라 반환한다(사용자 요청: "전월 얼마에서 당월 얼마로 얼마 변동,
    이렇게 표현하면 좋겠어"). actual_value(=% 또는 달성률)만으로는 유형마다 무엇을
    비교했는지 의미가 달라(예: 단가변동의 impact_amount는 매출액 차이지 단가 차이가
    아님) 역산이 위험하므로, 각 유형이 실제로 비교한 두 값을 그대로 다시 조회한다."""
    if metric_type == METRIC_PLAN_ACHIEVEMENT:
        row = db.connection.execute(
            "SELECT SUM(actual_amount), MAX(plan_amount) FROM aggregated_result WHERE batch_id = ? AND team = ?",
            [batch_id, team],
        ).fetchone()
        team_actual, team_plan = (row[0], row[1]) if row else (None, None)
        return team_plan, team_actual

    if metric_type == METRIC_PL_ITEM_PLAN:
        dev = find_team_item_deviation(db, batch_id, team, product_group or "")
        if dev is None:
            return None, None
        # "단위당 매출액"(sales_final)만 단위당 기준으로 판정·서술한다(pl_item_analysis.py
        # 참고) — 나머지 14개 항목은 plan_unit/actual_unit이 있어도(팀 전체 계획수량
        # 기준으로 항상 계산돼 있음) 그 값을 쓰면 안 된다. 실제로 겪은 버그: 이 조건이
        # "plan_unit이 있으면 무조건 단위당"이었을 때, 매출원가처럼 총액이 수백억인
        # 항목도 "총액÷팀 계획수량"이라는 작은 단가로 표시되어 F5에 "0.0억"으로만 보였다.
        if dev.key in UNIT_BASIS_KEYS and dev.plan_unit is not None and dev.actual_unit is not None:
            return dev.plan_unit, dev.actual_unit
        return dev.plan_total, dev.actual_total

    agg_row = db.connection.execute(
        f"SELECT {_AGG_COLUMNS_FOR_BEFORE_AFTER} FROM aggregated_result WHERE result_id = ?",
        [result_id],
    ).fetchone()
    if agg_row is None:
        return None, None
    (
        year, month, actual_amount, profit, sga_amount, avg_unit_price,
        prev_month_amount, prev_month_profit, prev_month_sga_amount, prev_month_avg_unit_price,
        prev_year_month_amount,
    ) = agg_row

    if metric_type == METRIC_PREV_MONTH:
        return prev_month_amount, actual_amount
    if metric_type == METRIC_PREV_YEAR:
        return prev_year_month_amount, actual_amount
    if metric_type == METRIC_PROFIT_TURN_NEGATIVE:
        return prev_month_profit, profit
    if metric_type == METRIC_UNIT_PRICE:
        return prev_month_avg_unit_price, avg_unit_price
    if metric_type == METRIC_SGA_SURGE:
        return prev_month_sga_amount, sga_amount
    return None, None


def _cumulative_before_for_unit_price(db, result_id: str, team: str, product_group: str | None) -> float | None:
    """Phase 20(.docs/phase/phase_20_단가변동누계평균통합.md, 사용자 확인) — "단가변동"
    플래그에 한해 전월 비교(before_value/after_value)와 별도로 누계평균(연초~직전월
    평균단가) 비교값도 같이 보여준다("당월 평균단가와 전월, 누계를 한꺼번에 비교")."""
    agg_row = db.connection.execute(
        "SELECT year, month FROM aggregated_result WHERE result_id = ?", [result_id]
    ).fetchone()
    if agg_row is None:
        return None
    year, month = agg_row
    return cumulative_prior_average(db, team, product_group, year, month, column="avg_unit_price")


def get_anomalies(db, batch_id: str) -> list[dict]:
    rows = db.connection.execute(
        """
        SELECT flag_id, result_id, team, product_group, metric_type, actual_value, threshold_value,
               impact_amount, is_confirmed_by_user
        FROM anomaly_flag
        WHERE batch_id = ?
        """,
        [batch_id],
    ).fetchall()
    flags = []
    for r in rows:
        flag_id, result_id, team, product_group, metric_type, actual_value, threshold_value, impact_amount, is_confirmed = r
        before_value, after_value = _before_after_for_flag(db, batch_id, result_id, team, product_group, metric_type)
        cumulative_before_value = (
            _cumulative_before_for_unit_price(db, result_id, team, product_group)
            if metric_type == METRIC_UNIT_PRICE
            else None
        )
        flags.append(
            {
                "flag_id": flag_id,
                "team": team,
                "product_group": product_group,
                "metric_type": metric_type,
                "actual_value": actual_value,
                "threshold_value": threshold_value,
                "impact_amount": impact_amount,
                "is_confirmed_by_user": bool(is_confirmed),
                "before_value": before_value,
                "after_value": after_value,
                "cumulative_before_value": cumulative_before_value,
            }
        )
    flags.sort(key=lambda f: abs(f["impact_amount"] or 0), reverse=True)
    return flags
