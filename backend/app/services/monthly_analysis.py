"""F4 Overview 손익 상세 분석 영역의 신규 탭 3종 — 월별 실적 분석(팀별/제품군별/거래처별).

.docs/phase/phase_14_월별실적분석탭.md 근거: 사용자 요청 컬럼 목록에 목표/계획 항목이
전혀 없다 — 계획 대비(pl_comparison.py)와 달리 **순수 실적 집계**만 보여준다.

팀별 탭은 사용자가 제공한 참고 이미지 형식을 따라 **팀마다 1~12월 행을 나열**하고
그 아래 "팀 요약"(연간 합계) 행을 붙인다(당월/누계 2단 비교가 아니다). 제품군별/
거래처별 탭은 원래 설계대로 당월(선택한 배치)과 금년 누계(연초~해당 월, 여러 배치의
refined_sales_record를 직접 합산 — app.services.analytics.get_cumulative_teams와
같은 패턴)를 함께 반환한다.

금액류(매출액/영업이익/판관비/제조원가/표준매출원가)는 백만원 단위로 변환해 반환한다
(사용자가 제공한 참고 이미지의 단위 표기 "단위 : EA,백만원"). 판매가(=매출액÷수량)도
같은 표 단위 기준을 따라 백만원/EA로 반환한다.

세 지표(제조원가/표준매출원가/가격변동율)에 대한 사용자 확인(2026-09-28):
  - 제조원가 = 실제 매출원가(기존 refined_sales_record.cogs_final, 신규 계산 없음).
  - 표준매출원가 = refined_sales_record.standard_cogs(Raw "매출원가(S)Tot" 단순 복사, Phase 14 신규 필드).
  - 가격변동율은 이번 컬럼 구성에서 제외(정의하지 않음).
"""
from __future__ import annotations

_MILLION = 1_000_000.0

_METRIC_SELECT = """
    SUM(quantity) AS quantity,
    SUM(sales_final) AS actual_amount,
    SUM(operating_profit_final) AS profit,
    SUM(sga_final) AS sga_amount,
    SUM(cogs_final) AS mfg_cost,
    SUM(standard_cogs) AS standard_cogs
"""


def _metrics(quantity, actual_amount, profit, sga_amount, mfg_cost, standard_cogs) -> dict:
    quantity = quantity or 0.0
    actual_amount = actual_amount or 0.0
    profit = profit or 0.0
    sga_amount = sga_amount or 0.0
    mfg_cost = mfg_cost or 0.0
    standard_cogs = standard_cogs or 0.0

    return {
        "quantity": quantity,
        "actual_amount": actual_amount / _MILLION,
        "profit": profit / _MILLION,
        "profit_rate": (profit / actual_amount * 100) if actual_amount else None,
        "sga_amount": sga_amount / _MILLION,
        "sga_rate": (sga_amount / actual_amount * 100) if actual_amount else None,
        "mfg_cost": mfg_cost / _MILLION,
        "mfg_cost_rate": (mfg_cost / actual_amount * 100) if actual_amount else None,
        "standard_cogs": standard_cogs / _MILLION,
        "avg_unit_price": (actual_amount / _MILLION / quantity) if quantity else None,
    }


def _zero_metrics() -> dict:
    return _metrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def _sum_metrics(rows: list[dict]) -> dict:
    return _metrics(
        sum(r["quantity"] for r in rows),
        sum(r["actual_amount"] * _MILLION for r in rows),
        sum(r["profit"] * _MILLION for r in rows),
        sum(r["sga_amount"] * _MILLION for r in rows),
        sum(r["mfg_cost"] * _MILLION for r in rows),
        sum(r["standard_cogs"] * _MILLION for r in rows),
    )


def get_team_monthly_analysis(db, batch_id: str) -> dict | None:
    """팀별 탭 — 사용자가 제공한 참고 이미지 형식대로 팀마다 1~12월 행을 나열하고
    (데이터가 없는 달은 빈 값), 그 아래 "팀 요약"(연간 합계) 행을 붙인다. 당월/누계
    2단 비교가 아니라 연간 월별 나열표다(Phase 14 후속 확인, 사용자 요청)."""
    period = db.batch_period(batch_id)
    if period is None:
        return None
    year, _ = period

    rows = db.connection.execute(
        f"SELECT team, month, {_METRIC_SELECT} FROM refined_sales_record WHERE year = ? GROUP BY team, month",
        [year],
    ).fetchall()
    by_team_month = {(r[0], r[1]): _metrics(*r[2:]) for r in rows}
    all_teams = sorted({team for team, _month in by_team_month})

    teams = []
    for team in all_teams:
        months = [{"month": m, "metrics": by_team_month.get((team, m))} for m in range(1, 13)]
        available = [entry["metrics"] for entry in months if entry["metrics"] is not None]
        teams.append(
            {
                "team": team,
                "months": months,
                "summary": _sum_metrics(available) if available else _zero_metrics(),
            }
        )
    teams.sort(key=lambda t: t["summary"]["actual_amount"], reverse=True)

    total = _sum_metrics([t["summary"] for t in teams]) if teams else _zero_metrics()
    return {"year": year, "teams": teams, "total": total}


def _extra_where(team: list[str] | None, part: list[str] | None) -> tuple[str, list]:
    """팀/파트 드릴다운 필터(사용자 요청: "손익 상세분석에 적용한 것과 같이") — pl_comparison.py의
    다중 선택 필터와 같은 방식으로 WHERE 절을 덧붙인다. "파트"는 지점코드 매핑 결과로
    refined_sales_record.part에 채워지는 값이다(app.services.branch 참고)."""
    clause = ""
    params: list = []
    if team:
        clause += f" AND team IN ({', '.join(['?'] * len(team))})"
        params += list(team)
    if part:
        clause += f" AND part IN ({', '.join(['?'] * len(part))})"
        params += list(part)
    return clause, params


def _grouped_analysis(
    db,
    batch_id: str,
    dimension_column: str,
    dimension_key: str,
    *,
    team: list[str] | None = None,
    part: list[str] | None = None,
) -> dict | None:
    period = db.batch_period(batch_id)
    if period is None:
        return None
    year, month = period
    extra_clause, extra_params = _extra_where(team, part)

    group_by = f"team, {dimension_column}"
    mtd_rows = db.connection.execute(
        f"SELECT team, {dimension_column}, {_METRIC_SELECT} FROM refined_sales_record "
        f"WHERE batch_id = ?{extra_clause} GROUP BY {group_by}",
        [batch_id, *extra_params],
    ).fetchall()
    ytd_rows = db.connection.execute(
        f"SELECT team, {dimension_column}, {_METRIC_SELECT} FROM refined_sales_record "
        f"WHERE year = ? AND month <= ?{extra_clause} GROUP BY {group_by}",
        [year, month, *extra_params],
    ).fetchall()

    mtd_by_key = {(r[0], r[1]): _metrics(*r[2:]) for r in mtd_rows}
    ytd_by_key = {(r[0], r[1]): _metrics(*r[2:]) for r in ytd_rows}
    # 매핑되지 않은 행은 product_group_2/customer_name이 NULL일 수 있다(is_mapped=False로
    # 이미 별도 표시되는 행들) — None과 문자열은 비교할 수 없어 정렬 키에서 빈 문자열로 취급한다.
    all_keys = sorted(set(mtd_by_key) | set(ytd_by_key), key=lambda k: (k[0], k[1] or ""))

    groups_by_team: dict[str, list[dict]] = {}
    for team, dim_value in all_keys:
        row = {
            dimension_key: dim_value,
            "mtd": mtd_by_key.get((team, dim_value), _zero_metrics()),
            "ytd": ytd_by_key.get((team, dim_value), _zero_metrics()),
        }
        groups_by_team.setdefault(team, []).append(row)

    groups = []
    for team in sorted(groups_by_team, key=lambda t: -_sum_metrics([r["mtd"] for r in groups_by_team[t]])["actual_amount"]):
        rows = groups_by_team[team]
        rows.sort(key=lambda r: r["mtd"]["actual_amount"], reverse=True)
        groups.append(
            {
                "team": team,
                "rows": rows,
                "subtotal": {
                    "mtd": _sum_metrics([r["mtd"] for r in rows]),
                    "ytd": _sum_metrics([r["ytd"] for r in rows]),
                },
            }
        )

    total = {
        "mtd": _sum_metrics([g["subtotal"]["mtd"] for g in groups]) if groups else _zero_metrics(),
        "ytd": _sum_metrics([g["subtotal"]["ytd"] for g in groups]) if groups else _zero_metrics(),
    }
    return {"year": year, "month": month, "groups": groups, "total": total}


def get_product_group_monthly_analysis(db, batch_id: str, *, team: list[str] | None = None) -> dict | None:
    return _grouped_analysis(db, batch_id, "product_group_2", "product_group_2", team=team)


def get_customer_monthly_analysis(
    db, batch_id: str, *, team: list[str] | None = None, part: list[str] | None = None
) -> dict | None:
    return _grouped_analysis(db, batch_id, "customer_name", "customer", team=team, part=part)


def get_monthly_analysis_filter_options(db, batch_id: str) -> dict | None:
    """제품군별/거래처별 탭의 팀·파트 드릴다운 드롭다운을 채우는, 이 배치에 실제로
    존재하는 값 목록(pl_comparison.py의 get_pl_comparison_filter_options와 같은 패턴)."""
    if db.batch_period(batch_id) is None:
        return None
    team_rows = db.connection.execute(
        "SELECT DISTINCT team FROM refined_sales_record WHERE batch_id = ? ORDER BY team",
        [batch_id],
    ).fetchall()
    part_rows = db.connection.execute(
        "SELECT DISTINCT part FROM refined_sales_record WHERE batch_id = ? AND part IS NOT NULL ORDER BY part",
        [batch_id],
    ).fetchall()
    return {"teams": [r[0] for r in team_rows], "parts": [r[0] for r in part_rows]}
