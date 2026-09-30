"""손익센터 코드 -> 팀 분류, 팀 -> 매핑표 조회 접두사.

docs/03_데이터정제.md §4.1 검증된 수식:
  팀 = IF(손익센터=20342,"모티브", IF(손익센터=20345,"고정형",
        IF(손익센터=20313,"차량대리점","차량OE")))

주의: 이 4개 분기만 원본 수식에서 확인되었다. PRD 10장 미해결 질문 13번에서
"산전팀"이 별도 팀으로 존재하는지(실제 참고 양식 기준) 재확인이 필요하다고
기록되어 있으므로, 검증되지 않은 5번째 팀을 여기서 임의로 추가하지 않는다.

일부 실적 파일(예: "Raw Data_업로드용.xlsb")은 "손익 센터" 컬럼 대신
"부문" 컬럼으로 팀을 구분한다(.docs/03_데이터정제.md §4.1 확장 참고).
"부문" 값은 손익센터와 다른 코드 체계("2610 산전고정형팀"처럼 4자리 코드 +
"산전"(모티브·고정형만) + 팀명 + "팀")를 쓰지만, 접두사를 뗀 팀명은 손익센터
분류와 동일한 4개 팀에 대응된다 — 08월 실제 "Raw Data_업로드용.xlsb" 전체
7676행에서 정확히 이 4개 값만 확인했다(사용자 확인: 두 컬럼 방식 모두 지원).
"""
from __future__ import annotations

_PROFIT_CENTER_TEAM_MAP = {
    20342: "모티브",
    20345: "고정형",
    20313: "차량대리점",
}

DEFAULT_TEAM = "차량OE"

# 매핑표(제품분류) 조회 시 실제 사용되는 키 접두사.
# 모티브·고정형은 팀명이 아니라 "산전"으로 조회한다 (검증된 quirk).
_MAPPING_PREFIX_OVERRIDE = {
    "모티브": "산전",
    "고정형": "산전",
}

# "부문" 컬럼 값 -> 팀 (실측된 4개 값만 등록, 근거 없는 5번째 값 추가 금지)
_DIVISION_TEAM_MAP = {
    "2630 차량대리점팀": "차량대리점",
    "2640 차량OE팀": "차량OE",
    "2620 산전모티브팀": "모티브",
    "2610 산전고정형팀": "고정형",
}


def classify_team(profit_center_code: int) -> str:
    return _PROFIT_CENTER_TEAM_MAP.get(int(profit_center_code), DEFAULT_TEAM)


def classify_team_from_division(division_value: str) -> str:
    """"부문" 컬럼 값(예: "2630 차량대리점팀")을 팀으로 분류한다.

    실측된 4개 값 외에는 근거가 없으므로 임의로 매핑하지 않고 예외를 던진다
    (호출부에서 계산오류로 처리하고 DEFAULT_TEAM으로 계속 진행한다).
    """
    value = (division_value or "").strip()
    team = _DIVISION_TEAM_MAP.get(value)
    if team is None:
        raise ValueError(f"부문 값을 팀으로 분류할 수 없습니다: {division_value!r}")
    return team


def mapping_prefix(team: str) -> str:
    return _MAPPING_PREFIX_OVERRIDE.get(team, team)
