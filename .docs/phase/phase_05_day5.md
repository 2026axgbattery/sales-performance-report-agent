# Day 5 작업 계획서 — 검토·수정 및 결과 다운로드 (F8 + F9)

- 근거 문서: [.docs/05_MVP계획서.md](../05_MVP계획서.md) Day 5 절, [.docs/02_prd.md](../02_prd.md) F8·F9, [.docs/06_MVP_Todo리스트.md](../06_MVP_Todo리스트.md) Day 5 절
- 관련 목업: [output/f8-report-review.html](../../output/f8-report-review.html), [output/f9-download.html](../../output/f9-download.html)

## 배경/동기

F7까지는 보고서 초안이 100% 자동 생성 결과다. PRD는 이 초안이 오탐지(임계치는 넘었지만 실제로는 보고할 필요가 없는 항목)를 포함할 수 있고, 담당자가 아는 배경 사정(특이비용, 거래처 이슈 등)은 시스템이 알 수 없다는 점을 전제로, F8에서 사람이 검토·보완하게 한다. F9는 이렇게 완성된 결과를 기존 배포 관행(엑셀 첨부)에 바로 쓸 수 있는 형태로 내보내는 마지막 단계다.

## 범위

- 백엔드: `report_item`에 `is_excluded`(제외 토글), `background_note`(배경 설명) 컬럼 추가, 수정 저장 API(`PATCH /reports/{draft_id}/items/{item_id}`)
- 백엔드: 엑셀 다운로드 API 3종 — Overview(F4), 이상징후 리스트(F5), 검토 완료 보고서(F7, 제외 항목 제외)
- 프론트엔드: F8 검토 화면(코멘트 인라인 수정, 제외 토글, 배경 설명 입력) — 기존 F7 화면(`app/reports/page.tsx`)을 확장해 구현(별도 화면을 새로 만들지 않는다. 초안 생성 직후 바로 검토까지 이어지는 PRD 흐름과 자연스럽게 맞는다)
- 프론트엔드: F9 다운로드 버튼 3종(Overview·이상징후·보고서) — F8 확장 화면과 Overview/이상징후 화면에 배치
- **범위 밖**: 워드/PDF 등 엑셀 이외 포맷(PRD 미해결 질문 4번, 아직 우선순위 미확인), 수정 이력 관리(PRD가 명시적으로 MVP 범위 밖으로 규정)

## 방법

1. `backend/app/db.py` — `report_item`에 `is_excluded BOOLEAN DEFAULT FALSE`, `background_note VARCHAR` 컬럼 추가.
2. `backend/app/services/reports.py` — `update_report_item(db, draft_id, item_id, updates)` 추가(user_comment/background_note/is_excluded 부분 수정).
3. `backend/app/routers/reports.py` — `PATCH /reports/{draft_id}/items/{item_id}`.
4. `backend/app/services/export.py` — openpyxl로 Overview·이상징후·보고서 3종 워크북 생성. 보고서 export는 `is_excluded=True` 항목을 제외하고, `user_comment`가 있으면 그 값을, 없으면 `auto_comment`를 쓰며, `background_note`가 있으면 별도 컬럼에 추가.
5. `backend/app/routers/exports.py` — `GET /batches/{id}/export/overview`, `GET /batches/{id}/export/anomalies`, `GET /reports/{draft_id}/export` — `StreamingResponse` + `Content-Disposition: attachment`로 반환.
6. 프론트엔드 `app/reports/page.tsx` 확장 — 각 항목에 코멘트 수정 textarea, 배경 설명 입력, 제외 체크박스 추가(모두 blur/변경 시 `PATCH` 호출). 상단에 Overview/이상징후/보고서 다운로드 버튼 3개 추가(Overview·이상징후 화면에도 각각 버튼 배치).
7. 테스트: 백엔드 — PATCH 부분 수정, 제외 토글이 export에 반영되는지, export 응답이 유효한 xlsx(openpyxl로 재파싱해 셀 값 검증)인지. 프론트 — 새 api 함수 단위 테스트.

## 완료 기준

- F8에서 코멘트 수정·삭제(제외)·배경 설명 추가가 저장되고 재조회 시 반영된다.
- F9 다운로드 파일 3종이 실제로 열리는 xlsx이고, 제외한 항목이 보고서 export에서 빠진다.
- 백엔드 pytest, 프론트 vitest·lint·build 전체 통과.
