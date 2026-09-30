"""F3 이상징후 계산 결과(anomaly_flag)를 comment_generator.AnalysisRecord로 매핑한다.

.docs/phase/phase_16_코멘트생성기연결.md 근거 — 사용자 요청: "실제 F3 계산 코드
(증감률/이상징후 계산 부분)를 보여주면서 이 결과를 comment_generator.AnalysisRecord로
매핑해서 F7 보고서 생성에 연결해줘".

F3(`app/services/anomaly.py`)이 판정하는 6개 이상징후 유형(`app/services/thresholds.py`의
METRIC_* 상수)은 서로 다른 지표를 본다 — 전월대비/전년대비/계획대비는 매출액,
흑자전환은 영업이익, 단가변동은 평균단가, 판관비급증은 판관비. `anomaly_flag.actual_value`
자체는 유형에 따라 이미 "%"(전월대비/전년대비/단가변동/판관비급증)이거나 "달성률(%)"
(계획대비)이거나 원시 금액(흑자전환)이라 의미가 다르므로, 유형별로 갈라서 매핑해야 한다.

`aggregated_result`를 result_id로 다시 조회하는 이유 — anomaly_flag는 판정에 쓰인
값 하나(actual_value)만 들고 있어 "당월 실제 값"(AnalysisRecord.value)과 "전월 대비
증감률"(mom_change_pct)을 유형과 무관하게 항상 채우려면 원본 집계 행이 필요하다.
"""
from __future__ import annotations

from app.services.anomaly import cumulative_prior_average
from app.services.comment_generator import AccountCategory, AnalysisRecord, TrendDirection
from app.services.metrics import pct_change
from app.services.thresholds import (
    METRIC_PLAN_ACHIEVEMENT,
    METRIC_PREV_MONTH,
    METRIC_PREV_YEAR,
    METRIC_PROFIT_TURN_NEGATIVE,
    METRIC_SGA_SURGE,
    METRIC_UNIT_PRICE,
)

# metric_type -> (사람이 읽는 지표 이름, 계정과목 분류)
# comment_generator.AccountCategory는 "값이 커지는 게 좋은가"를 판단하는 데 쓰인다.
# 평균단가는 이 프로젝트에서 방향성(오르면 좋다/나쁘다)을 확정한 근거가 없어(가격변동율
# 자체를 F4 월별 실적 분석 컬럼 구성에서도 사용자가 제외하기로 확정한 바 있다) OTHER로
# 가치중립 서술만 한다 — 추정으로 방향성을 부여하지 않는다.
_METRIC_NAME_AND_CATEGORY: dict[str, tuple[str, AccountCategory]] = {
    METRIC_PREV_MONTH: ("매출액", AccountCategory.REVENUE),
    METRIC_PREV_YEAR: ("매출액", AccountCategory.REVENUE),
    METRIC_PLAN_ACHIEVEMENT: ("매출액(계획대비)", AccountCategory.REVENUE),
    METRIC_PROFIT_TURN_NEGATIVE: ("영업이익", AccountCategory.OPERATING_PROFIT),
    METRIC_UNIT_PRICE: ("평균단가", AccountCategory.OTHER),
    METRIC_SGA_SURGE: ("판관비", AccountCategory.SGA),
}

_AGGREGATED_RESULT_COLUMNS = """
    year, month, actual_amount, profit, sga_amount, avg_unit_price,
    prev_month_available, prev_month_amount, prev_month_profit, prev_month_sga_amount,
    prev_month_avg_unit_price
"""


def _label(team: str, product_group: str | None, *, is_team_level: bool = False) -> str:
    # app/services/comments.py의 기존 표기(팀+제품군, 미매핑이면 "(미매핑)")와 동일하게
    # 맞춘다 — 같은 배치를 두 방식으로 봤을 때 팀/제품군 표기가 달라 보이지 않게 한다.
    # is_team_level=True(계획대비 전용, Phase 17)면 product_group=None이 "미매핑"이
    # 아니라 "팀 전체"를 뜻하므로 팀명만 쓴다.
    if is_team_level:
        return team
    return f"{team} {product_group}" if product_group else f"{team}(미매핑)"


def _trend(pct: float | None) -> TrendDirection:
    if pct is None:
        return TrendDirection.FLAT
    if pct > 0.05:
        return TrendDirection.UP
    if pct < -0.05:
        return TrendDirection.DOWN
    return TrendDirection.FLAT


def _build_record(
    *,
    db,
    batch_id: str,
    team: str,
    product_group: str | None,
    metric_type: str,
    actual_value: float,
    threshold_value: float | None,
    period_label: str,
    agg: tuple,
) -> AnalysisRecord:
    (
        year,
        month,
        actual_amount,
        profit,
        sga_amount,
        avg_unit_price,
        prev_month_available,
        prev_month_amount,
        prev_month_profit,
        prev_month_sga_amount,
        prev_month_avg_unit_price,
    ) = agg

    is_team_level_plan = metric_type == METRIC_PLAN_ACHIEVEMENT
    if is_team_level_plan:
        # 계획대비는 Phase 17부터 팀 단위로만 판정한다(app/services/anomaly.py 참고) —
        # anchor_result_id로 조회한 agg는 그 팀의 제품군 행 "하나"일 뿐이므로, 당월 값은
        # 그 팀의 제품군 행 전체를 다시 합산해야 한다(anomaly.py의 team_actual과 동일한
        # 계산을 여기서도 반복 — anomaly_flag는 팀 합계 값 자체를 저장하지 않는다).
        team_total_row = db.connection.execute(
            "SELECT SUM(actual_amount) FROM aggregated_result WHERE batch_id = ? AND team = ?",
            [batch_id, team],
        ).fetchone()
        actual_amount = team_total_row[0] if team_total_row and team_total_row[0] is not None else actual_amount

    metric_name, category = _METRIC_NAME_AND_CATEGORY[metric_type]
    team_name = _label(team, product_group, is_team_level=is_team_level_plan)

    # 유형별로 "당월 값"과 "전월 대비 증감률"을 채운다. actual_value가 이미 %인
    # 유형(전월대비/단가변동/판관비급증)은 그대로 mom_change_pct로 쓰고, 그렇지 않은
    # 유형은 aggregated_result의 전월 비교값으로 직접 계산한다 — 계획대비/흑자전환은
    # 원래 "전월 대비 %" 개념이 아니라서 별도 계산이 필요하다.
    if metric_type == METRIC_PREV_MONTH:
        value = actual_amount
        mom = actual_value
        deviation = abs(actual_value) - (threshold_value or 0.0)
    elif metric_type == METRIC_PREV_YEAR:
        value = actual_amount
        mom = pct_change(actual_amount, prev_month_amount) if prev_month_available else None
        deviation = abs(actual_value) - (threshold_value or 0.0)
    elif metric_type == METRIC_PLAN_ACHIEVEMENT:
        # mom은 여기서 계산하지 않는다 — actual_amount는 방금 팀 합계로 바꿨는데
        # prev_month_amount는 anchor로 잡힌 제품군 행 하나의 전월 값이라, 둘을 나누면
        # "팀 합계 vs 제품군 하나의 전월"이라는 잘못된 비교가 된다(0으로 대체하는 것보다
        # 나쁜, 앞뒤가 안 맞는 값을 만드는 것이므로 아예 비워 둔다).
        value = actual_amount
        mom = None
        deviation = abs(actual_value - (threshold_value or actual_value))
    elif metric_type == METRIC_PROFIT_TURN_NEGATIVE:
        value = profit
        mom = pct_change(profit, prev_month_profit) if prev_month_available else None
        deviation = None  # 임계치 없이(0 초과 여부만) 판정하는 유형이라 초과폭 개념이 없다
    elif metric_type == METRIC_UNIT_PRICE:
        # Phase 20(.docs/phase/phase_20_단가변동누계평균통합.md, 사용자 확인) — 단가변동은
        # 이제 전월 대비뿐 아니라 누계평균(연초~직전월 평균단가) 대비도 함께 본다.
        # actual_value는 anomaly.py가 "둘 중 더 대표적인" 쪽(전월 대비 우선)을 담고
        # 있으므로 그대로 mom으로 쓰고, 누계평균 대비는 여기서 다시 계산해 폐지된
        # METRIC_CUMULATIVE_AVG가 쓰던 ytd_change_pct 자리에 채운다(같은 문구 재사용).
        value = avg_unit_price
        mom = actual_value
        deviation = abs(actual_value) - (threshold_value or 0.0)
    elif metric_type == METRIC_SGA_SURGE:
        value = sga_amount
        mom = actual_value
        deviation = actual_value - (threshold_value or 0.0)
    else:
        # 6개 유형 밖의 metric_type(향후 확장)은 근거 없이 임의 매핑하지 않고, actual_value를
        # 그대로 당월 값으로 두고 전월 대비는 알 수 없는 것으로 둔다.
        value = actual_value
        mom = None
        deviation = None

    yoy = actual_value if metric_type == METRIC_PREV_YEAR else None
    ytd = None
    if metric_type == METRIC_UNIT_PRICE and year is not None:
        cum_avg_unit_price = cumulative_prior_average(db, team, product_group, year, month, column="avg_unit_price")
        ytd = pct_change(avg_unit_price, cum_avg_unit_price)

    return AnalysisRecord(
        team_name=team_name,
        metric_name=metric_name,
        period_label=period_label,
        value=value if value is not None else 0.0,
        mom_change_pct=mom,
        yoy_change_pct=yoy,
        ytd_change_pct=ytd,
        account_category=category,
        trend_direction=_trend(mom),
        is_anomaly=True,
        threshold_value=threshold_value,
        deviation_pct=deviation,
    )


def build_analysis_records(db, batch_id: str) -> list[tuple[str, AnalysisRecord]]:
    """배치의 anomaly_flag 전체를 (flag_id, AnalysisRecord) 리스트로 변환한다. flag_id를
    함께 반환해, 호출부(app.services.reports)가 report_item에 어떤 flag의 결과인지
    그대로 남길 수 있게 한다."""
    period = db.batch_period(batch_id)
    year, month = period if period else (None, None)
    period_label = f"{year}년 {month}월" if period else "알 수 없는 기간"

    flags = db.connection.execute(
        """
        SELECT flag_id, result_id, team, product_group, metric_type, actual_value, threshold_value
        FROM anomaly_flag
        WHERE batch_id = ?
        """,
        [batch_id],
    ).fetchall()

    records: list[tuple[str, AnalysisRecord]] = []
    for flag_id, result_id, team, product_group, metric_type, actual_value, threshold_value in flags:
        agg_row = db.connection.execute(
            f"SELECT {_AGGREGATED_RESULT_COLUMNS} FROM aggregated_result WHERE result_id = ?",
            [result_id],
        ).fetchone()
        if agg_row is None or metric_type not in _METRIC_NAME_AND_CATEGORY:
            continue
        record = _build_record(
            db=db,
            batch_id=batch_id,
            team=team,
            product_group=product_group,
            metric_type=metric_type,
            actual_value=actual_value,
            threshold_value=threshold_value,
            period_label=period_label,
            agg=agg_row,
        )
        records.append((flag_id, record))
    return records
