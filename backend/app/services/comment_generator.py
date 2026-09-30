# -*- coding: utf-8 -*-
"""
comment_generator.py

규칙/템플릿 기반 정성적 분석 코멘트 생성 모듈 (F7 - 보고서 초안 자동 생성)

설계 원칙 (01_아키텍처.md §3.4 / F7 요구사항과 동일):
  1. 코멘트는 수치 기반 "사실 서술"에 한정한다. 원인(why)을 추정하지 않는다.
  2. 모든 문장은 입력 record의 계산된 값에서만 파생된다 (결정론적, 검증 가능).
  3. 외부/사내 AI API를 호출하지 않고, 서사 구조(narrative structure) +
     표현 뱅크(phrase bank) + 맥락 결합(context blending)으로
     "분석적으로 읽히는" 문장을 조립한다.

이 모듈은 3개 계층으로 구성된다:
  - AnalysisRecord: 정량 분석 결과를 담는 입력 데이터 구조
  - PhraseBank: 같은 의미를 다른 표현으로 반환하는 표현 사전
  - NarrativeBuilder: headline → supporting detail → caution 순서로
    문단을 조립하는 서사 엔진

사용 예시는 파일 하단 `if __name__ == "__main__":` 블록 참고.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────────────────────
# 1. 입력 데이터 구조
# ─────────────────────────────────────────────────────────────

class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class AccountCategory(str, Enum):
    """
    03_데이터정제.md §4의 계정과목 그룹과 대응.
    같은 "증가"라도 계정과목에 따라 바람직한 방향이 반대이므로
    (매출·이익은 증가=긍정, 원가·비용은 증가=부정) 카테고리별로
    분리해서 관리한다.

    §4 매핑:
      REVENUE          -> §4.2 매출 (I~P)
      COGS             -> §4.3~4.4 매출원가: 재료비/노무비/경비 (Q~AU)
      SGA              -> §4.5 판관비 (AV~BL)
      OPERATING_PROFIT -> §4.6 영업이익 (BM, BN)
      QUANTITY         -> §4.6 매출수량(BO) / §4.7 수량(22.9cell)(BZ)
    """
    REVENUE = "revenue"
    COGS = "cogs"
    SGA = "sga"
    OPERATING_PROFIT = "operating_profit"
    QUANTITY = "quantity"
    OTHER = "other"


# 카테고리별 "값이 커지는 방향이 긍정적인가"를 정의.
# True  -> 증가가 긍정적(매출/이익), False -> 증가가 부정적(원가/비용),
# None  -> 가치 판단 없이 순수 방향만 서술(수량 등)
_HIGHER_IS_FAVORABLE: dict[AccountCategory, Optional[bool]] = {
    AccountCategory.REVENUE: True,
    AccountCategory.OPERATING_PROFIT: True,
    AccountCategory.COGS: False,
    AccountCategory.SGA: False,
    AccountCategory.QUANTITY: None,
    AccountCategory.OTHER: None,
}


# ─────────────────────────────────────────────────────────────
# 1-1. 계정과목(컬럼 헤더) → 카테고리 매핑
#      "클로드_실적_데이터_분석용_2.xlsx"의 '실적 Re-arrange용 수식' 시트
#      실제 헤더(A~BY, 77개 컬럼) 전수를 기준으로 작성.
#      식별자 컬럼(년/월/팀/제품구분 등)은 카테고리가 없으므로 매핑에서 제외한다.
# ─────────────────────────────────────────────────────────────

# 식별자·차원(dimension) 컬럼 — 수치 지표가 아니므로 코멘트 생성 대상에서 제외
IDENTIFIER_COLUMNS: set[str] = {
    "년", "월", "부문", "팀", "권역", "사업소", "파트",
    "거래처코드", "고객", "상품", "DESC", "구분", "판매구분",
    "제품구분1", "제품구분2", "제품구분3",
}

ACCOUNT_CATEGORY_BY_COLUMN: dict[str, AccountCategory] = {
    # ── §4.2 매출 계열 (Re-arrange 실제 헤더 Q~X) ──
    "영업-가마감매출": AccountCategory.REVENUE,
    "영업-매출할인": AccountCategory.REVENUE,
    "영업-마감매출조정": AccountCategory.REVENUE,
    "영업-정마감매출": AccountCategory.REVENUE,
    "영업-기타매출액": AccountCategory.REVENUE,
    "영업-매출액(조정전)": AccountCategory.REVENUE,
    "기획-매출조정": AccountCategory.REVENUE,
    "기획-매출액(최종마감)": AccountCategory.REVENUE,

    # ── §4.3 매출원가: 재료비 (Re-arrange 실제 헤더 Y~AN) ──
    "순연": AccountCategory.COGS,
    "경연": AccountCategory.COGS,
    "칼슘연": AccountCategory.COGS,
    "니켈": AccountCategory.COGS,
    "리튬": AccountCategory.COGS,
    "원재료비": AccountCategory.COGS,
    "전조": AccountCategory.COGS,
    "카바": AccountCategory.COGS,
    "격리판": AccountCategory.COGS,
    "주재료비": AccountCategory.COGS,
    "부재료비": AccountCategory.COGS,
    "포장비": AccountCategory.COGS,
    "부대품": AccountCategory.COGS,
    "부산물공제": AccountCategory.COGS,
    "기타재료비": AccountCategory.COGS,
    "재료비 계": AccountCategory.COGS,

    # ── §4.4 매출원가: 노무비·경비 (Re-arrange 실제 헤더 AO~BC) ──
    "변동직접": AccountCategory.COGS,
    "고정직접": AccountCategory.COGS,
    "직접노무비": AccountCategory.COGS,
    "간접노무비": AccountCategory.COGS,
    "노무비 계": AccountCategory.COGS,
    "변동경비": AccountCategory.COGS,
    "고정경비": AccountCategory.COGS,
    "외주가공비": AccountCategory.COGS,
    "경비 계": AccountCategory.COGS,
    "기타매출원가": AccountCategory.COGS,
    "실제매출원가": AccountCategory.COGS,
    "실제매출원가조정": AccountCategory.COGS,
    "매출원가(조정전)": AccountCategory.COGS,
    "기획팀-원가조정": AccountCategory.COGS,
    "매출원가(최종마감)": AccountCategory.COGS,

    # ── §4.5 판관비 (Re-arrange 실제 헤더 BD~BT) ──
    "차량유지비": AccountCategory.SGA,
    "운반비": AccountCategory.SGA,
    "수출비용": AccountCategory.SGA,
    "시험설치비": AccountCategory.SGA,
    "판매보증비": AccountCategory.SGA,
    "불량제품손실": AccountCategory.SGA,
    "해상운임": AccountCategory.SGA,
    "변동판관비": AccountCategory.SGA,
    "판관인건비": AccountCategory.SGA,
    "복리후생비": AccountCategory.SGA,
    "접대비": AccountCategory.SGA,
    "지급수수료": AccountCategory.SGA,
    "기타-판관비": AccountCategory.SGA,
    "고정판관비": AccountCategory.SGA,
    "판관비(조정전)": AccountCategory.SGA,
    "기획팀-판관비조정": AccountCategory.SGA,
    "판관비(최종마감)": AccountCategory.SGA,

    # ── §4.6 영업이익·수량 (Re-arrange 실제 헤더 BU~BX) ──
    "영업이익(조정전)": AccountCategory.OPERATING_PROFIT,
    "영업이익(최종마감)": AccountCategory.OPERATING_PROFIT,
    "매출수량": AccountCategory.QUANTITY,
    "재고실사차이": AccountCategory.OTHER,

    # ── §4.7 수량(22.9cell) (Re-arrange 실제 헤더 BY, 08월 신규) ──
    "수량(22.9cell)": AccountCategory.QUANTITY,
}


def get_account_category(metric_name: str) -> AccountCategory:
    """
    Re-arrange 시트의 컬럼 헤더 텍스트를 넣으면 해당 계정과목의
    AccountCategory를 반환한다. 매핑에 없는 이름(신규 계정과목,
    또는 오탈자가 섞인 헤더)이 들어오면 AccountCategory.OTHER를
    반환해 "가치 판단 없는 중립 서술"로 안전하게 폴백한다.

    03_데이터정제.md의 경고대로, 실제 파일의 헤더 텍스트는 오탈자가
    있을 수 있으므로(예: "원재료비_칼슘연(A" - 닫는 괄호 누락) 이
    함수를 호출하는 쪽에서 헤더 정규화(trim, 괄호 보정 등)를 먼저
    거치는 것을 권장한다.
    """
    return ACCOUNT_CATEGORY_BY_COLUMN.get(metric_name, AccountCategory.OTHER)


@dataclass
class AnalysisRecord:
    """
    F3(증감률·이상징후 계산) 단계의 출력을 그대로 받는 입력 구조.
    실제 필드명은 68개 계정과목 스키마 확정 후 매핑해서 조정하면 된다.
    """

    # 기본 식별자
    team_name: str                       # 예: "영업1팀"
    metric_name: str                     # 예: "매출액", "영업이익"
    period_label: str                    # 예: "2026년 9월"

    # 정량 값
    value: float                         # 당월 실적값
    # 전월 대비 증감률(%) — Optional. 이 프로젝트의 확립된 원칙("비교 불가는 0으로
    # 대체하지 않는다", app/services/aggregation.py·anomaly.py와 동일)에 따라, 전월
    # 비교 자체가 불가능하거나(prev_month_available=False) 애초에 전월 대비 개념이
    # 아닌 지표(예: 계획 대비 달성률)는 None으로 둔다 — NarrativeBuilder가 0%로
    # 꾸며내지 않고 "비교 기준 없음"을 그대로 서술한다(Phase 16, F3 이상징후 연동).
    mom_change_pct: Optional[float] = None
    yoy_change_pct: Optional[float] = None   # 전년 동월 대비 증감률 (%)
    # 연초~직전월 누계 월평균 대비 당월 증감률(%) — Phase 17에서 F3 "누계평균대비"
    # 기준(매출액)용으로 처음 채워 썼고, Phase 20(사용자 확인: "단가 변동에서만
    # 비교해보자")부터는 그 독립 기준이 폐지되며 "단가변동"(평균단가)의 누계 비교로
    # 용도가 옮겨갔다. 필드 자체는 원래 있었지만 NarrativeBuilder에 대응 문구가 없었다.
    ytd_change_pct: Optional[float] = None

    # 계정과목 분류 (03_데이터정제.md §4 그룹과 매핑, 문구의 방향성 판단에 사용)
    account_category: AccountCategory = AccountCategory.OTHER

    # 순위/비교 (동일 그룹 내 상대 위치)
    rank: Optional[int] = None           # 그룹 내 순위 (1위가 최상)
    total_count: Optional[int] = None    # 그룹 전체 개체 수

    # 추세
    trend_direction: TrendDirection = TrendDirection.FLAT
    consecutive_periods: int = 0         # 같은 방향 연속 개월 수
    moving_avg_3m_pct: Optional[float] = None  # 최근 3개월 평균 증감률

    # 이상징후 (F5/F6)
    is_anomaly: bool = False
    threshold_value: Optional[float] = None    # 초과 기준 임계치
    deviation_pct: Optional[float] = None      # 임계치 대비 초과폭(%p)

    # 기여도 분해 (선택 - 있으면 더 풍부한 문장 생성)
    top_contributor: Optional[str] = None      # 예: "B제품군"
    top_contributor_share_pct: Optional[float] = None  # 기여 비중(%)

    # 데이터 품질 플래그 (03_데이터정제.md §4.1 — 부문 값 미인식 시
    # DEFAULT_TEAM(차량OE)으로 대체 처리된 행이 섞여 있는 경우 등)
    is_calc_error: bool = False
    calc_error_reason: Optional[str] = None    # 예: "부문 값 미인식으로 차량OE로 잠정 분류"

    def __post_init__(self) -> None:
        # account_category를 명시적으로 지정하지 않았다면(기본값 OTHER인 채로),
        # metric_name이 실제 Re-arrange 시트 헤더와 일치하는 경우 자동으로 추론한다.
        if self.account_category == AccountCategory.OTHER:
            inferred = ACCOUNT_CATEGORY_BY_COLUMN.get(self.metric_name)
            if inferred is not None:
                self.account_category = inferred


# ─────────────────────────────────────────────────────────────
# 2. 표현 뱅크 (Phrase Bank)
#    같은 의미·강도를 여러 표현으로 갖고 있다가 랜덤하게 선택.
#    → 매번 같은 문장이 나오는 "정해진 템플릿" 느낌을 줄인다.
# ─────────────────────────────────────────────────────────────

class PhraseBank:

    # ---- 방향(증가/감소) × 호오(favorable/unfavorable/neutral) 4+2 조합 ----
    # "증가"라는 사실 자체는 모든 계정과목에서 동일하지만, 그 증가가
    # 좋은 신호인지 나쁜 신호인지는 계정과목(폴라리티)에 따라 달라진다.
    # → 가치가 실린 단어("개선"·"악화")는 favorable/unfavorable 세트에만 넣고,
    #   폴라리티가 없는 항목(수량 등)은 NEUTRAL 세트로 가치중립적으로 서술한다.

    UP_FAVORABLE = {  # 예: 매출·영업이익 증가
        "strong": [
            "뚜렷한 상승세를 보이며 개선되었습니다",
            "큰 폭으로 증가하며 실적이 개선되었습니다",
            "눈에 띄게 증가했습니다",
            "가파른 상승 흐름을 나타냈습니다",
        ],
        "moderate": [
            "완만한 증가세를 나타냈습니다",
            "소폭 개선되었습니다",
            "안정적인 증가 흐름을 보였습니다",
        ],
    }

    UP_UNFAVORABLE = {  # 예: 매출원가·판관비 증가 (비용 부담 확대)
        "strong": [
            "큰 폭으로 증가하며 비용 부담이 확대되었습니다",
            "뚜렷하게 늘어나며 원가 부담이 커졌습니다",
            "가파르게 증가한 것으로 나타났습니다",
        ],
        "moderate": [
            "완만하게 증가하며 다소 부담이 늘었습니다",
            "소폭 증가한 수준입니다",
        ],
    }

    DOWN_FAVORABLE = {  # 예: 매출원가·판관비 감소 (비용 부담 완화)
        "strong": [
            "큰 폭으로 감소하며 비용 부담이 완화되었습니다",
            "뚜렷하게 줄어들며 원가 부담이 낮아졌습니다",
            "가파르게 감소한 것으로 나타났습니다",
        ],
        "moderate": [
            "완만하게 감소하며 부담이 다소 줄었습니다",
            "소폭 감소한 수준입니다",
        ],
    }

    DOWN_UNFAVORABLE = {  # 예: 매출·영업이익 감소
        "strong": [
            "뚜렷한 하락세를 보였습니다",
            "큰 폭으로 감소했습니다",
            "눈에 띄게 위축되었습니다",
            "가파른 하락 흐름을 나타냈습니다",
        ],
        "moderate": [
            "완만한 감소세를 나타냈습니다",
            "소폭 둔화되었습니다",
            "다소 위축되는 흐름을 보였습니다",
        ],
    }

    UP_NEUTRAL = {  # 예: 수량 등 가치 판단이 필요 없는 항목의 증가
        "strong": ["큰 폭으로 증가했습니다", "뚜렷하게 늘어났습니다"],
        "moderate": ["완만하게 증가했습니다", "소폭 늘어났습니다"],
    }

    DOWN_NEUTRAL = {  # 예: 수량 등 가치 판단이 필요 없는 항목의 감소
        "strong": ["큰 폭으로 감소했습니다", "뚜렷하게 줄어들었습니다"],
        "moderate": ["완만하게 감소했습니다", "소폭 줄어들었습니다"],
    }

    FLAT = [
        "전월과 유사한 수준을 유지했습니다",
        "큰 변동 없이 안정적인 흐름을 보였습니다",
        "전월 대비 뚜렷한 변화는 없었습니다",
    ]

    CALC_ERROR = [
        "다만 이 값은 원본 데이터의 분류 항목을 인식하지 못해 잠정 처리된 수치({reason})이므로, 확정 수치가 아닌 참고용으로만 활용해야 합니다",
        "다만 이 수치는 데이터 정제 단계에서 잠정 분류된 값({reason})으로, 원본 확인 전까지는 참고용으로만 활용해야 합니다",
    ]

    @staticmethod
    def move_phrase(pct: float, higher_is_favorable: Optional[bool], intensity: str) -> str:
        """
        방향(부호) × 폴라리티에 맞는 표현을 하나 골라 반환.

        higher_is_favorable: "값이 커지는 쪽이 바람직한가"
            True  -> 매출/이익류 (증가=긍정, 감소=부정)
            False -> 원가/비용류 (증가=부정, 감소=긍정)
            None  -> 가치 판단 없음 (수량 등, 방향만 서술)
        """
        is_up = pct > 0.05
        is_down = pct < -0.05
        if not is_up and not is_down:
            return PhraseBank._pick(PhraseBank.FLAT)

        if higher_is_favorable is None:
            group = PhraseBank.UP_NEUTRAL if is_up else PhraseBank.DOWN_NEUTRAL
        elif is_up:
            # 증가는, "값이 커지는 게 좋은" 계정과목일 때만 긍정적으로 서술
            group = PhraseBank.UP_FAVORABLE if higher_is_favorable else PhraseBank.UP_UNFAVORABLE
        else:
            # 감소는, "값이 커지는 게 좋은" 계정과목일 때만 부정적으로 서술
            # (원가/비용류처럼 감소=좋음인 경우 DOWN_FAVORABLE을 써야 하므로 반대로 뒤집는다)
            group = PhraseBank.DOWN_UNFAVORABLE if higher_is_favorable else PhraseBank.DOWN_FAVORABLE

        return PhraseBank._pick(group[intensity])

    RANK_TOP = [
        "전체 {total}개 팀 중 {rank}위를 기록하며 상위권에 위치했습니다",
        "{total}개 팀 가운데 {rank}위로 두드러진 성과를 보였습니다",
    ]

    RANK_BOTTOM = [
        "전체 {total}개 팀 중 {rank}위에 머물렀습니다",
        "{total}개 팀 가운데 하위권인 {rank}위를 기록했습니다",
    ]

    TREND_CONTINUATION = [
        "{n}개월 연속 {direction} 흐름이 이어지고 있습니다",
        "{n}개월째 {direction} 추세가 지속되고 있습니다",
    ]

    VS_MOVING_AVG_ABOVE = [
        "직전 3개월 평균 증감률({avg:.1f}%) 대비 두드러진 상승 폭입니다",
        "최근 3개월 평균({avg:.1f}%)을 크게 웃도는 수준입니다",
    ]

    VS_MOVING_AVG_BELOW = [
        "직전 3개월 평균 증감률({avg:.1f}%)에는 다소 못 미치는 수준입니다",
        "최근 3개월 평균({avg:.1f}%) 대비로는 상대적으로 낮은 수준입니다",
    ]

    CONTRIBUTOR = [
        "이 중 {contributor}이(가) 전체 변동의 {share:.0f}%가량을 차지하며 주된 변동 요인으로 나타났습니다",
        "{contributor}의 비중이 {share:.0f}%로 가장 커, 해당 항목이 변동을 주도한 것으로 확인됩니다",
    ]

    ANOMALY = [
        "다만 임계치({threshold:g}) 대비 {deviation:.1f}%p 초과하여 이상징후로 분류되었으며, 별도 검토가 필요합니다",
        "다만 사전 설정된 임계치({threshold:g})를 {deviation:.1f}%p 초과해 확인이 필요한 항목으로 표시되었습니다",
    ]

    YOY_CLAUSE = [
        "전년 동월 대비로는 {pct:+.1f}% {word}",
    ]

    # Phase 17(.docs/phase/phase_17_이상징후판정범위조정.md, 사용자 확인) — "연초~직전월
    # 월평균 대비" 편차를 서술하는 문구. ytd_change_pct 필드는 원래부터 선언돼 있었지만
    # NarrativeBuilder에 대응 절이 없었다 — 새 필드를 추가하는 대신 이 필드를 그 용도로
    # 채운다.
    YTD_CLAUSE = [
        "연초 이후 누계 월평균 대비로는 {pct:+.1f}% {word}",
    ]

    @staticmethod
    def _pick(options: list[str]) -> str:
        return random.choice(options)


# ─────────────────────────────────────────────────────────────
# 3. 서사 조립 엔진 (Narrative Builder)
#    headline(핵심 요약) → supporting detail(근거/맥락) → caution(주의사항)
#    순서로 문장을 쌓아 하나의 분석 문단을 만든다.
# ─────────────────────────────────────────────────────────────

STRONG_THRESHOLD_PCT = 10.0   # 이 값 이상이면 "강한" 변화로 분류


# Phase 21(.docs/phase/phase_21_코멘트조사자동화및방어처리.md) — 이 프로젝트가 실제로
# 쓰지 않는 별도 초안(plan_variance_comment_generator.py가 짝으로 삼던 루트의
# comment_generator.py)을 검토해 이식했다. 그동안 문장마다 "은(는)"을 그대로 노출해
# 문법적으로 어색했는데, 받침 유무로 정확한 조사를 고른다.
def _has_batchim(word: str) -> bool:
    """마지막 글자에 받침이 있는지 판정 (한글이 아니면 받침 없는 것으로 취급)."""
    if not word:
        return False
    last_char = word[-1]
    code = ord(last_char)
    if 0xAC00 <= code <= 0xD7A3:
        return (code - 0xAC00) % 28 != 0
    return False


def _eun_neun(word: str) -> str:
    """단어 뒤에 붙일 조사 '은/는'을 받침 유무에 맞게 선택."""
    return "은" if _has_batchim(word) else "는"


class NarrativeBuilder:

    def __init__(self, record: AnalysisRecord, seed: Optional[int] = None):
        self.r = record
        if seed is not None:
            random.seed(seed)  # 테스트 시 결과 고정용 (운영에서는 미사용 권장)

    # ---- 1) headline: 이번 기간의 핵심 변화를 한 문장으로 ----
    def _headline(self) -> str:
        r = self.r
        pct = r.mom_change_pct

        # 전월 비교 자체가 불가능한 경우(prev_month_available=False) 또는 애초에
        # "전월 대비 %" 개념이 아닌 지표(계획 대비 달성률 등)는 mom_change_pct가
        # None으로 들어온다 — 0%로 꾸며내지 않고 당월 값만 사실대로 서술한다
        # (이 프로젝트의 "비교 불가는 0으로 대체하지 않는다" 원칙, Phase 16).
        if pct is None:
            return (
                f"{r.team_name}{_eun_neun(r.team_name)} {r.period_label} {r.metric_name}에서 "
                f"{r.value:,.0f}을(를) 기록했습니다(전월 비교 가능한 데이터가 없습니다)."
            )

        intensity = "strong" if abs(pct) >= STRONG_THRESHOLD_PCT else "moderate"

        favorable = _HIGHER_IS_FAVORABLE.get(r.account_category, None)
        phrase = PhraseBank.move_phrase(pct, favorable, intensity)

        sign = "+" if pct >= 0 else ""
        return (
            f"{r.team_name}{_eun_neun(r.team_name)} {r.period_label} {r.metric_name}에서 "
            f"전월 대비 {sign}{pct:.1f}%를 기록하며 {phrase}."
        )

    # ---- 2) supporting detail: 순위/추세/기여도 등 맥락 결합 ----
    def _supporting_details(self) -> list[str]:
        r = self.r
        sentences: list[str] = []

        # 순위 맥락
        if r.rank is not None and r.total_count:
            if r.rank <= max(1, r.total_count // 3):
                template = PhraseBank._pick(PhraseBank.RANK_TOP)
            else:
                template = PhraseBank._pick(PhraseBank.RANK_BOTTOM)
            sentences.append(template.format(total=r.total_count, rank=r.rank) + ".")

        # 이동평균 대비 맥락
        if r.moving_avg_3m_pct is not None:
            if r.mom_change_pct > r.moving_avg_3m_pct:
                template = PhraseBank._pick(PhraseBank.VS_MOVING_AVG_ABOVE)
            else:
                template = PhraseBank._pick(PhraseBank.VS_MOVING_AVG_BELOW)
            sentences.append(template.format(avg=r.moving_avg_3m_pct) + ".")

        # 연속 추세
        if r.consecutive_periods >= 2 and r.trend_direction != TrendDirection.FLAT:
            direction_word = "증가" if r.trend_direction == TrendDirection.UP else "감소"
            template = PhraseBank._pick(PhraseBank.TREND_CONTINUATION)
            sentences.append(
                template.format(n=r.consecutive_periods, direction=direction_word) + "."
            )

        # 전년 동월 비교
        if r.yoy_change_pct is not None:
            word = "증가했습니다" if r.yoy_change_pct >= 0 else "감소했습니다"
            template = PhraseBank._pick(PhraseBank.YOY_CLAUSE)
            sentences.append(template.format(pct=r.yoy_change_pct, word=word) + ".")

        # 연초~직전월 누계 월평균 비교(Phase 17)
        if r.ytd_change_pct is not None:
            word = "증가했습니다" if r.ytd_change_pct >= 0 else "감소했습니다"
            template = PhraseBank._pick(PhraseBank.YTD_CLAUSE)
            sentences.append(template.format(pct=r.ytd_change_pct, word=word) + ".")

        # 기여도 분해
        if r.top_contributor and r.top_contributor_share_pct is not None:
            template = PhraseBank._pick(PhraseBank.CONTRIBUTOR)
            sentences.append(
                template.format(
                    contributor=r.top_contributor,
                    share=r.top_contributor_share_pct,
                )
                + "."
            )

        return sentences

    # ---- 3) caution: 이상징후 / 데이터 품질 문제가 있을 때만 마지막에 덧붙임 ----
    def _cautions(self) -> list[str]:
        r = self.r
        cautions: list[str] = []

        if r.is_anomaly:
            threshold = r.threshold_value if r.threshold_value is not None else 0.0
            deviation = r.deviation_pct if r.deviation_pct is not None else 0.0
            template = PhraseBank._pick(PhraseBank.ANOMALY)
            cautions.append(template.format(threshold=threshold, deviation=deviation) + ".")

        # 데이터 품질 플래그: 03_데이터정제.md §4.1 - 부문 값 미인식 등으로
        # 잠정 분류된 행이 섞여 있으면, 이 수치를 확정치처럼 서술하지 않도록
        # 반드시 별도 문장으로 명시한다 (정성 코멘트가 오분류 데이터를
        # 정상 분석 결과처럼 포장하는 것을 막기 위함).
        if r.is_calc_error:
            reason = r.calc_error_reason or "분류 오류"
            template = PhraseBank._pick(PhraseBank.CALC_ERROR)
            cautions.append(template.format(reason=reason) + ".")

        return cautions

    def build(self) -> str:
        parts = [self._headline()]
        parts.extend(self._supporting_details())
        parts.extend(self._cautions())
        return " ".join(parts)


# ─────────────────────────────────────────────────────────────
# 4. 외부 노출 함수 (FastAPI 서비스 계층에서 이걸 호출)
# ─────────────────────────────────────────────────────────────

def generate_comment(record: AnalysisRecord, seed: Optional[int] = None) -> str:
    """
    단일 레코드(팀/계정과목 1건)에 대한 분석 문단을 생성한다.

    Parameters
    ----------
    record : AnalysisRecord
        F3 단계에서 계산된 정량 분석 결과.
    seed : int, optional
        표현 뱅크의 랜덤 선택을 고정하고 싶을 때 (예: 유닛 테스트,
        스냅샷 회귀 테스트). 운영 환경에서는 넘기지 않는 것을 권장.

    Returns
    -------
    str
        사람이 읽는 분석 문단 (원인 추정 없이 수치 기반 서술만 포함).
    """
    return NarrativeBuilder(record, seed=seed).build()


def generate_comments_bulk(records: list[AnalysisRecord]) -> list[dict]:
    """
    여러 레코드를 일괄 처리해 {식별자, 코멘트} 딕셔너리 리스트로 반환.
    F7 보고서 초안 생성 시 팀/계정과목별로 순회 호출하는 용도.
    """
    results = []
    for r in records:
        results.append(
            {
                "team_name": r.team_name,
                "metric_name": r.metric_name,
                "period_label": r.period_label,
                "account_category": r.account_category.value,
                "comment": generate_comment(r),
            }
        )
    return results


# ─────────────────────────────────────────────────────────────
# 5. 사용 예시 / 동작 확인용 (실제 서비스에는 import만 해서 사용)
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 예시 1: 영업이익 강한 증가 + 이상징후 + 기여도 (REVENUE/PROFIT 계열 → 증가=긍정)
    sample = AnalysisRecord(
        team_name="영업1팀",
        metric_name="영업이익",
        period_label="2026년 9월",
        value=1_250_000_000,
        mom_change_pct=14.7,
        account_category=AccountCategory.OPERATING_PROFIT,
        yoy_change_pct=8.2,
        rank=1,
        total_count=8,
        trend_direction=TrendDirection.UP,
        consecutive_periods=3,
        moving_avg_3m_pct=6.5,
        is_anomaly=True,
        threshold_value=10.0,
        deviation_pct=4.7,
        top_contributor="B제품군",
        top_contributor_share_pct=62.0,
    )
    print("=== 예시 1: 영업이익 강한 증가 (증가=긍정) ===")
    for i in range(2):
        print(f"[{i+1}]", generate_comment(sample))
    print()

    # 예시 2: 매출액 완만한 감소, 이상징후 없음 (REVENUE → 증가=긍정)
    sample2 = AnalysisRecord(
        team_name="영업3팀",
        metric_name="매출액",
        period_label="2026년 9월",
        value=430_000_000,
        mom_change_pct=-2.1,
        account_category=AccountCategory.REVENUE,
        rank=7,
        total_count=8,
        trend_direction=TrendDirection.DOWN,
        consecutive_periods=1,
        moving_avg_3m_pct=1.0,
        is_anomaly=False,
    )
    print("=== 예시 2: 매출액 완만한 감소 ===")
    for i in range(2):
        print(f"[{i+1}]", generate_comment(sample2))
    print()

    # 예시 3: 원재료비(COGS) 강한 증가 → 증가=부정(비용 부담 확대)로 서술되어야 함
    sample3 = AnalysisRecord(
        team_name="차량OE팀",
        metric_name="원재료비",
        period_label="2026년 9월",
        value=812_000_000,
        mom_change_pct=13.2,
        account_category=AccountCategory.COGS,
        rank=2,
        total_count=4,
        trend_direction=TrendDirection.UP,
        consecutive_periods=2,
        moving_avg_3m_pct=5.0,
    )
    print("=== 예시 3: 원재료비(COGS) 강한 증가 — '개선'이 아니라 '비용 부담 확대'로 서술 ===")
    for i in range(2):
        print(f"[{i+1}]", generate_comment(sample3))
    print()

    # 예시 4: 판관비(SGA) 감소 → 증가=부정 계열이므로 감소는 긍정(부담 완화)으로 서술
    sample4 = AnalysisRecord(
        team_name="산전모티브팀",
        metric_name="판관비(최종마감)",
        period_label="2026년 9월",
        value=305_000_000,
        mom_change_pct=-11.4,
        account_category=AccountCategory.SGA,
    )
    print("=== 예시 4: 판관비(SGA) 강한 감소 — '부담 완화'로 서술 ===")
    for i in range(2):
        print(f"[{i+1}]", generate_comment(sample4))
    print()

    # 예시 5: 03_데이터정제.md §4.1 - "부문" 값 미인식으로 DEFAULT_TEAM(차량OE) 처리된
    # 행이 섞여 있는 경우 (is_calc_error). 수량(QUANTITY)은 가치중립적으로 서술.
    sample5 = AnalysisRecord(
        team_name="차량OE팀",
        metric_name="수량(22.9cell)",
        period_label="2026년 9월",
        value=98_500,
        mom_change_pct=4.3,
        account_category=AccountCategory.QUANTITY,
        is_calc_error=True,
        calc_error_reason="부문 값 미인식으로 차량OE로 잠정 분류",
    )
    print("=== 예시 5: 수량(QUANTITY, 가치중립) + 데이터 품질 플래그(is_calc_error) ===")
    for i in range(2):
        print(f"[{i+1}]", generate_comment(sample5))
