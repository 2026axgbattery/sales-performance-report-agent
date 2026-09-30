# -*- coding: utf-8 -*-
"""
plan_variance_comment_generator.py

계획(Plan) 대비 실적(Actual) 차이 분석 — 정성적 코멘트 생성 모듈.

PlanActualVarianceService.analyze()가 반환하는 구조화된 dict
(summary / highlights / volume_price_bridge / fixed_cost_breakdown / detail)를
그대로 입력받아, 사람이 읽는 분석 문단으로 풀어낸다.

설계 방침 (사용자 확정 사항 — 2026-09):
  - 계획대비(Plan vs Actual)를 "메인" 비교축으로 삼는다.
  - 전월대비(MoM)는 "보조 지표"로, 각 계정과목 코멘트 맨 끝에
    참고 문장 한 줄로만 덧붙인다 (메인 분석 대상은 여전히 계획대비).
  - comment_generator.py의 AccountCategory / 방향성(favorable) 로직을
    그대로 재사용해 "매출·이익 증가=긍정, 원가·비용 증가=부정"이라는
    동일한 원칙을 계획대비 분석에도 일관되게 적용한다.
  - 계정과목 마스터에 없는(fallback 처리된) 항목은 반드시 코멘트에
    "미매핑 계정과목" 경고를 남긴다 — 이전 코드 리뷰에서 지적된
    "조용한 COGS 기본 분류" 문제를 서술 단계에서 보완하기 위함.

이 모듈은 comment_generator.py의 AccountCategory / _HIGHER_IS_FAVORABLE을
그대로 임포트해서 쓴다. 두 모듈은 반드시 같은 폴더(또는 같은 패키지)에
있어야 한다. 아래 import는 "패키지 안(app/services/ 등)에 상대 임포트로
들어간 경우"와 "이 파일 하나만 스크립트로 직접 실행하는 경우" 둘 다
동작하도록 되어 있다 — 실제 프로젝트에 넣을 때 이 부분이 깨지는 게
가장 흔한 통합 실패 지점이므로, 프로젝트의 실제 패키지 구조에 맞게
필요하면 아래 try/except의 상대 임포트 경로를 조정한다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

try:
    from .comment_generator import AccountCategory, _HIGHER_IS_FAVORABLE, _eun_neun
except ImportError:  # 패키지가 아니라 이 파일을 단독 스크립트로 실행할 때의 폴백
    from comment_generator import AccountCategory, _HIGHER_IS_FAVORABLE, _eun_neun


# ─────────────────────────────────────────────────────────────
# 1. 서비스 쪽 문자열 값 → comment_generator의 Enum으로 변환
# ─────────────────────────────────────────────────────────────

# PlanActualVarianceService.AccountCategory.value ("revenue"/"cogs"/"sga"/"profit")
# → comment_generator.AccountCategory
_SERVICE_CATEGORY_TO_ACCOUNT_CATEGORY: dict[str, AccountCategory] = {
    "revenue": AccountCategory.REVENUE,
    "cogs": AccountCategory.COGS,
    "sga": AccountCategory.SGA,
    "profit": AccountCategory.OPERATING_PROFIT,
}


class CostType(str, Enum):
    """PlanActualVarianceService.CostType과 1:1 대응."""
    VARIABLE = "variable"
    FIXED = "fixed"
    ADJUSTMENT = "adjustment"
    NEUTRAL = "neutral"


STRONG_THRESHOLD_PCT = 10.0  # 증감률 절대값이 이 값 이상이면 "강한" 변화로 서술


@dataclass
class VarianceCommentThresholds:
    """
    "특이사항"으로 언급할지 판단하는 임계값.
    PlanActualVarianceService.VarianceThresholds와 값을 맞춰서 넘기는 것을 권장
    (서비스가 실제로 highlights를 골라낸 기준과, 코멘트가 "주목할 만하다"고
    서술하는 기준이 서로 다르면 혼란을 준다).
    """
    ratio_pp_threshold: float = 0.3
    unit_cost_pct_threshold: float = 10.0
    amount_pct_threshold: float = 15.0


# ─────────────────────────────────────────────────────────────
# 2. 입력 데이터 구조 — analyze() 출력의 detail 행 1개에 대응
# ─────────────────────────────────────────────────────────────

@dataclass
class PlanVarianceRecord:
    account_name: str                          # 계정과목
    account_category: AccountCategory
    cost_type: CostType

    plan_amount: float
    actual_amount: float
    amount_change: float
    amount_change_pct: Optional[float] = None

    plan_share_pct: Optional[float] = None       # 계획_비중
    actual_share_pct: Optional[float] = None     # 실적_비중
    share_change_pp: Optional[float] = None      # 비중_증감_pp

    plan_unit_cost: Optional[float] = None
    actual_unit_cost: Optional[float] = None
    unit_cost_change_pct: Optional[float] = None

    # 보조 지표 (사용자 확정: 계획대비가 메인, 전월대비는 보조)
    mom_change_pct: Optional[float] = None

    # 팀 차원 (현재 PlanActualVarianceService에는 없음 — 향후 팀별로
    # 이 서비스를 반복 호출하게 되면 팀명을 채워서 넘기면 된다)
    team_name: Optional[str] = None

    # 데이터 품질 플래그: account_master에 없어 기본값(COGS/NEUTRAL/999)으로
    # 잠정 분류된 계정과목인 경우 True
    is_unmapped_account: bool = False

    # cost_type 문자열이 이 모듈이 아는 CostType 값(variable/fixed/adjustment/neutral)에
    # 없어서 NEUTRAL로 강제 대체된 경우 True. 서비스 쪽 계정 마스터에 새로운
    # cost_type이 추가됐는데 이 모듈이 아직 그걸 모를 때 발생 — 이 경우 조용히
    # 넘어가지 않고 반드시 코멘트에 경고를 남긴다.
    is_unknown_cost_type: bool = False


def record_from_detail_row(
    row: dict[str, Any],
    *,
    account_master: Optional[dict[str, Any]] = None,
    mom_change_pct: Optional[float] = None,
    team_name: Optional[str] = None,
) -> PlanVarianceRecord:
    """
    analyze()["detail"]의 원소(dict) 1개를 PlanVarianceRecord로 변환.

    account_master: 서비스에 실제로 넘긴 것과 동일한 account_master 딕셔너리를
        넘기면, 그 안에 없는 계정과목을 "미매핑"으로 정확히 표시할 수 있다.
        생략하면 미매핑 여부는 판단하지 않는다(is_unmapped_account=False 고정).

    필수 키(계정과목/계획_금액/실적_금액/금액_증감/category/cost_type)가 없으면
    KeyError를 그대로 낸다 — 이건 analyze() 출력 자체가 예상과 다르다는
    뜻이라 조용히 넘기지 않고 호출자(build_variance_comments)가 잡아서
    처리하도록 한다. 반면 cost_type 값 자체를 모르는 경우는 여기서
    NEUTRAL로 안전하게 대체하고 플래그만 남긴다 — 계정과목 하나 때문에
    보고서 전체가 죽는 것을 막기 위함.
    """
    account_name = row["계정과목"]
    category = _SERVICE_CATEGORY_TO_ACCOUNT_CATEGORY.get(row["category"], AccountCategory.OTHER)

    is_unknown_cost_type = False
    try:
        cost_type = CostType(row["cost_type"])
    except ValueError:
        cost_type = CostType.NEUTRAL
        is_unknown_cost_type = True

    is_unmapped = False
    if account_master is not None:
        is_unmapped = account_name not in account_master

    return PlanVarianceRecord(
        account_name=account_name,
        account_category=category,
        cost_type=cost_type,
        plan_amount=row["계획_금액"],
        actual_amount=row["실적_금액"],
        amount_change=row["금액_증감"],
        amount_change_pct=row.get("금액_증감률_pct"),
        plan_share_pct=row.get("계획_비중"),
        actual_share_pct=row.get("실적_비중"),
        share_change_pp=row.get("비중_증감_pp"),
        plan_unit_cost=row.get("계획_단위원가"),
        actual_unit_cost=row.get("실적_단위원가"),
        unit_cost_change_pct=row.get("단위원가_증감률_pct"),
        mom_change_pct=mom_change_pct,
        team_name=team_name,
        is_unmapped_account=is_unmapped,
        is_unknown_cost_type=is_unknown_cost_type,
    )


# ─────────────────────────────────────────────────────────────
# 3. 표현 뱅크 (계획대비 전용 문구)
# ─────────────────────────────────────────────────────────────

class VariancePhraseBank:

    AMOUNT_UP_FAVORABLE = {
        "strong": ["계획 대비 큰 폭으로 초과 달성했습니다", "계획을 뚜렷하게 웃돌았습니다"],
        "moderate": ["계획을 소폭 상회했습니다", "계획 대비 완만하게 초과했습니다"],
    }
    AMOUNT_UP_UNFAVORABLE = {
        "strong": ["계획 대비 크게 초과 집행되며 부담이 확대되었습니다", "계획을 뚜렷하게 웃돌아 비용이 늘었습니다"],
        "moderate": ["계획을 소폭 초과했습니다", "계획 대비 다소 늘어난 수준입니다"],
    }
    AMOUNT_DOWN_FAVORABLE = {
        "strong": ["계획 대비 크게 절감되었습니다", "계획을 뚜렷하게 밑돌며 비용이 줄었습니다"],
        "moderate": ["계획 대비 소폭 절감되었습니다", "계획을 다소 밑돌았습니다"],
    }
    AMOUNT_DOWN_UNFAVORABLE = {
        "strong": ["계획 대비 크게 미달했습니다", "계획을 뚜렷하게 밑돌았습니다"],
        "moderate": ["계획에 소폭 미달했습니다", "계획을 다소 밑돌았습니다"],
    }
    AMOUNT_NEUTRAL_UP = {
        "strong": ["계획 대비 큰 폭으로 늘었습니다"], "moderate": ["계획 대비 소폭 늘었습니다"],
    }
    AMOUNT_NEUTRAL_DOWN = {
        "strong": ["계획 대비 큰 폭으로 줄었습니다"], "moderate": ["계획 대비 소폭 줄었습니다"],
    }
    AMOUNT_FLAT = ["계획과 거의 동일한 수준을 기록했습니다", "계획 대비 큰 차이 없이 집행되었습니다"]

    SHARE_UP = [
        "매출 대비 비중은 {pp:+.1f}%p 변화해 계획 시점보다 커졌습니다",
        "매출 대비 비중이 {pp:+.1f}%p 올라 계획보다 비중이 확대되었습니다",
    ]
    SHARE_DOWN = [
        "매출 대비 비중은 {pp:+.1f}%p 변화해 계획 시점보다 작아졌습니다",
        "매출 대비 비중이 {pp:+.1f}%p 내려 계획보다 비중이 축소되었습니다",
    ]

    UNIT_COST_FAVORABLE = [
        "단위당 원가는 계획 대비 {pct:+.1f}%로 나타나 원가 효율이 개선된 방향입니다",
        "단위원가가 계획보다 {pct:+.1f}% 수준으로, 개당 비용 부담이 줄어든 방향입니다",
    ]
    UNIT_COST_UNFAVORABLE = [
        "단위당 원가는 계획 대비 {pct:+.1f}%로 나타나 원가 효율이 저하된 방향입니다",
        "단위원가가 계획보다 {pct:+.1f}% 수준으로, 개당 비용 부담이 늘어난 방향입니다",
    ]

    MOM_CLAUSE = [
        "참고로 전월 대비로는 {sign}{pct:.1f}%였습니다",
        "전월 대비 기준으로는 {sign}{pct:.1f}%를 나타냈습니다",
    ]

    MULTI_METRIC_CAUTION = [
        "{metrics} 지표에서 모두 사전 설정된 임계치를 초과해, 중점 검토 대상 항목으로 표시되었습니다",
        "{metrics} 기준 임계치를 동시에 초과한 항목으로, 우선 확인이 필요합니다",
    ]
    SINGLE_METRIC_CAUTION = [
        "{metrics} 기준 임계치를 초과해 특이사항으로 표시되었습니다",
    ]

    UNMAPPED_ACCOUNT = [
        "다만 이 계정과목은 계정 마스터에 등록되어 있지 않아 잠정적으로 매출원가로 분류된 값이므로, 실제 분류가 맞는지 별도 확인이 필요합니다",
    ]

    UNKNOWN_COST_TYPE = [
        "다만 이 계정과목의 원가 성격(고정비/변동비)을 인식하지 못해 임시로 '중립'으로 처리했으므로, 고정비/변동비 집계에는 포함되지 않았습니다",
    ]

    VOLUME_DOMINANT = [
        "매출 변동은 물량효과({volume:+,.0f})가 가격효과({price:+,.0f})보다 크게 작용한 결과로 분해됩니다",
    ]
    PRICE_DOMINANT = [
        "매출 변동은 가격효과({price:+,.0f})가 물량효과({volume:+,.0f})보다 크게 작용한 결과로 분해됩니다",
    ]
    MIXED_DIRECTION = [
        "매출 변동은 물량효과({volume:+,.0f})와 가격효과({price:+,.0f})가 서로 반대 방향으로 작용한 결과입니다",
    ]

    @staticmethod
    def _pick(options: list[str], rng: Optional[random.Random] = None) -> str:
        chooser = rng if rng is not None else random
        return chooser.choice(options)

    @staticmethod
    def amount_phrase(
        pct: Optional[float],
        higher_is_favorable: Optional[bool],
        intensity: str,
        rng: Optional[random.Random] = None,
    ) -> str:
        if pct is None:
            return "계획 대비 비교값을 산출할 수 없습니다"
        is_up = pct > 0.05
        is_down = pct < -0.05
        if not is_up and not is_down:
            return VariancePhraseBank._pick(VariancePhraseBank.AMOUNT_FLAT, rng)

        if higher_is_favorable is None:
            group = VariancePhraseBank.AMOUNT_NEUTRAL_UP if is_up else VariancePhraseBank.AMOUNT_NEUTRAL_DOWN
        elif is_up:
            group = (
                VariancePhraseBank.AMOUNT_UP_FAVORABLE
                if higher_is_favorable
                else VariancePhraseBank.AMOUNT_UP_UNFAVORABLE
            )
        else:
            group = (
                VariancePhraseBank.AMOUNT_DOWN_UNFAVORABLE
                if higher_is_favorable
                else VariancePhraseBank.AMOUNT_DOWN_FAVORABLE
            )
        return VariancePhraseBank._pick(group[intensity], rng)


# ─────────────────────────────────────────────────────────────
# 4. 서사 조립 엔진 — 계정과목 1건
# ─────────────────────────────────────────────────────────────

class PlanVarianceNarrativeBuilder:

    def __init__(
        self,
        record: PlanVarianceRecord,
        thresholds: Optional[VarianceCommentThresholds] = None,
        seed: Optional[int] = None,
    ):
        self.r = record
        self.th = thresholds or VarianceCommentThresholds()
        # comment_generator.NarrativeBuilder와 동일한 이유로 전역 random 상태를
        # 건드리지 않는 인스턴스별 RNG를 쓴다 (동시 요청 간 간섭 방지).
        self._rng = random.Random(seed)

    def _headline(self) -> str:
        r = self.r
        favorable = _HIGHER_IS_FAVORABLE.get(r.account_category, None)
        pct = r.amount_change_pct
        intensity = "strong" if (pct is not None and abs(pct) >= STRONG_THRESHOLD_PCT) else "moderate"
        phrase = VariancePhraseBank.amount_phrase(pct, favorable, intensity, rng=self._rng)

        prefix = f"{r.team_name} " if r.team_name else ""
        pct_str = f"{pct:+.1f}%" if pct is not None else "산출불가"
        subject = f"{prefix}{r.account_name}"
        return (
            f"{subject}{_eun_neun(r.account_name)} 계획 {r.plan_amount:,.0f} 대비 실적 {r.actual_amount:,.0f}로, "
            f"금액 기준 {pct_str}를 기록하며 {phrase}."
        )

    def _share_detail(self) -> Optional[str]:
        r = self.r
        if r.share_change_pp is None:
            return None
        if abs(r.share_change_pp) < 0.05:
            return None
        template = VariancePhraseBank._pick(
            VariancePhraseBank.SHARE_UP if r.share_change_pp > 0 else VariancePhraseBank.SHARE_DOWN,
            self._rng,
        )
        return template.format(pp=r.share_change_pp) + "."

    def _unit_cost_detail(self) -> Optional[str]:
        r = self.r
        if r.unit_cost_change_pct is None:
            return None
        favorable = _HIGHER_IS_FAVORABLE.get(r.account_category, None)
        is_up = r.unit_cost_change_pct > 0.05
        is_down = r.unit_cost_change_pct < -0.05
        if not is_up and not is_down:
            return None
        if favorable is None:
            return None
        # 단위원가는 "커지는 게 안 좋은" 방향이 일반적 (COGS/SGA에서만 유효한 개념)
        unit_cost_up_is_bad = not favorable  # COGS/SGA는 favorable=False → 단위원가 증가=나쁨
        is_bad = is_up if unit_cost_up_is_bad else is_down
        template = VariancePhraseBank._pick(
            VariancePhraseBank.UNIT_COST_UNFAVORABLE if is_bad else VariancePhraseBank.UNIT_COST_FAVORABLE,
            self._rng,
        )
        return template.format(pct=r.unit_cost_change_pct) + "."

    def _mom_clause(self) -> Optional[str]:
        r = self.r
        if r.mom_change_pct is None:
            return None
        sign = "+" if r.mom_change_pct >= 0 else ""
        template = VariancePhraseBank._pick(VariancePhraseBank.MOM_CLAUSE, self._rng)
        return template.format(sign=sign, pct=r.mom_change_pct) + "."

    def _quality_and_highlight_cautions(self) -> list[str]:
        r = self.r
        th = self.th
        rng = self._rng
        cautions: list[str] = []

        exceeded: list[str] = []
        if r.share_change_pp is not None and abs(r.share_change_pp) >= th.ratio_pp_threshold:
            exceeded.append("매출비중")
        if r.unit_cost_change_pct is not None and abs(r.unit_cost_change_pct) >= th.unit_cost_pct_threshold:
            exceeded.append("단위원가")
        if r.amount_change_pct is not None and abs(r.amount_change_pct) >= th.amount_pct_threshold:
            exceeded.append("총액")

        if len(exceeded) >= 2:
            template = VariancePhraseBank._pick(VariancePhraseBank.MULTI_METRIC_CAUTION, rng)
            cautions.append(template.format(metrics="·".join(exceeded)) + ".")
        elif len(exceeded) == 1:
            template = VariancePhraseBank._pick(VariancePhraseBank.SINGLE_METRIC_CAUTION, rng)
            cautions.append(template.format(metrics=exceeded[0]) + ".")

        if r.is_unmapped_account:
            cautions.append(VariancePhraseBank._pick(VariancePhraseBank.UNMAPPED_ACCOUNT, rng) + ".")

        if r.is_unknown_cost_type:
            cautions.append(VariancePhraseBank._pick(VariancePhraseBank.UNKNOWN_COST_TYPE, rng) + ".")

        return cautions

    def build(self) -> str:
        parts = [self._headline()]
        for detail in (self._share_detail(), self._unit_cost_detail()):
            if detail:
                parts.append(detail)
        parts.extend(self._quality_and_highlight_cautions())
        mom = self._mom_clause()
        if mom:
            parts.append(mom)
        return " ".join(parts)


def generate_variance_comment(
    record: PlanVarianceRecord,
    thresholds: Optional[VarianceCommentThresholds] = None,
    seed: Optional[int] = None,
) -> str:
    return PlanVarianceNarrativeBuilder(record, thresholds=thresholds, seed=seed).build()


# ─────────────────────────────────────────────────────────────
# 5. 요약(summary) / 물량·가격효과 분해 — 문단 서술
# ─────────────────────────────────────────────────────────────

def build_summary_narrative(summary: dict[str, Any]) -> str:
    """analyze()["summary"]를 한 문단으로 서술."""
    parts = []

    rev = summary.get("revenue", {})
    if rev.get("change_pct") is not None:
        favorable = rev["change_pct"] >= 0
        word = "초과 달성했습니다" if favorable else "미달했습니다"
        parts.append(
            f"매출은 계획 {rev['plan']:,.0f} 대비 실적 {rev['actual']:,.0f}로 "
            f"{rev['change_pct']:+.1f}% {word}"
        )

    cogs = summary.get("cogs", {})
    if cogs.get("ratio_plan_pct") is not None and cogs.get("ratio_actual_pct") is not None:
        ratio_diff = cogs["ratio_actual_pct"] - cogs["ratio_plan_pct"]
        direction = "상승" if ratio_diff > 0 else "하락"
        parts.append(
            f"매출원가율은 계획 {cogs['ratio_plan_pct']:.1f}%에서 실적 {cogs['ratio_actual_pct']:.1f}%로 "
            f"{abs(ratio_diff):.1f}%p {direction}했습니다"
        )

    op = summary.get("operating_profit", {})
    if op.get("change_pct") is not None:
        favorable = op["change_pct"] >= 0
        word = "상회했습니다" if favorable else "하회했습니다"
        parts.append(
            f"영업이익은 계획 {op['plan']:,.0f} 대비 실적 {op['actual']:,.0f}로 "
            f"{op['change_pct']:+.1f}% 계획을 {word}"
        )
    elif op.get("plan") is not None and op.get("actual") is not None:
        parts.append(
            f"영업이익은 계획 {op['plan']:,.0f}, 실적 {op['actual']:,.0f}을 기록했습니다"
        )

    return ". ".join(parts) + "." if parts else "요약 정보를 산출할 수 없습니다."


def build_volume_price_narrative(volume_price_bridge: dict[str, Any]) -> Optional[str]:
    """analyze()["volume_price_bridge"]를 한 문장으로 서술. 데이터 없으면 None."""
    if not volume_price_bridge.get("available"):
        return None

    volume = volume_price_bridge["volume_effect"]
    price = volume_price_bridge["price_effect"]

    if volume == 0 and price == 0:
        return None

    same_direction = (volume >= 0) == (price >= 0)
    if same_direction:
        template = (
            VariancePhraseBank.VOLUME_DOMINANT
            if abs(volume) >= abs(price)
            else VariancePhraseBank.PRICE_DOMINANT
        )
    else:
        template = VariancePhraseBank.MIXED_DIRECTION

    sentence = VariancePhraseBank._pick(template).format(volume=volume, price=price)

    qty_pct = volume_price_bridge.get("quantity_change_pct")
    price_pct = volume_price_bridge.get("unit_price_change_pct")
    if qty_pct is not None and price_pct is not None:
        sentence += f" (판매수량 {qty_pct:+.1f}%, 평균판가 {price_pct:+.1f}%)"

    return sentence + "."


# ─────────────────────────────────────────────────────────────
# 6. 최상위 진입점 — analyze() 결과를 통째로 받아 전부 서술
# ─────────────────────────────────────────────────────────────

def build_variance_comments(
    variance_result: dict[str, Any],
    *,
    account_master: Optional[dict[str, Any]] = None,
    mom_change_lookup: Optional[dict[str, float]] = None,
    thresholds: Optional[VarianceCommentThresholds] = None,
    team_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    PlanActualVarianceService.analyze()의 반환값을 그대로 받아,
    - 전체 요약 문단
    - 물량효과/가격효과 문장(있으면)
    - 계정과목별 코멘트 리스트
    를 만들어 반환한다.

    mom_change_lookup: {"계정과목": 전월대비_증감률(float)} — 보조 지표로
        각 계정과목 코멘트 끝에 참고 문장으로 붙는다. 없으면 생략된다.

    계정과목 1건에서 예기치 못한 예외가 나도(예: analyze() 출력 스키마가
    바뀌는 등) 전체 보고서 생성이 죽지 않도록, 실패한 건은 플레이스홀더
    코멘트로 대체하고 "generation_errors"에 남긴다. 이 리스트가 비어
    있으면 전부 정상 처리된 것이다 — F8 화면이나 로그에서 이 필드를
    확인하면 어떤 계정과목이 왜 실패했는지 바로 알 수 있다.
    """
    mom_change_lookup = mom_change_lookup or {}

    account_comments = []
    generation_errors: list[dict[str, str]] = []
    for row in variance_result.get("detail", []):
        account_name = row.get("계정과목", "(계정과목 이름 없음)")
        try:
            record = record_from_detail_row(
                row,
                account_master=account_master,
                mom_change_pct=mom_change_lookup.get(account_name),
                team_name=team_name,
            )
            account_comments.append(
                {
                    "account_name": account_name,
                    "account_category": record.account_category.value,
                    "cost_type": record.cost_type.value,
                    "is_unmapped_account": record.is_unmapped_account,
                    "is_unknown_cost_type": record.is_unknown_cost_type,
                    "comment": generate_variance_comment(record, thresholds=thresholds),
                }
            )
        except Exception as exc:  # noqa: BLE001 - 이 계정과목만 건너뛰고 나머지는 계속 처리
            generation_errors.append(
                {"account_name": account_name, "error": f"{type(exc).__name__}: {exc}"}
            )
            account_comments.append(
                {
                    "account_name": account_name,
                    "account_category": None,
                    "cost_type": None,
                    "is_unmapped_account": None,
                    "is_unknown_cost_type": None,
                    "comment": f"[코멘트 생성 실패] {account_name} 항목은 자동 서술을 만들지 못했습니다. 원본 수치를 상세 데이터(detail)에서 직접 확인해 주세요.",
                }
            )

    return {
        "overall_summary": build_summary_narrative(variance_result.get("summary", {})),
        "volume_price_narrative": build_volume_price_narrative(
            variance_result.get("volume_price_bridge", {})
        ),
        "account_comments": account_comments,
        "generation_errors": generation_errors,
    }


# ─────────────────────────────────────────────────────────────
# 7. 동작 확인용 데모
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # PlanActualVarianceService.analyze()가 실제로 반환할 법한 구조를
    # 그대로 흉내낸 샘플 (필드명/키 이름 전부 실제 서비스와 동일하게 맞춤).
    sample_result = {
        "summary": {
            "revenue": {"plan": 10000.0, "actual": 11000.0, "change_pct": 10.0},
            "cogs": {"plan": 5800.0, "actual": 7230.0, "ratio_plan_pct": 58.0, "ratio_actual_pct": 65.7},
            "operating_profit": {
                "plan": 2000.0, "actual": 1500.0, "change_pct": -25.0,
                "margin_plan_pct": 20.0, "margin_actual_pct": 13.6,
            },
        },
        "volume_price_bridge": {
            "available": True,
            "plan_quantity": 1000.0, "actual_quantity": 1100.0,
            "quantity_change_pct": 10.0,
            "plan_unit_price": 10.0, "actual_unit_price": 10.0,
            "unit_price_change_pct": 0.0,
            "volume_effect": 1000.0, "price_effect": 0.0,
            "total_revenue_change": 1000.0,
        },
        "detail": [
            {
                "계정과목": "재료비", "계획_금액": 4000.0, "계획_수량": None,
                "실적_금액": 4800.0, "실적_수량": None,
                "계획_비중": 40.0, "실적_비중": 43.6, "비중_증감_pp": 3.6,
                "금액_증감": 800.0, "금액_증감률_pct": 20.0,
                "계획_단위원가": None, "실적_단위원가": None, "단위원가_증감률_pct": None,
                "category": "cogs", "cost_type": "variable",
            },
            {
                "계정과목": "신규계정(마스터에없음)", "계획_금액": 300.0, "계획_수량": None,
                "실적_금액": 900.0, "실적_수량": None,
                "계획_비중": 3.0, "실적_비중": 8.18, "비중_증감_pp": 5.18,
                "금액_증감": 600.0, "금액_증감률_pct": 200.0,
                "계획_단위원가": None, "실적_단위원가": None, "단위원가_증감률_pct": None,
                "category": "cogs", "cost_type": "neutral",
            },
        ],
    }

    # 실제 서비스에 넘겼던 account_master와 동일한 걸 넘겨야 미매핑 탐지가 정확함
    account_master = {
        "매출액": None, "재료비": None, "노무비-고정직접": None, "노무비-간접": None,
        "경비-고정": None, "경비-외주가공": None, "복리후생비": None, "지급수수료": None,
        "접대비": None, "기타(포장비/부대품)": None, "상품구매,재고실사차이 등": None,
        "조정": None, "운반비": None, "판관비-고정": None, "영업이익": None,
    }

    mom_lookup = {"재료비": 4.2}  # 보조 지표 예시 (전월 대비는 재료비만 있다고 가정)

    result = build_variance_comments(
        sample_result,
        account_master=account_master,
        mom_change_lookup=mom_lookup,
        team_name="차량OE팀",
    )

    print("=== 전체 요약 ===")
    print(result["overall_summary"])
    print()
    print("=== 물량/가격 효과 ===")
    print(result["volume_price_narrative"])
    print()
    print("=== 계정과목별 코멘트 ===")
    for c in result["account_comments"]:
        print(f"[{c['account_name']}] (unmapped={c['is_unmapped_account']})")
        print(" ", c["comment"])
        print()
