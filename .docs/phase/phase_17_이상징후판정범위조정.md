# Phase 17 작업 계획서 — 이상징후 판정 범위 조정(계획대비=팀 단위, 누계평균대비 신설)

- 근거: 사용자 요청(원문) — "판정에 있어서 각 팀의 제품군에 대한 분석은 전월 또는 누계 평균 대비를 위주로 분석하고, 계획대비에 대한 분석은 팀 계획 vs 팀 실적을 기본으로 한다."
- 사용자 확인(2026-09-28): 누계평균 = 연초~직전월의 월평균(당월 제외), 기본 임계치 15%(전년대비와 동일).

## 배경/동기

`app/services/anomaly.py`가 F3의 6개 판정 기준을 전부 "팀×제품군" 단위(`aggregated_result` 1행)로 평가하고 있었는데, 그중 계획대비(`achievement_rate`)는 실제로는 버그였다 — `aggregation.py`가 저장하는 `plan_amount`는 이미 "그 팀의 월간 계획 총액"이 모든 제품군 행에 그대로 복제된 값인데(코드 주석에 명시), `achievement_rate = actual_amount(제품군 하나) / plan_amount(팀 전체)`로 계산하고 있어 제품군 단위로 보면 항상 미달로 나온다. F4/PDF의 팀별 목표 대비 실적 표는 이미 팀 단위로 올바르게 계산하고 있었지만(`app/services/analytics.py`의 `TEAM_ROLLUP_SQL`), F3 이상징후 판정만 이 버그를 갖고 있었다.

## 범위

**구현**:
1. `app/services/thresholds.py`에 `METRIC_CUMULATIVE_AVG = "누계평균대비"` 신설, 기본 임계치 15%로 시딩.
2. `app/services/anomaly.py`:
   - 계획대비: 팀×제품군 루프에서 빼서, 팀 단위로 한 번만 평가(팀의 제품군 행 전체 `actual_amount` 합계 vs 팀 계획)하도록 재구성.
   - 누계평균대비 신설: 팀×제품군 단위로, 연초~직전월(당월 제외) `aggregated_result.actual_amount` 월평균과 당월 실적을 비교.
3. `app/services/comment_generator.py`: 기존 `ytd_change_pct` 필드(선언만 되어 있고 실사용처가 없었음, 한글 주석도 "누계 대비 증감률"로 이미 의미가 일치)를 새 필드 추가 대신 재사용해 "연초~직전월 누계 월평균 대비 당월 증감률(%)"을 담도록 필드 주석을 갱신하고, `YTD_CLAUSE` 문구뱅크 항목 + `_supporting_details()` 분기를 추가했다(당초 계획한 `cumulative_avg_change_pct` 신규 필드 대신 — 기존 미사용 필드를 활용하는 편이 더 적은 변경으로 동일 목적을 달성한다고 판단, "최근 3개월 평균" `moving_avg_3m_pct`와는 여전히 별개 필드).
4. `app/services/report_analysis_mapper.py`: 신규 metric_type 매핑 추가, 계획대비는 팀 전체 합계를 다시 조회해 `value`를 채우고 라벨도 제품군 없이 팀명만 쓰도록 수정.
5. `.docs/02_prd.md`의 F3 표에 7번째 기준(누계평균대비) 추가 + 판정 단위(팀×제품군 vs 팀) 컬럼 신설로 계획대비가 팀 단위임을 명시. (완료)

## 완료 보고

- 백엔드 전체 pytest 184개 전부 통과 확인.
- 실제 로컬 DuckDB(`backend/data/app.duckdb`)에 대해 서버 기동 후 `GET /thresholds`로 7개 기준이 기존 DB에도 자동 시딩됨을 확인, 실제 배치(2026-08)에 `POST /batches/{id}/recompute` 실행 후 `GET /batches/{id}/anomalies`로 계획대비 플래그가 팀당 1건(제품군 없음)으로, 누계평균대비 플래그가 팀×제품군 단위로 생성됨을 확인했다.

**범위 밖**:
- 단가변동/판관비급증/흑자전환은 이번 요청 대상이 아니라 그대로 둔다(이미 전월 대비 기반).

## 방법·완료 기준

- `anomaly.py`의 계획대비가 팀당 최대 1건만 플래그하고, `actual_value`가 팀 합계 기준 달성률과 일치.
- 누계평균대비가 1월(직전월 없음)에는 플래그되지 않고, 연초~직전월 평균과 당월의 편차가 임계치를 넘을 때만 플래그.
- 백엔드 전체 pytest 통과.
