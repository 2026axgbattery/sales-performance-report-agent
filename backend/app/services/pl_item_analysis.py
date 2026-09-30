"""Phase 18(.docs/phase/phase_18_손익항목계획대비판정.md) — 손익 상세 분석
(app/services/pl_comparison.py)의 계정과목(재료비/노무비/경비/판관비 세부)별로
"팀 계획 대비 팀 실적"이 얼마나 벗어났는지 판정하고, 그 사실을 문장으로 조립한다.

사용자 요청 원문(Phase 18): "각 구분 항목별 계획 대비 실적의 총액 차 또는 단위당
가격 차이에 대한 판정, 계획대비 실적의 차이(비중차)를 분석할때는 팀단위 비교." —
드릴다운 필터(고객/상품/DESC/제품구분1~3)는 절대 적용하지 않고 항상 팀 전체 실적
vs 팀 전체 계획으로만 판정한다(F3 "계획대비"를 팀 단위로 좁힌 Phase 17과 같은 원칙).

사용자 확인(Phase 18 후속, .docs/phase/phase_18_손익항목계획대비판정.md 참고) —
서술 대상을 아래 15개 항목으로 명시적으로 한정한다("이상징후 하이라이트에서는
손익항목 계획대비는 ... 항목 한정"). 그중 "단위당 매출액"만 예외적으로 총액이
아니라 **단위당(=매출액÷매출수량) 기준**으로 판정한다 — 매출액 총액 자체는 이미
전월대비/전년대비/누계평균대비/계획대비(F3 기존 4개 기준)가 다루고 있어, 여기서는
그 기준들이 보지 않는 단위당 판가 변동만 추가로 본다.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.comment_generator import _eun_neun
from app.services.pl_comparison import TEAMS, get_pl_comparison

# pl_comparison.LINE_ITEMS의 key -> 라벨과 대응(주석은 실제 LINE_ITEMS 라벨을 그대로
# 인용). "재료비 계"/"노무비 계"/"경비 계"/"총원가" 같은 상위 소계는 사용자가 이번에
# 명시적으로 뺀 항목이므로 포함하지 않는다.
PL_NARRATIVE_ITEM_KEYS: frozenset[str] = frozenset(
    {
        "raw_material_total",  # 원재료비 계
        "main_material_total",  # 주재료비 계
        "other_material_supplies",  # 부재료비
        "other_material_etc",  # 기타재료비(포장비 등) 계
        "labor_direct",  # 직접노무비 계
        "labor_indirect",  # 간접노무비
        "expense_variable",  # 변동경비
        "expense_fixed",  # 고정경비
        "expense_outsourcing",  # 외주가공비
        "other_cogs",  # 기타(상품구매,재고실사차이 등) — get_pl_comparison이 동적으로 삽입하는 합성 항목
        "sga_variable",  # 변동판관비 계
        "sga_fixed",  # 고정판관비 계
        "cogs_final",  # 매출원가
        "sga_final",  # 판관비 계
        "sales_final",  # 단위당 매출액(예외 — 아래 _metric_pct 참고)
    }
)

# "단위당 매출액"만 총액이 아니라 단위당 기준으로 판정한다(위 모듈 docstring 참고).
UNIT_BASIS_KEYS: frozenset[str] = frozenset({"sales_final"})


def _metric_pct(line) -> float | None:
    """이 항목의 판정에 쓸 증감율(%)을 반환한다 — sales_final만 단위당 기준
    ((실적단가-계획단가)/계획단가), 나머지는 총액 기준(line.change_rate)이다.
    판정에 필요한 값이 없으면(계획 단가/총액이 0이거나 드릴다운 필터로 비교불가) None."""
    if line.key in UNIT_BASIS_KEYS:
        if not line.plan_unit or line.diff_unit is None:
            return None
        return (line.diff_unit / line.plan_unit) * 100
    if not line.plan_total or line.change_rate is None:
        return None
    return line.change_rate * 100


@dataclass
class PLItemDeviation:
    team: str
    key: str
    label: str
    plan_unit: float | None
    actual_unit: float | None
    diff_unit: float | None
    plan_total: float
    actual_total: float
    diff_total: float
    change_rate_pct: float
    plan_ratio: float | None
    actual_ratio: float | None


def _collect_team_deviations(db, batch_id: str, team: str, threshold_pct: float) -> list[PLItemDeviation]:
    result = get_pl_comparison(db, batch_id, team=[team])
    deviations: list[PLItemDeviation] = []
    for line in result.lines:
        if line.key not in PL_NARRATIVE_ITEM_KEYS:
            continue
        change_rate_pct = _metric_pct(line)
        if change_rate_pct is None or abs(change_rate_pct) < threshold_pct:
            continue
        deviations.append(
            PLItemDeviation(
                team=team,
                key=line.key,
                label=line.label,
                plan_unit=line.plan_unit,
                actual_unit=line.actual_unit,
                diff_unit=line.diff_unit,
                plan_total=line.plan_total,
                actual_total=line.actual_total,
                diff_total=line.diff_total,
                change_rate_pct=change_rate_pct,
                plan_ratio=line.plan_ratio,
                actual_ratio=line.actual_ratio,
            )
        )
    return deviations


def find_pl_item_deviations(db, batch_id: str, threshold_pct: float) -> list[PLItemDeviation]:
    """4개 팀 각각에 대해 드릴다운 필터 없이(=팀 전체 실적 vs 팀 전체 계획) 계정과목별
    증감율(%)이 threshold_pct 이상 벗어난 항목만 모아 반환한다."""
    deviations: list[PLItemDeviation] = []
    for team in TEAMS:
        deviations.extend(_collect_team_deviations(db, batch_id, team, threshold_pct))
    return deviations


def find_team_item_deviation(db, batch_id: str, team: str, label: str) -> PLItemDeviation | None:
    """F7 보고서 초안 생성 시점에 특정 (팀, 항목 라벨)의 편차를 다시 계산한다 — 다른
    F7 코멘트들이 aggregated_result를 result_id로 재조회하는 것과 같은 패턴으로,
    anomaly_flag에는 판정에 쓰인 최소 정보만 남기고 나머지는 재조회한다."""
    result = get_pl_comparison(db, batch_id, team=[team])
    for line in result.lines:
        if line.label != label or line.key not in PL_NARRATIVE_ITEM_KEYS:
            continue
        change_rate_pct = _metric_pct(line)
        if change_rate_pct is None:
            continue
        return PLItemDeviation(
            team=team,
            key=line.key,
            label=line.label,
            plan_unit=line.plan_unit,
            actual_unit=line.actual_unit,
            diff_unit=line.diff_unit,
            plan_total=line.plan_total,
            actual_total=line.actual_total,
            diff_total=line.diff_total,
            change_rate_pct=change_rate_pct,
            plan_ratio=line.plan_ratio,
            actual_ratio=line.actual_ratio,
        )
    return None


def format_pl_item_comment(dev: PLItemDeviation) -> str:
    """수치 기반 사실 서술 문장을 조립한다. "때문/원인/인해/탓" 등 원인 추정 어휘는
    쓰지 않는다(이 프로젝트 전역 원칙, test_comments.py/test_report_analysis_mapper.py와
    같은 금칙어 검사 대상)."""
    if dev.key in UNIT_BASIS_KEYS:
        # "단위당 매출액"은 단위당 기준으로만 판정하므로(모듈 docstring 참고), 이미
        # 다른 F3 기준이 다루는 매출액 총액·비중 문장은 만들지 않는다.
        unit_word = "상승" if dev.diff_unit >= 0 else "하락"
        subject = "단위당 매출액"
        return (
            f"{dev.team} {subject}{_eun_neun(subject)} 계획 {dev.plan_unit:,.0f}원 대비 실적 "
            f"{dev.actual_unit:,.0f}원으로 {abs(dev.diff_unit):,.0f}원"
            f"({dev.change_rate_pct:+.1f}%) {unit_word}했습니다."
        )

    sentences: list[str] = []

    if dev.plan_unit is not None and dev.actual_unit is not None and dev.diff_unit is not None:
        unit_word = "상승" if dev.diff_unit >= 0 else "하락"
        sentences.append(
            f"{dev.team} {dev.label}{_eun_neun(dev.label)} 단위당 계획 {dev.plan_unit:,.0f}원 대비 실적 "
            f"{dev.actual_unit:,.0f}원으로 {abs(dev.diff_unit):,.0f}원 {unit_word}했습니다."
        )
        total_word = "증가" if dev.diff_total >= 0 else "감소"
        sentences.append(
            f"총액 기준으로는 계획 {dev.plan_total:,.0f}원 대비 실적 {dev.actual_total:,.0f}원으로 "
            f"{abs(dev.diff_total):,.0f}원({dev.change_rate_pct:+.1f}%) {total_word}했습니다."
        )
    else:
        total_word = "증가" if dev.diff_total >= 0 else "감소"
        sentences.append(
            f"{dev.team} {dev.label}{_eun_neun(dev.label)} 계획 {dev.plan_total:,.0f}원 대비 실적 "
            f"{dev.actual_total:,.0f}원으로 {abs(dev.diff_total):,.0f}원({dev.change_rate_pct:+.1f}%) "
            f"{total_word}했습니다."
        )

    if dev.plan_ratio is not None and dev.actual_ratio is not None:
        diff_ratio = dev.actual_ratio - dev.plan_ratio
        ratio_word = "높아졌습니다" if diff_ratio >= 0 else "낮아졌습니다"
        sentences.append(
            f"매출액 대비 비중은 계획 {dev.plan_ratio:.1f}%에서 실적 {dev.actual_ratio:.1f}%로 "
            f"{diff_ratio:+.1f}%p {ratio_word}"
        )

    return " ".join(sentences)
