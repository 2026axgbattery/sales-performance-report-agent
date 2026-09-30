# Phase 19 작업 계획서 — 실적 파일 다중 월 자동 분할 업로드 + 겹치는 달 덮어쓰기 확인

- 근거: 사용자가 F4 Overview에서 "7월 선택 시 수량·매출 표시 등이 안 맞는다"고 보고, 원인 조사 결과 실적 파일 하나(1~8월 데이터 포함)를 업로드하면 시스템이 `sorted(기간들)[0]`(가장 이른 달)만 배치로 인식해 **전체 월의 실적을 그 한 달에 합산 저장**하던 것으로 확인됨(`app/services/aggregation.py`가 batch_id 하나로만 GROUP BY하고 행별 연/월을 보지 않음).
- 사용자 확인(2026-09-28):
  1. "실적 파일 하나에 여러 달 데이터가 섞여 있을 때, 시스템이 각 행의 실제 기간(연/월)을 기준으로 자동으로 달별 배치를 나눠 저장하도록 고치면 될까요?" → **예, 자동으로 월별 배치 분리(권장)**. 계획/손익계산서/매핑표 파일은 지금처럼 전체(=대표 배치 하나)에 공통 적용.
  2. 후속 요청(원문): "전체 업로드를 했을때 데이터 월이 겹치는 달이 있으면, 해당 월의 데이터를 덮어서 쓸지 물어보고, 덮어쓴다고 하면 엎어쓰고, 새로운 월은 입력이 되는걸로 하면 개선이 될까" → 겹치는(=이미 배치가 있는) 달만 덮어쓰기 여부를 확인하고, 겹치지 않는 새 달은 확인 없이 항상 저장한다.

## 배경/동기

`app/routers/uploads.py`는 실적 파일 여러 개를 업로드할 수 있게 만들어졌지만(F1 화면은 실적 파일 슬롯이 1개로 고정돼 있어 실제로는 파일 1개만 온다), "파일 1개 = 기간 1개"를 암묵적으로 가정했다 — `batch_periods`가 여러 개면 `period_warning`만 문자열로 얹어 사용자에게 알릴 뿐, 실제로는 `sorted(batch_periods)[0]`(가장 이른 기간) 하나만 배치로 만들고 **그 배치 안의 모든 행을 기간 구분 없이 합산**한다(`aggregation.py`의 `compute_aggregates_for_batch`가 `WHERE batch_id = ?`로만 묶고 `year`/`month`를 보지 않음). 사용자가 실제로 1~8월치를 한 파일에 담아 올리면서 이 가정이 깨졌고, "1월 배치"에 8개월치가 전부 합산된 값이 저장되는 실제 버그로 나타났다(반면 6월·7월은 이 업로드보다 훨씬 전에 올라간 소규모 테스트 데이터가 그대로 남아있어 화면에 옛날 값이 보였다).

## 범위

**구현**:
1. `app/routers/uploads.py`의 `/uploads` 핸들러 재구성:
   - 실적 파일의 정제 결과(`RefinedRow` 목록)를 각 행의 `(year, month)`로 그룹지어(`rows_by_period: dict[(int,int), list[RefinedRow]]`) 기간별로 나눈다.
   - 각 기간에 대해 `db.find_batch_id_by_period(year, month)`로 기존 배치 존재 여부를 확인해 `conflicting_periods`(이미 배치가 있음)와 `new_periods`(신규)로 나눈다.
   - `conflicting_periods`가 있고 아직 사용자 확인(`confirm_overwrite` 폼 필드)이 없으면, **아무것도 저장하지 않고** `{"requires_confirmation": true, "conflicting_periods": [...], "new_periods": [...]}`를 반환한다(같은 파일들을 다시 제출해야 하므로 프론트가 File 객체를 들고 있어야 함).
   - 확인이 왔거나(`confirm_overwrite=true/false`) 애초에 겹치는 기간이 없으면 커밋을 진행한다: `new_periods`는 항상 저장, `conflicting_periods`는 `confirm_overwrite=true`일 때만 기존 배치를 지우고 덮어쓰며 `false`면 그 기간은 건너뛴다(`skipped_periods`로 응답에 표시, 기존 데이터는 그대로 둔다).
   - 계획/손익계산서/매핑표 파일은 기간별로 나뉘지 않는 실적 외 파일이므로, 커밋된 기간 중 가장 이른 기간의 배치("대표 배치")에 그대로 연결한다(이 파일들이 조회되는 `sales_plan_record`/`team_pl_record`는 이미 `team+year+month`로 조회되고 재업로드 시 연도 단위로 지우고 다시 채우므로, 어느 배치에 달려 있든 계산 결과에는 영향이 없다 — batch_id는 계보 추적용).
   - 응답 스키마: 기존 단일 배치 업로드(대부분의 실사용 케이스 — 파일 하나에 기간 하나)와의 하위 호환을 위해, 커밋된 배치가 1개든 여러 개든 상위 필드(`batch_id`/`target_period`/`total_rows`/`unmapped_rows`/`calc_error_rows`/`aggregated_groups`/`anomaly_count`/`overwrote_existing_batch`)는 **대표 배치** 기준값을 그대로 채우고(기존 테스트·프론트·스모크 테스트가 이 필드들을 그대로 씀), 신규 `batches`(기간별 전체 목록)·`skipped_periods`·`requires_confirmation: false`를 추가한다.
2. 프론트 `app/upload/page.tsx`: 응답이 `requires_confirmation: true`면 겹치는 기간 목록을 보여주는 확인 다이얼로그(간단한 인라인 배너 + 확인/취소 버튼)를 띄우고, 확인 시 같은 파일들로 `confirm_overwrite=true`를 붙여 재요청, 취소 시 `confirm_overwrite=false`로 재요청(겹치는 달 스킵, 새 달만 저장)한다. 성공 응답의 `batches` 배열을 이용해 "N개 기간 처리됨(그중 M개 덮어씀)" 같은 요약을 보여준다.
3. `lib/api.ts`의 `uploadFiles` 타입에 `requires_confirmation`/`conflicting_periods`/`new_periods`/`batches`/`skipped_periods` 필드와 `confirm_overwrite` 파라미터를 추가한다.

**범위 밖**:
- 기간별로 개별 선택하는(체크박스) 세분화된 확인 UI는 만들지 않는다 — 겹치는 기간 전체에 대해 "덮어쓸지" 하나의 결정만 받는다(사용자 문구가 단수 결정으로 읽힘).
- 서버 쪽에 파싱 결과를 캐싱해 재업로드 없이 확인만으로 커밋하는 최적화는 하지 않는다 — 로컬 1인 도구라 파일을 다시 보내 재파싱하는 비용이 문제되지 않는다고 보고, 상태 관리 복잡도를 늘리지 않는다.

## 방법·완료 기준

- 1~8월 데이터가 섞인 실적 파일을 업로드하면, 기존에 배치가 없는 달(예: 2~5월)은 확인 없이 즉시 각각 별도 배치로 저장되고, 이미 배치가 있는 달(예: 6·7·8월)은 `requires_confirmation`으로 먼저 물어본 뒤 확인 시에만 덮어써진다.
- 각 기간별 `aggregated_result`가 그 기간 자신의 실적 행만으로 계산된다(다른 달과 합산되지 않음) — 이번 버그의 핵심 재현 시나리오.
- 백엔드 전체 pytest, 프론트 lint·build·vitest 통과.
