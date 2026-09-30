"""F3. 증감률·이상징후 자동 계산 — 7개 판단 기준 평가.

docs/02_prd.md F3 표 기준. 비교 대상 데이터가 없으면(전년 동월 등) "비교 불가"로
취급해 계산에서 제외한다 (0%나 임의값으로 대체하지 않음).

Phase 17(.docs/phase/phase_17_이상징후판정범위조정.md, 사용자 확인) — 판정 범위를
두 갈래로 나눴다: "각 팀의 제품군에 대한 분석은 전월 또는 누계 평균 대비를 위주로
분석하고, 계획대비에 대한 분석은 팀 계획 vs 팀 실적을 기본으로 한다." 그래서
전월대비/전년대비/단가변동/판관비급증은 그대로 팀×제품군 단위로 평가하고, 계획대비만
팀 단위로 한 번씩 평가하도록 뺐다. 계획대비를 팀×제품군 단위로 두면
`aggregated_result.achievement_rate`가 "제품군 하나의 실적 ÷ 팀 전체 계획"이 되어(팀
계획이 모든 제품군 행에 복제 저장되므로, app/services/aggregation.py 참고) 어떤
제품군이든 항상 미달로 나오는 버그가 있었다 — F4/PDF가 이미 팀 단위로 올바르게
계산하던 것(app/services/analytics.py의 TEAM_ROLLUP_SQL)과 F3만 어긋나 있었다.

Phase 20(.docs/phase/phase_20_단가변동누계평균통합.md, 사용자 확인) — Phase 17에서
신설한 "누계평균대비"(매출액을 연초~직전월 평균과 비교)를 독립 기준에서 폐지하고,
그 "누계평균 비교" 개념만 "단가변동"(평균단가) 안에 흡수시켰다: "누계 평균대비는
별도의 버튼으로 분류하지 말고... 단가 변동에서만 비교해보자." 단가변동은 이제 전월
대비와 누계평균 대비를 모두 계산해 둘 중 하나라도 임계치를 넘으면 플래그하고, 화면에는
항상 둘 다 보여준다(app/services/analytics.py의 get_anomalies 참고).
"""
from __future__ import annotations

import uuid

from app.services.metrics import pct_change as _pct_change
from app.services.pl_item_analysis import find_pl_item_deviations
from app.services.thresholds import (
    METRIC_PL_ITEM_PLAN,
    METRIC_PLAN_ACHIEVEMENT,
    METRIC_PREV_MONTH,
    METRIC_PREV_YEAR,
    METRIC_PROFIT_TURN_NEGATIVE,
    METRIC_SGA_SURGE,
    METRIC_UNIT_PRICE,
    get_thresholds,
)


def cumulative_prior_average(
    db, team: str, product_group: str | None, year: int, month: int, *, column: str = "actual_amount"
) -> float | None:
    """연초~직전월(당월 제외)의 팀×제품군 월평균 수치(사용자 확인: 당월을 포함하면
    "이번 달이 스스로를 끌어올리는" 편향이 생기므로 직전월까지만 평균 낸다). 1월이거나
    아직 이전 달 집계가 하나도 없으면 비교 기준이 없는 것이므로 None을 반환한다(0이나
    당월 값으로 대체하지 않음). `column`은 aggregated_result의 컬럼명만 받는 내부
    전용 매개변수라(외부 입력이 아님) f-string으로 끼워 넣어도 SQL 인젝션 위험이 없다
    — Phase 20에서 평균단가(avg_unit_price) 기준 누계평균도 재사용하려고 일반화했다
    (매출액 전용이던 것을 pl_comparison.py의 컬럼 매개변수 패턴과 동일하게 확장)."""
    if month <= 1:
        return None
    row = db.connection.execute(
        f"""
        SELECT AVG({column}) FROM aggregated_result
        WHERE team = ? AND product_group IS NOT DISTINCT FROM ? AND year = ? AND month < ?
        """,
        [team, product_group, year, month],
    ).fetchone()
    return row[0] if row else None


def evaluate_anomalies(db, batch_id: str) -> int:
    thresholds = get_thresholds(db)
    db.connection.execute("DELETE FROM anomaly_flag WHERE batch_id = ?", [batch_id])

    period = db.batch_period(batch_id)
    year, month = period if period else (None, None)

    rows = db.connection.execute(
        """
        SELECT result_id, team, product_group, actual_amount, profit, sga_amount, avg_unit_price,
               plan_amount, achievement_rate,
               prev_month_available, prev_month_amount, prev_month_profit,
               prev_month_sga_amount, prev_month_avg_unit_price
        FROM aggregated_result
        WHERE batch_id = ?
        """,
        [batch_id],
    ).fetchall()

    flag_count = 0
    for (
        result_id,
        team,
        product_group,
        actual_amount,
        profit,
        sga_amount,
        avg_unit_price,
        plan_amount,
        achievement_rate,
        prev_month_available,
        prev_month_amount,
        prev_month_profit,
        prev_month_sga_amount,
        prev_month_avg_unit_price,
    ) in rows:
        flags: list[tuple[str, float, float, float]] = []  # (metric_type, actual_value, threshold_value, impact_amount)

        # 1. 전월 대비 매출/이익 증감률
        if prev_month_available:
            change = _pct_change(actual_amount, prev_month_amount)
            th = thresholds[METRIC_PREV_MONTH].threshold_value
            if change is not None and th is not None and abs(change) >= th:
                flags.append((METRIC_PREV_MONTH, change, th, actual_amount - (prev_month_amount or 0)))

        # 4. 흑자 -> 적자 전환 (임계치 없이 조건 충족 시 항상 플래그)
        if prev_month_available and prev_month_profit is not None:
            if prev_month_profit >= 0 and profit < 0:
                flags.append((METRIC_PROFIT_TURN_NEGATIVE, profit, 0.0, profit - prev_month_profit))

        # 5. 평균단가 변동 — 전월 대비와 누계평균 대비를 함께 판정한다(Phase 20, 사용자
        # 확인: "당월 평균단가와 전월, 누계를 한꺼번에 비교"). 둘 중 하나라도 기존
        # 단가변동 임계치(기본 5%)를 넘으면 플래그 하나로 남긴다 — 전월/누계에 별도
        # 임계치를 새로 만들지 않는다(F6 설정을 늘리지 않기 위한 단순화).
        if avg_unit_price is not None:
            th = thresholds[METRIC_UNIT_PRICE].threshold_value
            prev_change = _pct_change(avg_unit_price, prev_month_avg_unit_price) if prev_month_available else None
            cum_avg_unit_price = (
                cumulative_prior_average(db, team, product_group, year, month, column="avg_unit_price")
                if year is not None
                else None
            )
            cum_change = _pct_change(avg_unit_price, cum_avg_unit_price)
            breached_prev = prev_change is not None and th is not None and abs(prev_change) >= th
            breached_cum = cum_change is not None and th is not None and abs(cum_change) >= th
            if breached_prev or breached_cum:
                representative = prev_change if prev_change is not None else cum_change
                flags.append(
                    (METRIC_UNIT_PRICE, representative, th, actual_amount - (prev_month_amount or 0))
                )

        # 6. 판관비/기타비용 급증 (전월 대비, 한쪽 방향만)
        if prev_month_available:
            change = _pct_change(sga_amount, prev_month_sga_amount)
            th = thresholds[METRIC_SGA_SURGE].threshold_value
            if change is not None and th is not None and change >= th:
                flags.append((METRIC_SGA_SURGE, change, th, sga_amount - (prev_month_sga_amount or 0)))

        # 2. 전년 동월 대비 증감률 (별도 조회)
        prev_year = db.connection.execute(
            "SELECT prev_year_month_available, prev_year_month_amount FROM aggregated_result WHERE result_id = ?",
            [result_id],
        ).fetchone()
        if prev_year and prev_year[0]:
            change = _pct_change(actual_amount, prev_year[1])
            th = thresholds[METRIC_PREV_YEAR].threshold_value
            if change is not None and th is not None and abs(change) >= th:
                flags.append((METRIC_PREV_YEAR, change, th, actual_amount - (prev_year[1] or 0)))

        for metric_type, actual_value, threshold_value, impact_amount in flags:
            db.connection.execute(
                """
                INSERT INTO anomaly_flag (
                    flag_id, batch_id, result_id, team, product_group,
                    metric_type, actual_value, threshold_value, impact_amount, is_confirmed_by_user
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(uuid.uuid4()),
                    batch_id,
                    result_id,
                    team,
                    product_group,
                    metric_type,
                    actual_value,
                    threshold_value,
                    impact_amount,
                    False,
                ],
            )
            flag_count += 1

    # 계획대비 — 팀 단위로 한 번만 평가한다(사용자 확인: "계획대비에 대한 분석은 팀
    # 계획 vs 팀 실적을 기본으로 한다"). plan_amount는 팀의 모든 제품군 행에 같은 값이
    # 복제 저장돼 있으므로(app/services/aggregation.py) MAX로 한 번만 취하고, 실적은
    # 그 팀의 제품군 행 전체를 합산한다 — F4/PDF의 TEAM_ROLLUP_SQL과 동일한 방식.
    team_rows = db.connection.execute(
        """
        SELECT team, SUM(actual_amount) AS team_actual, MAX(plan_amount) AS team_plan,
               MIN(result_id) AS anchor_result_id
        FROM aggregated_result
        WHERE batch_id = ?
        GROUP BY team
        """,
        [batch_id],
    ).fetchall()
    for team, team_actual, team_plan, anchor_result_id in team_rows:
        if not team_plan:
            continue
        team_achievement_rate = (team_actual or 0.0) / team_plan * 100
        low = thresholds[METRIC_PLAN_ACHIEVEMENT].threshold_low
        high = thresholds[METRIC_PLAN_ACHIEVEMENT].threshold_high
        breached_low = low is not None and team_achievement_rate < low
        breached_high = high is not None and team_achievement_rate > high
        if not breached_low and not breached_high:
            continue
        bound = low if breached_low else high
        # product_group=NULL — 이 플래그는 "미매핑"이 아니라 "팀 전체(제품군 구분 없음)"를
        # 뜻한다(계획대비만 해당하는 예외적인 의미이므로 읽는 쪽에서 metric_type과 함께
        # 봐야 한다). anchor_result_id는 report_analysis_mapper가 배치/팀을 역참조할 수
        # 있도록 그 팀의 아무 제품군 행이나 하나 잡아 FK로 둔다(값 자체는 여기서 다시
        # 계산한 팀 합계를 쓰므로 anchor 행의 개별 값은 사용하지 않는다).
        db.connection.execute(
            """
            INSERT INTO anomaly_flag (
                flag_id, batch_id, result_id, team, product_group,
                metric_type, actual_value, threshold_value, impact_amount, is_confirmed_by_user
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                batch_id,
                anchor_result_id,
                team,
                None,
                METRIC_PLAN_ACHIEVEMENT,
                team_achievement_rate,
                bound,
                (team_actual or 0.0) - team_plan,
                False,
            ],
        )
        flag_count += 1

    # 손익항목계획대비(Phase 18, .docs/phase/phase_18_손익항목계획대비판정.md,
    # 사용자 확인) — 손익 상세 분석(pl_comparison.py)의 재료비/노무비/경비/판관비
    # 세부 항목별로, 위 계획대비와 같은 원칙(팀 계획 vs 팀 실적)으로 판정한다.
    # anchor_result_id는 team_rows에서 이미 팀별로 하나씩 구해뒀으므로 재사용한다
    # (team_plan이 없어 위 계획대비 루프에서 continue된 팀도 anchor는 그대로 쓸 수 있다).
    # get_pl_comparison은 batch_period(=upload_batch 행)가 없으면 예외를 던지므로
    # (pl_comparison.py), period가 없는 배치(단위 테스트가 직접 aggregated_result만
    # 채우고 upload_batch는 생략하는 경우 등)에서는 이 패스 자체를 건너뛴다.
    team_anchor = {team: anchor_result_id for team, _, _, anchor_result_id in team_rows}
    pl_item_threshold = thresholds[METRIC_PL_ITEM_PLAN].threshold_value
    if year is not None and pl_item_threshold is not None:
        for dev in find_pl_item_deviations(db, batch_id, pl_item_threshold):
            anchor_result_id = team_anchor.get(dev.team)
            if anchor_result_id is None:
                continue
            # product_group 칸을 "팀 전체"(NULL)가 아니라 계정과목 라벨(예: "재료비 계")로
            # 재사용한다 — F7(reports.py)이 이 라벨로 pl_item_analysis를 다시 조회해
            # 단위당/총액/비중 차이를 문장으로 조립한다.
            db.connection.execute(
                """
                INSERT INTO anomaly_flag (
                    flag_id, batch_id, result_id, team, product_group,
                    metric_type, actual_value, threshold_value, impact_amount, is_confirmed_by_user
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(uuid.uuid4()),
                    batch_id,
                    anchor_result_id,
                    dev.team,
                    dev.label,
                    METRIC_PL_ITEM_PLAN,
                    dev.change_rate_pct,
                    pl_item_threshold,
                    dev.diff_total,
                    False,
                ],
            )
            flag_count += 1

    return flag_count
