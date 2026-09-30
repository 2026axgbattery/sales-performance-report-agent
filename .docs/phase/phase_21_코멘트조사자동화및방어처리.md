# Phase 21 작업 계획서 — 은/는 조사 자동 선택 + F7 코멘트 생성 방어 처리

- 근거: 사용자가 검토를 요청한 `plan_variance_comment_generator.py`/`comment_generator.py`(루트, 이 프로젝트가 실제로 쓰지 않는 별도 초안) 분석 결과, 그중 두 가지 아이디어만 이 프로젝트에 부분 이식하기로 확인함(사용자: "1~2번만 반영해보자").

## 배경/동기

1. **은/는 조사 자동 선택**: 현재 `backend/app/services/comment_generator.py`와 `pl_item_analysis.py`는 문법적으로 항상 어색한 "은(는)"을 그대로 노출한다. 검토한 루트 `comment_generator.py`에는 받침 유무로 "은"/"는"을 정확히 골라주는 `_eun_neun`/`_has_batchim` 헬퍼가 있다.
2. **F7 코멘트 생성 방어 처리**: `app/services/reports.py`의 `create_report_draft()`는 `generate_comment()`/`format_pl_item_comment()` 호출에 try/except가 전혀 없어, 항목 1건에서 예외가 나면 F7 초안 생성 전체가 500으로 죽는다(게다가 `report_draft` 행은 이미 커밋된 채 항목 없는 "유령 초안"이 남는다). 이 프로젝트가 `uploads.py`/`refinement.py`에서 이미 쓰는 "행 1개 실패가 전체를 안 죽인다" 원칙과 어긋난다.

## 범위

**구현**:
1. `app/services/comment_generator.py`에 `_has_batchim`/`_eun_neun`(검토한 루트 버전에서 그대로 이식)을 추가하고, `NarrativeBuilder._headline()`의 두 곳(`pct is None` 분기·정상 분기)에서 `"은(는)"`을 `f"{r.team_name}{_eun_neun(r.team_name)}"`로 교체한다.
2. `app/services/pl_item_analysis.py`의 `format_pl_item_comment()` 3곳(단위당 매출액 분기, 단위당+총액 분기, 총액만 분기)도 동일하게 교체한다.
3. `app/services/reports.py`의 `create_report_draft()`: 두 루프(`build_analysis_records` 결과 루프, `pl_item_flags` 루프) 각각에서 코멘트 생성 호출을 항목 단위 try/except로 감싸, 실패한 항목은 "[코멘트 생성 실패] ... 원본 수치를 직접 확인해 주세요" 플레이스홀더로 대체하고 나머지 항목은 계속 처리한다. 새 DB 컬럼이나 API 응답 필드는 추가하지 않는다(플레이스홀더 자체가 `auto_comment`에 그대로 저장되므로 기존 스키마로 충분).

**범위 밖**: 나머지 두 아이디어(미매핑 경고 문장, 다중 지표 동시 초과 경고)는 이번에 반영하지 않는다(사용자 확인).

## 방법·완료 기준

- `_eun_neun("모티브")=="는"`, `_eun_neun("차량대리점")=="은"` 등 받침 유무에 따라 정확히 선택되는지 단위 테스트로 확인.
- 코멘트 생성 중 강제로 예외를 일으켜도(예: 레코드 몰킹) F7 초안 생성이 500으로 죽지 않고 해당 항목만 플레이스홀더로 대체되는지 회귀 테스트로 확인(Edit 도구로 일부러 예외를 넣어 테스트가 실제로 이 상황을 잡는지 검증 후 원복).
- 백엔드 전체 pytest, 프론트 영향 없음(백엔드 전용 변경).

## 완료 보고

- `comment_generator.py`에 `_has_batchim`/`_eun_neun`을 추가하고 `NarrativeBuilder._headline()` 두 분기, `pl_item_analysis.format_pl_item_comment()` 세 분기의 "은(는)" 리터럴을 교체했다.
- `reports.py`의 두 코멘트 생성 루프(`build_analysis_records` 루프, `pl_item_flags` 루프)를 항목 단위 try/except로 감싸 실패 시 플레이스홀더로 대체하도록 고쳤다.
- 신규 테스트: `test_comment_generator.py`(조사 선택 4건), `test_pl_item_analysis.py`에 조사 검증 2건 추가, `test_reports_api.py`에 `monkeypatch`로 코멘트 생성 실패를 강제해 F7 초안이 죽지 않고 실패 항목만 플레이스홀더가 되는지 검증하는 회귀 테스트 1건(Edit 도구로 try/except를 일시적으로 제거해 테스트가 실제로 실패함을 확인한 뒤 복구).
- 백엔드 전체 215개 통과. 프론트 변경 없음(백엔드 전용).
