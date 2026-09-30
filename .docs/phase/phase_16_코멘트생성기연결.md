# Phase 16 작업 계획서 — F3 이상징후 계산 결과를 comment_generator.AnalysisRecord로 매핑해 F7에 연결

- 근거: 사용자 요청(원문) — "실제 F3 계산 코드(증감률/이상징후 계산 부분)를 보여주면서 '이 결과를 comment_generator.AnalysisRecord로 매핑해서 F7 보고서 생성에 연결해줘'" (`@backend/app/services/comment_generator.py`).

## 배경/동기

`app/services/comment_generator.py`는 이번 세션에서 다룬 적 없는 기존 파일로, 규칙/표현뱅크 기반의 더 풍부한 서사형 코멘트 생성기(`AnalysisRecord` 입력 → `NarrativeBuilder`가 headline/근거/주의 3단 문단 조립)다. 현재 F7(`app/services/reports.py`)은 더 단순한 `app/services/comments.py`(단문 사실 서술)를 쓰고 있다 — 이번 작업은 F3(`app/services/anomaly.py`)가 계산한 실제 이상징후 결과를 `comment_generator.AnalysisRecord`로 변환해 F7이 `comments.py` 대신 이걸 쓰도록 바꾸는 것이다.

## 범위

**구현**:
1. `comment_generator.py`의 `AnalysisRecord.mom_change_pct`를 `Optional[float] = None`으로 바꾼다 — 지금은 필수 필드라 항상 값을 채워야 하는데, F3의 6개 판정 기준 중 일부(계획대비 달성률, 흑자전환)는 애초에 "전월 대비 %" 개념이 아니고, 전월 비교 자체가 불가능한 경우(`prev_month_available=False`)도 있다. 이 프로젝트 전체의 확립된 원칙("비교 불가는 0으로 대체하지 않는다", `app/services/aggregation.py`/`anomaly.py`에 이미 적용됨)과 같은 원칙을 따라, 비교 불가를 0%로 꾸며내지 않고 `NarrativeBuilder`가 "비교 기준 없음"을 자연스럽게 서술하도록 만든다.
2. 신규 `app/services/report_analysis_mapper.py` — `build_analysis_records(db, batch_id) -> list[AnalysisRecord]`. `anomaly_flag`를 `aggregated_result`(result_id로 JOIN)와 결합해 각 이상징후 유형(전월대비/전년대비/계획대비/흑자전환/단가변동/판관비급증)에 맞는 `metric_name`·`value`·`mom_change_pct`·`yoy_change_pct`·`account_category`·`is_anomaly`·`threshold_value`·`deviation_pct`를 채운다. 근거 없이 순위(rank)·기여도(top_contributor)·이동평균 등은 F3가 계산하지 않으므로 채우지 않는다(None으로 남겨 `NarrativeBuilder`가 해당 문장을 생략하게 함).
3. `app/services/reports.py`의 `create_report_draft`가 `comments.generate_comment(flag)` 대신 `report_analysis_mapper.build_analysis_records` + `comment_generator.generate_comment(record)`를 쓰도록 교체한다.
4. `app/services/comments.py`는 삭제하지 않는다(사용자가 별도로 요청하지 않음, `tests/test_comments.py`가 독립적으로 계속 검증) — F7에서의 참조만 교체한다.

**범위 밖**:
- rank/moving_avg_3m_pct/top_contributor/consecutive_periods/trend_direction의 연속 개월 추적 — F3가 현재 이런 값을 계산·저장하지 않는다. 근거 없이 만들어내지 않고 기본값(None/0/FLAT)으로 둔다.
- `is_calc_error` 연동 — `refined_sales_record.is_calc_error`는 팀×제품군 집계 단위가 아니라 원본 행 단위라, 이번 매핑에서는 반영하지 않는다(향후 필요 시 별도 확인).

## 방법

1. `comment_generator.py` 수정: `mom_change_pct: Optional[float] = None`, `_headline()`이 None일 때 "비교 가능한 전월 데이터가 없어 이번 기간 값만 서술" 계열의 중립 문구로 대체.
2. `app/services/report_analysis_mapper.py` 신규 작성.
3. `app/services/reports.py` 수정.
4. 테스트: 매퍼 단위 테스트(6개 metric_type 전부), F7 통합 테스트(auto_comment가 comment_generator 스타일 문장을 담는지 확인), comment_generator의 mom_change_pct=None 케이스 테스트.

## 완료 기준

- F7 보고서 초안 생성 시 `auto_comment`가 `comment_generator.generate_comment()`가 만든 서사형 문장이다.
- 전월 비교가 불가능한 이상징후 항목도 크래시 없이 자연스러운 문장을 생성한다(0%로 꾸며내지 않음).
- 백엔드 전체 pytest 통과.
