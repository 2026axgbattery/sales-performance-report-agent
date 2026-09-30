"""F6. 임계치 설정 — F3의 6개 판단 기준 기본값과 조회/저장.

docs/02_prd.md F3 표(제안 기본 임계치)와 동일한 기본값을 사용한다.
"계획 대비 달성률"만 상/하한 두 값을 쓰고, 나머지는 단일 값(threshold_value)을 쓴다.
"흑자→적자 전환"은 임계치 없이 조건 충족 시 항상 플래그하므로 값이 없다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

METRIC_PREV_MONTH = "전월대비"
METRIC_PREV_YEAR = "전년대비"
METRIC_PLAN_ACHIEVEMENT = "계획대비"
METRIC_PROFIT_TURN_NEGATIVE = "흑자전환"
METRIC_UNIT_PRICE = "단가변동"
METRIC_SGA_SURGE = "판관비급증"
# Phase 18(.docs/phase/phase_18_손익항목계획대비판정.md, 사용자 확인) — 손익 상세
# 분석(pl_comparison.py)의 계정과목(재료비/노무비/경비/판관비 세부)별로 팀 계획 대비
# 실적이 얼마나 벗어났는지 판정한다. 계획대비(METRIC_PLAN_ACHIEVEMENT)가 팀의 매출
# 달성률(%)을 보는 것과 달리, 이건 팀의 "비용 항목"별 계획 대비 증감율(%)을 본다.
METRIC_PL_ITEM_PLAN = "손익항목계획대비"
# Phase 17에서 신설했던 "누계평균대비"(매출액을 연초~직전월 평균과 비교)는 Phase 20
# (.docs/phase/phase_20_단가변동누계평균통합.md, 사용자 확인 — "누계 평균대비는 별도의
# 버튼으로 분류하지 말고... 단가 변동에서만 비교해보자")에서 폐지했다 — 매출액
# 누계평균 비교는 완전히 없애고, 그 "누계평균 비교" 개념만 단가변동(METRIC_UNIT_PRICE)
# 안에 흡수시켰다(app/services/anomaly.py 참고, 전월/누계 중 하나라도 임계치를 넘으면
# 단가변동 하나로 플래그하고 화면에 둘 다 보여줌).

ALL_METRICS = [
    METRIC_PREV_MONTH,
    METRIC_PREV_YEAR,
    METRIC_PLAN_ACHIEVEMENT,
    METRIC_PROFIT_TURN_NEGATIVE,
    METRIC_UNIT_PRICE,
    METRIC_SGA_SURGE,
    METRIC_PL_ITEM_PLAN,
]

DEFAULTS: dict[str, dict[str, float | None]] = {
    METRIC_PREV_MONTH: {"threshold_value": 10.0, "threshold_low": None, "threshold_high": None},
    METRIC_PREV_YEAR: {"threshold_value": 15.0, "threshold_low": None, "threshold_high": None},
    METRIC_PLAN_ACHIEVEMENT: {"threshold_value": None, "threshold_low": 90.0, "threshold_high": 120.0},
    METRIC_PROFIT_TURN_NEGATIVE: {"threshold_value": None, "threshold_low": None, "threshold_high": None},
    METRIC_UNIT_PRICE: {"threshold_value": 5.0, "threshold_low": None, "threshold_high": None},
    METRIC_SGA_SURGE: {"threshold_value": 20.0, "threshold_low": None, "threshold_high": None},
    # 사용자 확인: 전월대비와 같은 10%.
    METRIC_PL_ITEM_PLAN: {"threshold_value": 10.0, "threshold_low": None, "threshold_high": None},
}


@dataclass
class Threshold:
    metric_type: str
    threshold_value: float | None
    threshold_low: float | None
    threshold_high: float | None


def seed_default_thresholds(db) -> None:
    """threshold_config에 없는 metric_type만 기본값으로 채운다(있는 건 건드리지 않음).
    "완전히 비어 있을 때만" 체크하면, 기존 로컬 DB에 이미 6개가 시딩된 뒤 새 metric_type
    (예: Phase 17의 "누계평균대비")을 ALL_METRICS에 추가해도 그 DB에는 영영 안 채워진다
    — 매번 "이미 있는 metric_type"을 확인해 빠진 것만 채우도록 해야 새 기준이 기존
    로컬 DB에서도 안전하게 나타난다(app/db.py의 COLUMN_MIGRATIONS와 같은 이유).

    반대 방향(기준이 없어진 경우)도 정리한다 — Phase 20에서 "누계평균대비"를
    ALL_METRICS에서 뺐는데 삭제 로직이 없으면, 이미 이 기준을 시딩해둔 기존 로컬
    DB에는 고아 행으로 영원히 남아 GET /thresholds에 유령처럼 계속 나타난다."""
    placeholders = ", ".join(["?"] * len(ALL_METRICS))
    db.connection.execute(
        f"DELETE FROM threshold_config WHERE metric_type NOT IN ({placeholders})", ALL_METRICS
    )

    existing_metrics = {
        r[0] for r in db.connection.execute("SELECT metric_type FROM threshold_config").fetchall()
    }
    now = datetime.now()
    for metric in ALL_METRICS:
        if metric in existing_metrics:
            continue
        defaults = DEFAULTS[metric]
        db.connection.execute(
            "INSERT INTO threshold_config "
            "(config_id, metric_type, threshold_value, threshold_low, threshold_high, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                str(uuid.uuid4()),
                metric,
                defaults["threshold_value"],
                defaults["threshold_low"],
                defaults["threshold_high"],
                now,
            ],
        )


def get_thresholds(db) -> dict[str, Threshold]:
    seed_default_thresholds(db)
    rows = db.connection.execute(
        "SELECT metric_type, threshold_value, threshold_low, threshold_high FROM threshold_config"
    ).fetchall()
    return {
        r[0]: Threshold(metric_type=r[0], threshold_value=r[1], threshold_low=r[2], threshold_high=r[3])
        for r in rows
    }


class UnknownMetricError(ValueError):
    pass


def update_thresholds(db, updates: list[dict]) -> dict[str, Threshold]:
    """updates: [{"metric_type": ..., "threshold_value"?: ..., "threshold_low"?: ..., "threshold_high"?: ...}]"""
    seed_default_thresholds(db)
    now = datetime.now()
    for update in updates:
        metric = update.get("metric_type")
        if metric not in ALL_METRICS:
            raise UnknownMetricError(f"알 수 없는 판단 기준입니다: {metric}")
        db.connection.execute(
            "UPDATE threshold_config SET "
            "threshold_value = COALESCE(?, threshold_value), "
            "threshold_low = COALESCE(?, threshold_low), "
            "threshold_high = COALESCE(?, threshold_high), "
            "updated_at = ? "
            "WHERE metric_type = ?",
            [
                update.get("threshold_value"),
                update.get("threshold_low"),
                update.get("threshold_high"),
                now,
                metric,
            ],
        )
    return get_thresholds(db)
