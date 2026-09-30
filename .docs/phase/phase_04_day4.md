# Day 4 작업 계획서 — 보고서 초안 자동 생성 (F7)

- 근거 문서: [.docs/05_MVP계획서.md](../05_MVP계획서.md) Day 4 절, [.docs/02_prd.md](../02_prd.md) F7·7장(ReportDraft/ReportItem)
- 관련 목업: [output/f7-report-draft.html](../../output/f7-report-draft.html)

## 배경/동기

F1~F6까지는 "데이터 업로드 → 정제 → 집계 → 이상징후 판정 → 화면 표시 → 임계치 조정"까지 담당자가 직접 화면을 보고 해석해야 하는 단계다. F7의 목적은 이 결과(F5의 이상징후 리스트)를 근거로 보고서 초안(그래프+코멘트)을 자동 생성해, 담당자가 매월 반복하던 "숫자 나열 및 문장화" 작업(과제기획서 기준 월 12시간 소요)을 줄이는 것이다.

## 범위

- 백엔드: `ReportDraft`/`ReportItem` 스키마, 이상징후 유형별 규칙 기반 코멘트 생성기, 보고서 초안 생성 API(`POST /reports`)·조회 API(`GET /reports/{id}`)
- 프론트엔드: 보고서 초안 화면(F7) — 배치 선택 → "초안 생성" → 이상징후별 코멘트 + 추이 차트 표시
- **범위 밖(Day 5로 이동)**: 코멘트 인라인 수정, 항목 삭제/제외, 배경 설명 입력(F8), 엑셀 다운로드(F9)

## 방법

1. `backend/app/db.py`에 `report_draft`(draft_id, batch_id, created_at, status), `report_item`(item_id, draft_id, flag_id nullable, auto_comment, user_comment nullable, chart_ref) 테이블 추가.
2. `backend/app/services/comments.py` — anomaly_flag 1건을 받아 PRD 예시("OO지사 OO제품군 매출 전월 대비 -18%, 계획 대비 82% 달성")와 같은 형식의 수치 기반 사실 서술 문장을 6개 metric_type별로 생성. "때문에/원인/인해" 등 원인 추정 어휘를 쓰지 않는다 — 테스트로 금지어 미포함을 검증한다.
3. `backend/app/services/reports.py` — `create_report_draft(db, batch_id)`: 해당 배치의 `anomaly_flag` 전체를 조회해 `report_item`을 1건씩 생성(코멘트 자동 생성, `chart_ref`에 team/product_group/metric_type을 담아 프론트가 기존 `GET /batches/{id}/trend` API로 차트를 그릴 수 있게 함). `get_report_draft(db, draft_id)`: draft+item 목록 반환.
4. `backend/app/routers/reports.py` — `POST /reports`(batch_id) / `GET /reports/{id}`.
5. 프론트엔드 `app/reports/page.tsx` — 배치 선택 → 초안 생성 버튼 → 이상징후별 카드(코멘트 + 해당 팀의 기존 추이 차트 재사용) 렌더링. `lib/api.ts`에 `createReportDraft`/`getReportDraft` 추가.
6. 테스트: 코멘트 생성기 단위 테스트(6개 유형 × 금지어 검증), API 통합 테스트(초안 생성 → 조회, 이상징후 0건 배치 처리), 프론트 vitest.

## 완료 기준

- F5의 이상징후 리스트 전체가 보고서 초안에 그래프+코멘트로 반영된다.
- 코멘트 문구가 수치 기반 사실 서술에 한정되고 원인 추정을 포함하지 않는다 (금지어 테스트로 검증).
- 백엔드 pytest, 프론트 vitest·lint·build 전체 통과.
