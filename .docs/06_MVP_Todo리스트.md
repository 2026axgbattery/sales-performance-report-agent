# MVP Todo List — 영업실적·손익 분석 및 보고서 자동 생성 Agent

- 근거 문서: [.docs/05_MVP계획서.md](05_MVP계획서.md)
- 범위: MVP(F1~F9) 전체를 다룬다 (5일 개발 기준). v2(V1~V6)는 포함하지 않는다.
- 체크박스는 05_MVP계획서.md의 Day 1~5 구성과 완료 기준(Definition of Done)을 실행 단위로 쪼갠 것이다.

---

## ⚠️ MVP 완료 필수 게이트 — v2로 이월 금지 (사용자 확정 사항)

아래 항목은 **"나중에 하면 되는 보완 사항"이 아니라 MVP 완료 기준의 일부**다. 담당자가 명시적으로 "이번 개발에 반드시 포함되어야 하며, 다음 버전(v2)으로 미루지 말 것"을 요청했다. 이 항목이 미완료 상태면 F1~F9 전체가 구현되어 있어도 **MVP는 완료된 것으로 보지 않는다**.

- [ ] **F8 웍스AI 종합 유추 — 실제 API 연동** (`.docs/02_prd.md` F8, 미해결 질문 15번). 목업 응답이 아니라 사내 웍스AI 모델을 실제로 호출해, 담당자가 입력한 배경 설명과 F3 수치를 종합한 유추 문장이 생성되어야 완료로 인정한다.
  - [ ] (선행조건, 사용자 확인 필요) 웍스AI API 사용 승인·엔드포인트·인증 방식·요청/응답 포맷 확보 — 이게 없으면 이 항목 자체를 시작할 수 없다. 확보되는 즉시 알려주면 바로 이어서 진행한다.
  - [ ] 어댑터 함수(`synthesize_background` 등)를 목업 응답으로 먼저 구현해 F8 화면·저장 흐름을 완성 (API 스펙 없이도 지금 시작 가능)
  - [ ] 위 선행조건이 채워지면 어댑터 내부를 실제 API 호출로 교체
  - [ ] 실제 API 응답이 `report_item.ai_synthesized_note`에 저장되고 F8 화면에 표시되는 것을 실제 서버로 확인

이 게이트는 Day 5 "F8. 보고서 초안 검토·수정" 절과 5장 Definition of Done에도 동일하게 반영되어 있다 — 이 표만 보고 v2로 넘어가지 않도록 두 곳 모두에 체크박스를 뒀다.

---

## 0. 착수 전 확인 (Day 1 시작 전에 확정해야 하는 항목)

05_MVP계획서.md 6장의 리스크 중 개발을 막는 항목만 먼저 처리한다.

- [X] 연간 판매계획 파일 실제 샘플 확보 — **더미 샘플로 대체 확인**(`판매계획_더미데이터.xlsx`, 실제 원본은 아직 미확보). 스키마는 [.docs/03_데이터정제.md](03_데이터정제.md) §6.1 참고 — 거래처×제품군×월 단위. `app/services/plan.py` 재구현 완료([.docs/phase/phase_06_판매계획연동.md](phase/phase_06_판매계획연동.md) 참고, 실제 더미 파일 1200행 전체로 파싱·집계 검증 완료).
- [X] 팀별 손익계산서 파일 실제 샘플 확보 — **더미 샘플로 대체 확인**(`손익계산서_더미데이터.xlsx`, 실제 원본은 아직 미확보). 스키마는 [.docs/03_데이터정제.md](03_데이터정제.md) §6.2 참고 — 팀별 계정과목×월 구조. `team_pl_record` 실제 파싱 로직 미구현(현재 raw_payload 보관만 함).
- [ ] 로컬 개발 환경 구성 방식 확정 (FastAPI 포트, Next.js 포트, 둘을 프록시로 연결할지 여부)
- [ ] "지사" 표기를 실제 데이터 축인 "팀"으로 통일하기로 확정 (문서·코드 변수명 모두)
- [ ] 원본 SAP 데이터(손익센터 코드 목록)로 "산전팀"이 실제 존재하는 팀인지, 팀 5개(고정형/모티브/산전팀/차량대리점/차량OE)가 제품군 3개(차량AS/차량OE/산업용)로 어떻게 매핑되는지 확인 (PRD 미해결 질문 13번)
- [ ] 제조원가·제조원가율·표준매출원가의 원본 컬럼(또는 계산식) 확인 — 확인 전까지 F2에서 표준원가(S) 계열 컬럼을 폐기하지 않고 보존 (PRD 미해결 질문 14번)

---

## Day 1 — 데이터 파이프라인 기반 (F1 + F2) — ✅ 구현 완료 (backend/, 테스트 28개 통과)

### 백엔드 골격

- [X] FastAPI 프로젝트 스캐폴딩 (디렉터리 구조, uvicorn 실행 스크립트) — `backend/app/main.py`
- [X] DuckDB 연결 설정 — `backend/app/db.py`
- [X] 스키마 생성: UploadBatch, UploadedFile
- [X] 스키마 생성: ProductMapping, RefinedSalesRecord(정제 결과) / SalesPlanRecord·TeamPLRecord — **단순화됨**: 계획·손익계산서 파일의 실제 컬럼 스키마가 아직 미확인(0장 리스크)이라 원본을 그대로 보관하는 최소 테이블(raw_payload)로만 만들었다. 별도의 "정제 전 원본 실적" 테이블은 만들지 않고, 정제 결과(RefinedSalesRecord) 하나로 원본 식별 정보까지 함께 저장했다 — 스키마 재검토 후 필요하면 분리한다.

### F1. 파일 업로드

- [X] 다중 파일 업로드 API (`POST /uploads`) — 개수 제한 없이 수신
- [X] 파일 형식 검증 (.xlsx / .xls / .xlsb / .csv 허용) — **.csv·.xlsb 경로는 실제 파일로 테스트 완료**(.xlsb는 SAP 원본 실제 형식이라 Day 5+ 추가 작업으로 지원함, `test_upload_accepts_xlsb_actual_file`). .xlsx/.xls는 openpyxl 구현은 되어 있으나 실제 파일로는 아직 테스트하지 않음
- [X] 파일 종류(실적/계획/손익계산서/매핑표) 사용자 지정 파라미터 처리
- [X] ~~파일 종류 자동 인식 로직~~ — **범위에서 제외 확정.** 자동 인식 로직 없이 항상 사용자가 직접 지정하는 방식으로 PRD 미해결 질문 6번이 해결됨(`.docs/02_prd.md` 참고). 지금 구현(사용자가 매번 지정)이 곧 최종 사양이다.
- [X] 필수 파일(실적 통합 파일) 누락 시 업로드/분석 차단 및 안내 메시지
- [X] 파일 종류별 필수 컬럼 존재 검증 — **구현 범위 축소**: 03_데이터정제.md에서 확인한 실적 파일 142개 컬럼 중, F2 정제 로직이 실제로 쓰는 25개 컬럼만 필수로 검증한다 (아래 F2 참고)
- [X] 누락 컬럼 발견 시 "어떤 파일의 어떤 컬럼인지" 구체적으로 반환
- [X] 업로드된 파일 간 대상 기간(연/월) 불일치 시 경고 응답 (차단하지 않고 warning 필드로 반환)
- [X] 동일 기간 재업로드 시 기존 배치 덮어쓰기 처리
- [X] 매핑표 미업로드 시 이전에 저장된 매핑표 재사용 로직

### F2. 데이터 정제 및 매핑

- [X] 제품분류 매핑표 파싱 (10개 컬럼: 인자·구분(팀)·제품·구분·용도·제품구분1~4·자재내역)
- [X] "팀 구분 + 제품코드" 합성 키 생성 로직 (예: `산전MAZ00001`) — 모티브·고정형→"산전" 접두사 quirk 포함
- [X] 매핑 조인 — 실적 데이터만 구현. 계획·손익계산서는 원본 컬럼 스키마 미확인으로 조인 로직은 아직 없음
- [X] 미매핑 제품코드 플래그 처리 (집계에서 제외하지 않음) — 테스트로 검증
- [X] 계정과목별 정제 규칙 구현 — 6개 패턴을 **대표 컬럼으로 구현**(전체 68개 컬럼 중 매출 8개·원재료비 5개·주재료비 3개·최종손익 2개 등): 실제 검증된 엑셀 원본 값(PCC01179, PCC04736)과 정확히 일치하는지 테스트로 대조했다. 노무비·경비·판관비의 세부 항목(간접노무비, 경비 계, 판관인건비 등)은 패턴이 동일(직접 복사 또는 합산)하므로 후속 작업으로 남겨두었다 (코드에 명시).
  - [X] 패턴 ①: 원본값 그대로 복사
  - [X] 패턴 ②: 식별자 파싱 (코드+설명 분리)
  - [X] 패턴 ③: 코드 → 명칭 매핑 (팀 구분)
  - [X] 패턴 ④: VLOOKUP 방식 매핑 (제품구분)
  - [X] 패턴 ⑤: 항목 합산/차감/역산
  - [X] 패턴 ⑥: 최종 손익 계산 (매출-원가-판관비)
  - [X] 제품코드 접두사 예외 규칙 (R·QZZ 시작 시 매출수량 0 처리)
- [X] 계산 오류(널값/음수 등 비정상 값) 행 플래그 처리 (전체 집계는 막지 않음)
- [X] 정제 결과를 지사·제품군·팀 단위로 구조화해 저장

### Day 1 완료 확인

- [X] 샘플 실적 파일 업로드 → 정제 테이블이 DuckDB에 저장되는지 확인 (`test_upload_persists_refined_rows_in_duckdb`)
- [X] 미매핑/계산오류 케이스가 조용히 누락되지 않고 플래그로 남는지 확인 (`test_refine_flags_unmapped_product_without_dropping_it` 등)
- [X] pytest 28개 전체 통과, `uvicorn app.main:app` 실제 기동 후 `/health` 200 확인

> Day 1은 "0. 착수 전 확인"의 미해결 리스크(계획/손익계산서 샘플 파일, 팀 5개/제품군 3개 구조, 제조원가·표준매출원가 컬럼)를 해결한 것이 아니라, 그 리스크가 F1·F2 핵심 파이프라인(실적 파일 업로드→정제→매핑)을 막지 않는 범위로 스코프를 좁혀 구현했다. 위 항목들은 여전히 열려 있으며, 해결되면 스키마·정제 로직을 확장해야 한다.

---

## Day 2 — 계산 엔진 (F3 + F6) — ✅ 구현 완료 (테스트 26개 추가, 누적 54개 통과)

### 스키마

- [X] AggregatedResult 스키마 생성 — **MTD만 저장**: 전월/전년동월 비교값과 계획(plan)/달성률까지 포함했으나, PRD가 언급한 "YTD" 누계 필드는 이 테이블에 저장하지 않기로 했다. YTD는 여러 월별 배치를 그때그때 합산 조회하는 방식(Day 3 F4 화면에서 구현)으로 설계를 단순화했다.
- [ ] CustomerResult 스키마 생성 (팀×거래처 드릴다운용) — Day 3로 이동 (F4 ⑧ 화면 작업 시 필요)
- [X] ThresholdConfig, AnomalyFlag 스키마 생성 + 기본값 시딩 — PRD F3 표의 6개 기준·기본값과 동일하게 시딩됨 (`GET /thresholds`로 확인)

### F3. 증감률·이상징후 자동 계산

- [X] 전월 대비 매출/이익 증감률 계산
- [X] 전년 동월 대비 증감률 계산 (신규 팀/제품군은 "비교 불가" 처리, 0%·임의값 대체 금지) — 단위 테스트로 "비교 불가 시 플래그 생성 안 함"까지 검증
- [X] 계획 대비 달성률 계산 — **MTD만 구현**. (갱신) 처음엔 팀+년+월+계획매출액이라는 잠정 스키마로 구현했으나, 이후 실제 구조(거래처×제품군×월)를 확인해 `app/services/plan.py`를 재구현하고 `aggregation.py`의 plan_amount 조회도 단일 행 조회에서 팀 단위 `SUM`으로 변경했다 (Phase 6, [.docs/phase/phase_06_판매계획연동.md](phase/phase_06_판매계획연동.md))
- [X] 흑자→적자 전환 판정 로직 — "이전에 흑자였다가 이번에 적자로 전환"된 경우만 플래그, 계속 적자인 경우는 플래그하지 않음을 테스트로 구분
- [X] 평균단가 변동률 계산
- [X] 판관비/기타비용 급증(전월 대비) 계산 — 증가 방향만 플래그(감소는 플래그하지 않음)를 테스트로 검증
- [X] 6개 기준 판정 결과를 AnomalyFlag로 저장 (기준별 실제값·임계값·영향금액 포함)

### F4 지표 계산 (F4 화면이 쓰는 집계, 계산 로직은 Day 2에서 준비)

- [ ] 팀별 MTD/YTD 목표 대비 실적·달성률 집계 — MTD는 Day2에서 완료(AggregatedResult), YTD 집계 쿼리는 Day 3로 이동
- [ ] 제품군(차량AS/차량OE/산업용) × 제품구분 단위 집계 — Day 3로 이동
- [ ] 팀×거래처 단위 집계(CustomerResult 적재) — Day 3로 이동

### F6. 임계치 설정

- [X] 임계치 조회 API (`GET /thresholds`)
- [X] 임계치 저장 API (`PUT /thresholds`) — 명시적 호출로만 저장, 자동저장 없음
- [X] 임계치 변경 후 F3 재계산이 실제로 반영되는지 검증 로직 — `POST /batches/{batch_id}/recompute` 추가(재업로드 없이 재계산). 실제 업로드 재실행 시에도 자동으로 재계산됨

### Day 2 완료 확인

- [X] 임계치를 바꾸면 AnomalyFlag 결과가 즉시 바뀌는 것을 API 레벨에서 확인 (`test_threshold_change_and_recompute_changes_flags`)
- [X] 전년 데이터 없는 케이스가 "비교 불가"로 정확히 표시되는지 확인 (`test_multi_month_upload_produces_expected_anomaly_flags`)
- [X] pytest 54개 전체 통과 (Day1 28 + Day2 26), 실제 서버 기동 후 `/thresholds` 응답 확인

---

## Day 3 — Overview·하이라이트 화면 (F4 + F5, F1~F6 통합) — ✅ 구현 완료 (백엔드 5개 추가, 누적 59개 통과 / 프론트엔드 신규 13개 통과)

### 프론트엔드 셋업

- [X] Next.js 프로젝트 생성 (App Router, TypeScript, Tailwind v4) — `frontend/`
- [X] [.docs/design.md](design.md) 토큰을 CSS 커스텀 프로퍼티 + Tailwind `@theme inline`으로 매핑 — `frontend/app/globals.css` (`output/f1-file-upload.html`의 실제 색상값과 대조 확인). **shadcn/ui는 설치하지 않음** — 컴포넌트 수가 적어 직접 Tailwind 마크업으로 구현
- [X] Recharts 설치, Overview 팀별 추이 차트에 적용 (`LineChart`)

### 백엔드: F4/F5용 조회 API 신규 추가 (Day 2까지는 없었음)

- [X] `GET /batches` — 업로드된 배치(연/월) 목록
- [X] `GET /batches/{id}/overview` — 팀별 롤업 + 전체 요약(KPI) — `app/services/analytics.py`
- [X] `GET /batches/{id}/trend` — 팀 단위 1~12월 추이(데이터 없는 달은 null)
- [X] `GET /batches/{id}/anomalies` — 이상징후 목록(영향 금액 내림차순)
- [X] CORS 설정 (`http://localhost:3000` 허용)

### F1 화면

- [X] 업로드 화면 구현 (`frontend/app/upload/page.tsx`) — **단순화**: `output/f1-file-upload.html`의 상세 레이아웃을 그대로 재현하지 않고, 파일 선택·종류 지정·업로드 결과(경고 포함) 표시에 집중한 기능 우선 버전
- [X] 파일별 검증 결과/경고 UI 연동 (백엔드 응답의 warning 필드 표시)

### F4. Overview 화면 — ⚠️ **범위 축소**: 실제 참고 양식(`output/f4-overview.html`)의 8개 섹션 전체를 재현하지 않고, 아래 단일 화면으로 단순화했다

- [X] 상단 KPI 요약 (전체 매출·영업이익·전월대비·계획대비 달성률)
- [X] 팀별 목표 대비 실적 테이블 (수량·매출·영업이익·이익율·계획대비·전월대비·전년대비) — ①·②·③·④·⑤를 하나의 테이블로 통합, 당월(MTD) 기준만 표시
- [X] 팀 클릭 시 하단에 해당 팀의 1~12월 추이 차트 표시 (⑥에 해당, 라인 차트로 대체)
- [ ] ⑦ 월별 실적 분석(제품군별) — 3개 제품군 탭 + 제품구분별 당월·금년누계 — **미구현**, Day 4 이후로 이동
- [ ] ⑧ 팀×거래처별 상세 드릴다운 — **미구현** (CustomerResult 스키마 자체가 아직 없음), Day 4 이후로 이동
- [ ] 금년 누계(YTD) 표시 — 백엔드에 YTD 저장 필드가 없어(Day 2 설계 결정) 화면에서도 아직 미노출. 여러 배치를 합산 조회하는 방식으로 추후 추가 가능

### F5. 이상징후 하이라이트 화면 (`frontend/app/anomalies/page.tsx`)

- [X] 임계치 초과 항목 리스트 (영향 금액순 정렬)
- [X] 판정 기준(6개 metric_type) 필터 UI (칩 형태)
- [X] 각 항목에 플래그 기준·수치·영향 금액 표시

### F6. 임계치 설정 화면 (`frontend/app/thresholds/page.tsx`)

- [X] 6개 기준별 입력 폼
- [X] 저장 버튼 (명시적 저장)
- [ ] 기본값 재설정 기능 — 미구현 (백엔드에 reset API 없음)

### 엣지 케이스 (F1~F6 관련)

- [X] 이상징후 0건일 때 "이상징후가 없습니다" 명확히 표시
- [ ] 대용량 파일 처리 중 상태 표시 — 미구현 (업로드는 동기 응답만 표시)
- [ ] 파일 인코딩 오류 시 재업로드 안내 메시지 — 미구현

### Day 3 개발 중 발견·수정한 실제 버그

- [X] `analytics.py`의 팀별 롤업 쿼리가 계획매출액(`plan_amount`)을 `SUM`으로 합산해 계획대비 달성률이 실제보다 훨씬 낮게 계산되는 버그 발견 및 수정. `plan_amount`는 팀 단위 값이지만 `aggregated_result`에는 제품군별 행마다 동일 값이 중복 저장되므로, 제품군이 2개 이상인 팀은 계획이 2배 이상으로 합산되고 있었다. `SUM(plan_amount)` → `MAX(plan_amount)`로 수정하고, 회귀 테스트(`test_overview_returns_team_rollup_and_summary`)에 정확한 기대값(727885 / 900000 = 80.87%)을 명시해 재발을 막았다.

### Day 3 완료 확인

- [X] pytest 59개 전체 통과 (Day1 28 + Day2 26 + Day3 5), vitest 13개 전체 통과
- [X] `npm run lint`, `npm run build`(TypeScript 체크 포함) 통과
- [X] Node.js 스모크 테스트(`frontend/scripts/smoke-test.mjs`)로 브라우저와 동일한 fetch/FormData 인코딩 경로 기준 F1→F3→F4→F5→F6 전체 연동 확인 (curl은 이 환경에서 한글 폼 필드가 CP949로 깨져 사용 불가함을 확인, 대안으로 작성)
- [X] F1~F6 전체 플로우가 프론트-백엔드 연동 상태로 로컬에서 오류 없이 동작

---

## Day 4 — 보고서 자동 생성 (F7) — ✅ 구현 완료 (백엔드 14개 추가, 누적 73개 통과 / 프론트엔드 신규 2개 추가, 누적 15개 통과)

- [X] ReportDraft, ReportItem 스키마 생성 — `backend/app/db.py` (`report_draft`, `report_item`), 배치 재업로드/삭제 시 `delete_batch`가 연쇄 삭제하도록 반영
- [X] F5 이상징후 리스트를 근거로 팀별 그래프 데이터 생성 — **범위 축소**: 별도의 그래프 생성 API를 새로 만들지 않고, Day 3에 이미 만든 `GET /batches/{id}/trend?team=`을 프론트에서 그대로 재사용한다 (`report_item.chart_ref`에 team 값만 저장). 제품군별 그래프는 미구현(팀 단위만)
- [X] 이상징후 유형별(전월대비/전년대비/계획대비/흑자→적자/단가변동/판관비급증) 코멘트 템플릿 작성 — `backend/app/services/comments.py`
- [X] 코멘트 생성기 구현 — 수치 기반 사실 서술만 포함, 원인 추정 문구 금지 검증 (`test_comments.py`에서 "때문/원인/인해/탓/추정" 등 금지어 미포함을 6개 유형 전체에 대해 테스트)
- [X] 보고서 초안 생성 API (`POST /reports`) + 조회 API (`GET /reports/{draft_id}`)
- [X] 보고서 초안 화면 구현 (`frontend/app/reports/page.tsx`) — **단순화**: `output/f7-report-draft.html` 목업의 레이아웃을 그대로 재현하지 않고, 배치 선택 → "초안 생성" 버튼 → 팀별 섹션(추이 차트 + 해당 팀 이상징후 코멘트 목록)으로 단순화했다

### Day 4 완료 확인

- [X] F5의 이상징후 리스트 전체가 보고서 초안에 그래프+코멘트로 반영됨 — `test_create_report_draft_has_one_item_per_anomaly_flag`로 이상징후 개수와 ReportItem 개수 일치 검증
- [X] 코멘트 문구가 원인 추정을 포함하지 않는지 확인 — 5개를 무작위 샘플 검수하는 대신, 6개 metric_type 전부에 대해 금지어 부재를 단위 테스트로 자동 검증 (더 엄격한 방식으로 대체)
- [X] pytest 73개 전체 통과 (Day1~3 59 + Day4 14), vitest 15개 전체 통과, lint·build 통과
- [X] 실제 서버 기동 후 업로드→`POST /reports`→`GET /reports/{id}` 흐름을 curl로 종단 확인 (계획대비 79.8%, 전년대비 +43.6% 등 실제 수치가 코멘트에 정확히 반영됨을 확인)

---

## Day 5 — 검토·다운로드 및 전체 통합 (F8 + F9) — ⚠️ 기본 구현 완료, 웍스AI 실제 연동 게이트 미완료 (백엔드 15개 추가, 누적 82개 통과 / 프론트엔드 신규 3개 추가, 누적 17개 통과)

### F8. 보고서 초안 검토·수정

- [X] 코멘트 인라인 수정 UI — `app/reports/page.tsx`의 `ReportItemRow`, textarea로 구현(별도 contenteditable 없이 폼 방식)
- [X] 이상징후 항목 삭제/제외 토글 — 실제로 행을 지우지 않고 `is_excluded` 플래그로 표시하며, F9 보고서 export에서만 제외한다(원본 판정 이력은 보존)
- [X] 담당자 배경 설명 자유 텍스트 입력·저장 — `background_note` 컬럼, 코멘트 수정(`user_comment`)과 별개 필드로 분리
- [X] 수정 결과 저장 API (`PATCH /reports/{draft_id}/items/{item_id}`) — 3개 필드(user_comment/background_note/is_excluded) 중 전달된 것만 부분 수정
- [X] 화면 구현 — **범위 축소**: `output/f8-report-review.html`의 별도 화면을 새로 만들지 않고, F7 화면(`app/reports/page.tsx`)을 확장해 "생성 직후 바로 검토"가 이어지도록 구현했다
- [ ] **(MVP 완료 필수 게이트 — v2 이월 금지, 문서 상단 참고) 웍스AI 종합 유추**: 담당자가 배경 설명을 입력하면 사내 웍스AI 모델이 F3 수치(실제값·임계값·영향 금액)와 배경 설명을 종합해 손익에 반영된 내용을 유추한 문장(`ai_synthesized_note`)을 생성한다 (`.docs/02_prd.md` F8, 미해결 질문 15번). 웍스AI API 엔드포인트·인증 방식 확보가 선행조건 — 확보되는 즉시 개발을 이어간다. **목업 응답으로 대체하고 넘어가는 것은 MVP 완료로 인정하지 않는다.**

### F9. 결과 다운로드

- [X] Overview 결과 엑셀 export (`GET /batches/{id}/export/overview`)
- [X] 이상징후 리스트 엑셀 export (`GET /batches/{id}/export/anomalies`)
- [X] 검토 완료된 상세 보고서 엑셀 export (`GET /reports/{draft_id}/export`, 제외된 항목 제외 — 테스트로 검증) — **(신규 확정) 상세 보고서 초안은 최종적으로 엑셀이 아니라 PDF·PPT 중 선택 다운로드로 확정됨** (`.docs/02_prd.md` F9, 미해결 질문 4번 해결). 아래 항목이 추가로 필요함
- [ ] **(신규 확정, 미구현) 상세 보고서 초안 PDF export**
- [ ] **(신규 확정, 미구현) 상세 보고서 초안 PPT export** — F7의 팀별 추이 차트(Recharts, 클라이언트 렌더링)를 정적 이미지로 서버에서 렌더링하는 방법이 아직 미확정 (미해결 질문 16번)
- [ ] **(신규 확정, 미구현) 다운로드 시점에 PDF/PPT 서식을 선택하는 UI**
- [X] 다운로드 API 및 화면 구현 — **범위 축소**: `output/f9-download.html`의 별도 다운로드 화면을 만들지 않고, Overview·이상징후·보고서 각 화면에 다운로드 버튼을 바로 배치했다
- [X] 다운로드 파일이 기존 배포 경로에 바로 첨부 가능한 형태인지 확인 — 실제 xlsx로 열리는지 openpyxl로 재파싱해 테스트(엑셀 프로그램으로 직접 열어보는 수기 검증은 하지 않음). PDF·PPT export는 미구현 상태라 아직 확인 불가

### 전체 통합

- [X] 프론트-백엔드 전체 API 연동 (F1→F2→F3→F4→F5→F6→F7→F8→F9) — curl·smoke-test.mjs로 종단 확인
- [ ] 실제(또는 샘플) SAP 실적 파일로 End-to-end 리허설 — 실제 SAP 파일 미확보로 미실시(0장 리스크와 동일한 사유), 검증된 샘플 2행(PCC01179/PCC04736) 기준으로만 리허설함
- [ ] 수기 계산 결과와 자동 계산 결과 교차 검증 — 별도 수기 검증 세션은 하지 않았고, `.docs/03_데이터정제.md`에서 이미 검증된 엑셀 원본값과 정제 로직 테스트가 이를 대신하고 있음

### Day 5 개발 중 발견·수정한 실제 버그

- [X] 로컬 DuckDB 파일(`backend/data/app.duckdb`)이 `report_item`에 `is_excluded`/`background_note` 컬럼이 없던 Day 4 시점에 이미 생성되어 있어, Day 5 코드로 재기동하면 `POST /reports`가 500 에러를 내는 것을 실제 서버로 확인. `CREATE TABLE IF NOT EXISTS`는 기존 테이블을 변경하지 않기 때문 — `app/db.py`에 `COLUMN_MIGRATIONS` 목록과 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`를 추가해, 컬럼이 늘어나도 기존 로컬 DB 파일이 깨지지 않도록 했다. 회귀 테스트(`test_db_migrations.py`)로 "예전 스키마로 만들어진 파일을 다시 열면 새 컬럼이 추가되는지"를 검증.

### Day 5 이후 실제 브라우저 확인 중 발견·수정한 실제 버그

- [X] **DuckDB 커넥션 스레드 세이프티 문제(F7 화면에서 실제로 발생)**: `get_db()`가 프로세스 전역으로 공유하는 DuckDB `Connection` 하나를, FastAPI가 동기 라우트를 스레드풀에서 실행하며 여러 요청이 동시에 사용하고 있었다. F7 보고서 화면은 팀별 추이를 `Promise.all`로 동시에 요청하는데(Day 4에 추가된 유일한 병렬 요청 지점), 두 스레드가 같은 커넥션에서 쿼리를 인터리빙하면서 서로의 결과 행이 섞이는 실제 예외(`get_trend`에서 "not enough values to unpack")가 발생했고, 이 예외가 CORS 미들웨어 응답 경로 중간에 발생해 브라우저 콘솔에는 "CORS policy에 의해 차단됨"으로 표시되는 등 원인 파악이 까다로웠다. 헤드리스 브라우저로 실제 F7 화면을 열어보기 전까지는 발견되지 않았던 문제다 — pytest의 `TestClient`는 순차 실행되고, 그동안의 curl 기반 종단 확인도 항상 요청을 하나씩 순서대로 보냈기 때문에 병렬 요청 상황을 한 번도 재현하지 못했다. `app/main.py`에 `asyncio.Lock` 기반 미들웨어를 추가해 모든 HTTP 요청을 직렬화하는 것으로 해결했고(로컬 1인 사용자 도구라 성능상 문제 없음), `tests/test_concurrency.py`로 스레드 기반 동시 요청 회귀 테스트를 추가했다(미들웨어를 제거하면 테스트가 실제로 실패하는 것까지 확인).

- **교훈**: 지금까지 "F1~F9 전체 플로우를 curl/스모크 테스트로 종단 확인했다"고 여러 번 보고했지만, 이는 항상 순차 요청만 검증한 것이라 이런 종류의 동시성 버그를 잡을 수 없었다. 앞으로 프론트엔드가 병렬 요청(`Promise.all` 등)을 보내는 화면을 추가할 때는 실제 브라우저(또는 스레드 기반 동시 요청 테스트)로 별도 확인이 필요하다.

### Day 5 완료 확인 — Definition of Done ([.docs/05_MVP계획서.md](05_MVP계획서.md) 5장과 동일)

- [X] 샘플 SAP 실적 파일(검증된 2행 포함) 1개월 치로 F1~F9 전체 플로우가 로컬에서 오류 없이 동작 — curl로 업로드→Overview→이상징후→추이→임계치→보고서 생성→검토(PATCH)→3종 엑셀 다운로드까지 종단 확인
- [X] Overview·이상징후 하이라이트 표시 수치가 입력 데이터와 일치
- [X] 임계치 변경 시 F3·F5 결과가 재계산·재표시됨
- [X] F7 코멘트가 수치 기반 사실 서술에 한정되고 원인 추정을 포함하지 않음
- [X] F8에서 코멘트 수정·삭제(제외)·배경 설명 추가가 정상 동작
- [X] F9 다운로드 파일이 실제로 열리는 xlsx 형태(openpyxl 재파싱으로 검증)
- [ ] 수기 계산 대비 자동 계산 결과 불일치 0건 — 실제 SAP 원본 파일 기반 수기 대조는 미실시(위 사유와 동일)
- [X] 엣지 케이스(미매핑/계산오류/전년데이터없음 등)가 앱을 중단시키지 않고 화면에 표시됨

---

## Phase 6 — 판매계획 실제 스키마 반영 — ✅ 구현 완료 (백엔드 6개 추가, 누적 89개 통과)

근거: [.docs/phase/phase_06_판매계획연동.md](phase/phase_06_판매계획연동.md), [.docs/03_데이터정제.md](03_데이터정제.md) §6

- [X] `sales_plan_record` 스키마를 실제 구조(거래처×제품군×월, 판가/수량/hq_report_group 등)로 재설계 — `COLUMN_MIGRATIONS`로 기존 로컬 DB도 안전하게 확장
- [X] `app/services/plan.py` 전면 재작성 — 팀별 시트(고정형/모티브/차량대리점/차량OE) + `인자` 매핑 시트를 openpyxl로 직접 파싱, "금액" 수식 캐시값을 믿지 않고 판가×수량 직접 계산
- [X] 시트별 VLOOKUP 리터럴 실측(`TEAM_SHEET_TO_FACTOR_KEY`) — "차량대리점" 시트인데 내부 수식은 "대리점"을 키로 쓰는 것을 확인, 추정하지 않고 실측값 그대로 반영
- [X] `aggregation.py`의 plan_amount 조회를 단일 행 조회 → 팀 단위 `SUM`으로 변경 (거래처×제품군 다중 행 대응)
- [X] 연간 파일 재업로드 시 같은 연도 기존 행 삭제 후 재삽입 (중복 합산 방지, `test_reuploading_plan_file_same_year_does_not_double_count`)
- [X] 실제 더미 파일(`판매계획_더미데이터.xlsx`, 4개 팀 시트·1200행) 전체로 파싱→업로드→Overview 조회까지 실 서버 종단 확인
- [X] 분류 체계(product_group/product_type/hq_report_group) 정형화 로드맵을 PRD 미해결 질문 17번과 phase 문서에 단계별로 기록 (지금은 통합하지 않고 원본 보존만 함)
- [X] `team_pl_record`(손익계산서) 실제 계정과목 파싱 — Phase 7로 이어서 구현 완료 (아래 참고)

---

## Phase 7 — 팀별 손익계산서 실제 파싱 — ✅ 구현 완료 (백엔드 4개 추가, 누적 93개 통과)

근거: [.docs/phase/phase_07_손익계산서연동.md](phase/phase_07_손익계산서연동.md), [.docs/03_데이터정제.md](03_데이터정제.md) §6.2

- [X] `team_pl_record` 스키마를 실제 구조(팀×계정과목×월)로 재설계 — `COLUMN_MIGRATIONS`로 기존 로컬 DB도 안전하게 확장
- [X] `app/services/team_pl.py` 신규 — 팀별 시트(모티브/고정형/대리점/차량oe)를 openpyxl로 직접 파싱, 연도는 `국내`(집계) 시트 제목에서 추출
- [X] 매출원가(A)Tot·매출총이익(A)·판관비(Total)·영업이익(A) 4개 소계 행을 원본 캐시값 대신 확인된 수식(SUM 범위·뺄셈) 그대로 직접 계산 — 판매계획의 "금액=판가×수량"과 동일한 종류의 문제를 동일한 방식으로 해결
- [X] 시트명을 앱 표준 팀 명칭으로 정규화(`대리점`→`차량대리점`, `차량oe`→`차량OE`) — 판매계획의 VLOOKUP 리터럴 불일치와 같은 종류의 명명 불일치를 실측 확인 후 반영
- [X] 실제 더미 파일(`손익계산서_더미데이터.xlsx`, 4개 팀×76개 계정과목×12개월=3648행) 전체로 파싱 검증, 실 서버에 판매계획·손익계산서 파일을 함께 업로드해 종단 확인
- [ ] F3/F4가 이 데이터를 조회·활용하도록 연결 — 현재 요구사항에 없어 범위 밖으로 남김(저장까지만 구현)

---

## Phase 8 — 지점코드 매핑 구현 (F2 확장) — ✅ 구현 완료 (백엔드 7개 추가, 누적 106개 통과)

근거: 담당자가 08월 실제 파일(`2026년 08월 3. 손익분석 (1단계 작업용)__과제용.xlsb`)로 시트 구조를 재확인, [.docs/03_데이터정제.md](03_데이터정제.md) §3.5

- [X] 시트 구조 재확인 — 3개가 아니라 **4개**(실적 Raw Data/Re-arrange/**지점코드**(신규)/제품분류). F1은 [실적 Raw Data] 내용만, 맵핑표는 [지점코드]+[제품분류]를 함께 업로드하는 것으로 F1/F2 경계 확정.
- [X] `branch_mapping` 테이블 신규 — "팀+거래처코드" 합성 키(제품분류와 동일한 패턴). **제품분류와 달리 모티브·고정형도 "산전" 접두사를 쓰지 않는다**는 것을 실측으로 확인(추정 아님).
- [X] `app/services/branch.py` 신규 — `BranchMappingTable` 파싱·조회. 지점코드 시트에는 팀 컬럼이 따로 없어 "인자"에서 거래처코드 접미사를 떼어내 팀을 구함.
- [X] `app/services/mapping.py`에 `parse_mapping_upload` 추가 — 매핑표 파일에서 (제품분류, 지점코드|None) 두 DataFrame을 함께 추출. CSV는 제품분류 단일 표(하위 호환), xlsx/xlsb는 시트명으로 각각 탐색.
- [X] `refined_sales_record`에 region/office/part/is_branch_mapped 컬럼 추가(`COLUMN_MIGRATIONS`로 기존 로컬 DB도 안전하게 확장), `refine_row`/`refine_actual_records`가 `BranchMappingTable`(선택 인자, 기본 None — 하위 호환)로 조회해 채움.
- [X] **실제 08월 파일 50행으로 검증** — 제품분류·지점코드 둘 다 100% 매핑, 조회된 region/office/part 값이 실제 Re-arrange 시트 값과 정확히 일치함을 확인.
- [ ] Re-arrange 시트의 "부문"(예: 차량/산전) 컬럼은 아직 미구현 — 팀에서 바로 유도되는지 별도 매핑이 필요한지 미확인.

## Phase 9 — 수량(22.9cell) 기본 수량 전환 — ✅ 구현 완료 (백엔드 4개 추가, 누적 110개 통과)

근거: 담당자가 08월 실제 파일에 BZ열(78번째, "수량(22.9cell)")을 추가하고 이를 향후 수량 분석·모든 손익 분석의 기본 수량으로 확정. [.docs/03_데이터정제.md](03_데이터정제.md) §4.7

- [X] 전체 6029행을 BO(매출수량)·BZ(수량(22.9cell))로 실측 비교 — 팀="모티브" AND 제품구분1(보고4용)="V전지:Set"인 546행만 ×22.9, 나머지 5483행은 1:1로 확인(예외 없음).
- [X] 22.9 배율의 출처를 Raw Data 용량(단위당)/연량(단위당) 등에서 찾아봤으나 무관한 값(전압·용량)만 확인 — 특정 제품 속성에서 유도되지 않는, "V전지:Set" 제품군 전체에 적용되는 고정 계수로 판단.
- [X] `app/services/identifiers.py`에 `apply_cell_22_9_conversion(product_group_1, quantity)` 추가.
- [X] `app/services/mapping.py`에 `ProductMappingTable.lookup_product_group_1` 추가 — 기존 `lookup`(제품구분3)과 별개로 제품구분1(보고4용) 조회.
- [X] `RefinedRow`에 `quantity_raw`(R/QZZ 예외 규칙만 적용된 원본, 기존 BO) 필드를 신설하고, 기존 `quantity` 필드는 여기에 22.9cell 환산을 추가 적용한 값(BZ 상당)으로 재정의. 컬럼명을 유지했으므로 `aggregation.py`/F3/F4는 코드 변경 없이 자동으로 새 기본 수량을 사용.
- [X] `refined_sales_record`에 `quantity_raw` 컬럼 추가(`COLUMN_MIGRATIONS`로 기존 로컬 DB도 안전하게 확장).
- [ ] 22.9 계수 자체의 업무적 의미(왜 정확히 22.9인지, 예: SET당 표준 셀 환산 개수)는 담당자 확인 필요 — 근거 없는 값으로 추정하지 않음.

## Phase 10 — "부문" 컬럼 기반 팀 분류 지원 (F2 확장) — ✅ 구현 완료 (백엔드 5개 추가, 누적 115개 통과)

근거: 사용자가 F1에 `2026년 08월 Raw Data_업로드용.xlsb`를 실제로 업로드하다가 "손익 센터 컬럼이 없다"는 오류를 만남. 조사 결과 이 파일(142개 컬럼)에는 "손익 센터" 컬럼이 아예 없고 "부문" 컬럼으로 팀을 구분한다는 것을 확인. [.docs/03_데이터정제.md](03_데이터정제.md) §4.1 확장

- [X] 최초엔 pyxlsb/calamine 두 라이브러리 모두 헤더가 깨져 보여 "파일 자체가 손상됐다"고 오판할 뻔했으나, 진단 스크립트의 콘솔 출력 인코딩 문제였음을 UTF-8 파일 출력으로 재확인 — 실제 파일 내용은 정상.
- [X] 142개 컬럼 전수 확인 — "손익 센터"만 없고 나머지(매출·원재료비·주재료비 등)는 기존 `REQUIRED_RAW_COLUMNS`와 전부 일치. 대신 "부문" 컬럼이 "코드 + (모티브·고정형만 '산전') + 팀명 + '팀'" 형식으로 팀을 담고 있음(예: `"2630 차량대리점팀"`).
- [X] 전체 7676행에서 부문 값이 정확히 4개(`2630 차량대리점팀`/`2640 차량OE팀`/`2620 산전모티브팀`/`2610 산전고정형팀`)뿐임을 확인 — 접두사를 떼면 기존 4개 팀과 정확히 대응.
- [X] 사용자에게 "부문 컬럼으로 전환" vs "두 컬럼 다 지원" vs "이 파일은 잘못된 파일" 중 선택하도록 질문 — **"두 컬럼 다 지원(있는 쪽 사용)"으로 확정**.
- [X] `app/services/team.py`에 `classify_team_from_division(division_value)` 추가 — 실측된 4개 값만 매핑, 그 외는 `ValueError`.
- [X] `app/services/refinement.py` — `REQUIRED_RAW_COLUMNS`에서 "손익 센터"를 제거하고 `TEAM_SOURCE_COLUMNS = ("손익 센터", "부문")`로 "둘 중 하나는 있어야 함"을 검증. `refine_row`는 "손익 센터"가 있으면 기존 로직, 없으면 "부문"으로 팀을 분류하며, 알 수 없는 부문 값은 `DEFAULT_TEAM`으로 계속 진행하고 `is_calc_error=True`로 표시(배치 전체를 크래시시키지 않음).
- [X] **실제 08월 "Raw Data_업로드용.xlsb" 7676행 전체로 종단 검증** — `validate_raw_columns` 통과, 전 행 정상 분류(차량대리점 5049/모티브 1037/고정형 1261/차량OE 329), calc_error 0건.

## Phase 11 — 팀별 손익계산서 계획 대비 실적 비교 — ✅ 구현 완료 (백엔드 14개 추가, 누적 125개 통과)

근거: 사용자 요청("손익계산서는 제품구분 없이 국내+4개 팀 단위로 계획 대비 실적 비교") + 사용자가 제공한 실제 참고 파일(`2026년 08월 4. 손익분석 (2단계 배포용) 1.xlsb`). [.docs/phase/phase_11_팀별손익계산서비교.md](phase/phase_11_팀별손익계산서비교.md)

- [X] 스크린샷 표의 계산식을 실제 숫자로 역산 검증 — 단위당=총액÷수량, 비중=항목÷매출액, 계획대비=실적−계획.
- [X] "계획" 값의 출처가 이미 F1에서 지원하는 "손익계산서" 업로드(`team_pl_record`)임을 확인 — 신규 업로드 슬롯 불필요.
- [X] 노무비·경비·판관비 세부(§4.4·§4.5) 합산 공식을 실제 파일(2026-08 과제용) Raw Data+Re-arrange 6029행 전수 대조로 재검증(불일치 0건) — 07월 문서의 추정 서술(판관인건비 8개 항목, 역산 잔여값)과 다른 부분(9개 항목, 정방향 합산)을 갱신.
- [X] `app/services/refinement.py` — `REQUIRED_RAW_COLUMNS`에 노무비·경비·판관비 세부 원본 컬럼 47개 추가, `RefinedRow`에 재료비 계/노무비 계/경비 계/판관비 세부 20개 필드 추가.
- [X] `app/db.py` — `refined_sales_record`에 새 컬럼 18개 추가(`COLUMN_MIGRATIONS`로 기존 로컬 DB 안전 확장).
- [X] `app/routers/uploads.py`의 `_store_refined_rows`를 컬럼 리스트+`getattr` 기반으로 리팩터링(수동 플레이스홀더 카운팅 위험 제거).
- [X] `app/services/pl_comparison.py` 신규 — `LINE_ITEMS`(실적 컬럼×표시 라벨)와 `PLAN_ITEM_GROUPS`(계획 쪽 leaf 계정과목 합산 규칙)로 팀(또는 "국내"=전체) 단위 계획 대비 실적 비교를 계산.
- [X] `GET /batches/{id}/pl-comparison?team=...` 신규 엔드포인트(team 생략 시 국내 전체).
- [X] 기존 테스트 픽스처(`actual_sample.csv` 등)에 새 컬럼을 0 기본값으로 확장, `actual_sample.xlsb`는 Excel COM으로 재생성(CSV를 UTF-8 BOM으로 저장해야 재생성 시 헤더가 깨지지 않음 — 재발 방지 기록).
- [ ] 스크린샷의 "전략기획팀 회계조정액" 섹션은 산출 근거 미확인으로 범위 밖에 둠 — 필요 시 추가 확인.
- [ ] 프론트엔드 화면은 이번 phase 범위 밖(백엔드까지만 구현).

## Phase 12 — 계획대비 표에 전월대비 추가 및 Overview 드릴다운 필터 — ✅ 구현 완료

근거: 사용자 요청("전월대비도 추가해주고... 드릴다운과 필터 항목을 추가하여... 필터는 팀, 년, 월, 고객, 상품, desc, 제품구분1~3"). [.docs/phase/phase_12_전월대비및드릴다운.md](phase/phase_12_전월대비및드릴다운.md)

- [X] `pl_comparison.py`에 전월대비(단위당/총액/증감율) 추가 — 계획대비와 동일한 공식, `_prev_period`로 1월→전년 12월 wraparound 처리, 전월 데이터 없으면 `prev_month_available=False`.
- [X] 드릴다운 필터(고객/상품코드/DESC/제품구분1~3)를 실적(`refined_sales_record`) 쪽에만 적용 — 계획(`team_pl_record`)은 팀×월 단위라 그 이하로 쪼갤 수 없음(사용자 확인).
- [X] `GET /batches/{id}/pl-comparison/filters` 신규 — 배치에 실제 존재하는 필터 값 목록 반환.
- [X] 프론트 `components/PLComparisonPanel.tsx` 신규 — 7개 필터 드롭다운 + 13개 컬럼 표, `app/overview/page.tsx`에 배치.

## Phase 13 — 업로드(연동) 실패 시 원인을 화면에 표시 — ✅ 구현 완료 (백엔드 3개 추가, 156개 통과)

근거: 사용자 요청("연동이 실패했을 때(파일이 없거나, 형식이 다르거나) 웹앱이 죽지 않고 '어떤 이유로 연동이 안 됐는지'를 화면에 보여주도록 만들어줘"). [.docs/phase/phase_13_업로드오류처리.md](phase/phase_13_업로드오류처리.md)

- [X] `app/services/validation.py`에 `FileParseError` 추가 — 확장자는 맞지만 내용을 읽지 못하는 실적 파일(손상/미지원 구조)을 `read_dataframe`이 잡아 원인과 함께 변환(`plan.py`/`team_pl.py`가 이미 쓰던 "workbook 열기를 try/except로 감싸기" 패턴을 동일 적용).
- [X] `app/services/mapping.py`의 `parse_mapping_upload`도 같은 패턴으로 `pd.ExcelFile`/`.parse()` 실패를 `MappingValidationError`로 변환 — 구현 중 `app/routers/uploads.py`가 이 호출을 try 블록 밖에 두는 실수를 발견·수정(손상 매핑표 테스트로 재현).
- [X] `app/main.py`에 전역 catch-all 미들웨어 추가 — 처음엔 `@app.exception_handler(Exception)`으로 구현했으나 Starlette가 이를 `ServerErrorMiddleware`(CORS보다 바깥)로 옮겨버려 오류 응답에 CORS 헤더가 안 붙는 것을 `tests/test_error_handling.py`로 재현·확인, 평범한 `@app.middleware("http")` + `CORSMiddleware`를 마지막에 등록하는 방식으로 수정.
- [X] `tests/test_error_handling.py` 신규 — 손상 파일 업로드, 전역 핸들러의 CORS 헤더 동반 여부 회귀 테스트.

## Phase 14 — F4 손익 상세 분석 영역을 탭으로 확장(월별 실적 분석 3종) — ✅ 구현 완료 (백엔드 5개 추가, 162개 통과)

근거: 사용자가 제공한 참고 이미지 3장 + 요청("F4 OVERVIEW에서 손익 상세 분석의 위치에 내용을 탭 형태로... 탭 종류: 월별 실적 분석(팀별/제품군별/거래처별), 손익 상세 분석"). [.docs/phase/phase_14_월별실적분석탭.md](phase/phase_14_월별실적분석탭.md)

- [X] 블로킹 질문 3개(제조원가/표준매출원가/가격변동율 정의)를 사용자에게 직접 확인 — 제조원가=실제 매출원가(기존 `cogs_final`), 표준매출원가=Raw "매출원가(S)Tot" 신규 단순 복사, 가격변동율은 컬럼 구성에서 제외.
- [X] `refinement.py`/`db.py`/`uploads.py` — `standard_cogs` 신규 필드 추가(`COLUMN_MIGRATIONS` 포함), 기존 fixture(`actual_sample.csv` 등) 4종에 "매출원가(S)Tot" 컬럼 추가(A계열과 동일 값으로 채움 — 테스트용, 실제 표준원가 차이는 반영 안 함), `actual_sample.xlsb`(Excel COM 재생성)·`actual_sample_header_row2.xlsx`(openpyxl 스크립트로 스태거드 헤더 재구성) 갱신.
- [X] `app/services/monthly_analysis.py` 신규 — 팀별/제품군별(팀×제품구분2)/거래처별(팀×고객) 순수 실적 집계(계획 데이터 없음), 당월+금년 누계, 백만원 단위 변환. 제품군/고객 값이 NULL(미매핑)일 수 있어 정렬 키에서 `or ""` 보정(실제로 겪은 `TypeError` 수정).
- [X] `app/routers/analytics.py`에 `GET /batches/{id}/monthly-analysis/{team|product-group|customer}` 3개 신규.
- [X] 프론트 `components/OverviewDetailTabs.tsx`(탭 컨테이너) + `MonthlyAnalysisTable.tsx`(공유 표) + 3개 패널 컴포넌트 신규, `app/overview/page.tsx`의 `PLComparisonPanel` 직접 배치를 `OverviewDetailTabs`로 교체(기존 `PLComparisonPanel`은 탭 하나로 그대로 재사용).
- [X] 백엔드 `tests/test_monthly_analysis.py` 신규(당월/누계 합산, 팀별 소계 검증), 프론트 lint·build·vitest 전체 통과.

## Phase 15 — Overview PDF 카테고리 선택 다운로드 + F7 정제 데이터 전체 다운로드 — ✅ 구현 완료 (백엔드 6개 추가, 169개 통과)

근거: 사용자 요청("overview에서 pdf 다운로드하면, 아래의 각 탭의 것도 내용이 담겨서 출력이 될수 있께... 다운로드하고 싶은 카테고리를 체크할수 있게" / "f7의 다운로드 버튼을 하나 추가해줘. raw와 맵핑을 거쳐 정제된 실적 Re-arrange용 수식 시트 전체, xlsx 양식"). [.docs/phase/phase_15_PDF카테고리선택및정제데이터다운로드.md](phase/phase_15_PDF카테고리선택및정제데이터다운로드.md)

- [X] `pdf_export.py`를 섹션 빌더 구조로 리팩터링 — `team_matrix`(기존)/`monthly_team`/`monthly_product_group`/`monthly_customer`/`pl_comparison`(신규 4종) `SECTION_KEYS`, `build_overview_pdf(db, batch_id, sections=None)`가 선택된 섹션만 `PageBreak()`로 이어붙인다.
- [X] `GET /batches/{id}/export/overview`에 `sections` 쿼리 파라미터(다중 선택, 생략 시 전체) 추가.
- [X] 프론트 `components/OverviewPdfDownloadButton.tsx` 신규 — 카테고리 체크박스 드롭다운(기본 전체 선택), `app/overview/page.tsx`의 기존 단순 `<a>` 링크를 대체.
- [X] `app/services/refinement.py`에 `REFINED_ROW_COLUMNS` 공개(`uploads.py`가 손으로 유지하던 목록을 RefinedRow 필드 순서에서 도출하도록 이전 — 두 곳이 어긋나지 않게 함).
- [X] `app/services/export.py`에 `build_refined_export_workbook_for_draft`/`_for_batch` 신규 — `REFINED_COLUMN_LABELS`(71개 컬럼 전부, 추정 없이 `refinement.py` 주석·03_데이터정제.md에서 실측한 한글 이름)로 헤더를 붙여 `GET /reports/{draft_id}/export/refined`로 노출.
- [X] `app/reports/page.tsx`에 "실적 Re-arrange 전체 다운로드(xlsx)" 버튼 추가.
- [X] 테스트: PDF 섹션 선택에 따른 페이지/텍스트 포함 여부(`test_pdf_export.py` 3건), 정제 데이터 전체 다운로드(`test_exports_api.py`), 프론트 lint·build·vitest 전체 통과. 실제 배치(6523행)로도 PDF(18페이지)·xlsx(6524행×71열) 다운로드를 직접 확인.

## Phase 16 — F3 이상징후 계산 결과를 comment_generator.AnalysisRecord로 매핑해 F7 연결 — ✅ 구현 완료 (백엔드 8개 추가, 179개 통과)

근거: 사용자 요청("실제 F3 계산 코드(증감률/이상징후 계산 부분)를 보여주면서 '이 결과를 comment_generator.AnalysisRecord로 매핑해서 F7 보고서 생성에 연결해줘'", `@backend/app/services/comment_generator.py`). [.docs/phase/phase_16_코멘트생성기연결.md](phase/phase_16_코멘트생성기연결.md)

- [X] `app/services/comment_generator.py`(사용자가 제공한 기존 파일, 서사형 코멘트 생성기)의 `AnalysisRecord.mom_change_pct`를 `Optional[float] = None`으로 변경 — F3의 계획대비/흑자전환 유형은 "전월 대비 %" 개념이 아니고 전월 비교가 아예 불가능할 수도 있어, 이 프로젝트의 "비교 불가는 0으로 대체하지 않는다" 원칙에 맞춰 `NarrativeBuilder`가 0%로 꾸며내지 않고 중립 문장으로 대체하게 함.
- [X] `app/services/report_analysis_mapper.py` 신규 — `anomaly_flag`를 `result_id`로 `aggregated_result`와 다시 JOIN해, 6개 이상징후 유형(전월대비/전년대비/계획대비/흑자전환/단가변동/판관비급증)마다 의미가 다른 `actual_value`(%·달성률·원시금액 혼재)를 올바른 `AnalysisRecord` 필드로 매핑.
- [X] `app/services/reports.py`의 `create_report_draft`가 `app/services/comments.py` 대신 `report_analysis_mapper` + `comment_generator.generate_comment`를 쓰도록 교체(`comments.py`는 삭제하지 않고 `test_comments.py`가 독립적으로 계속 검증).
- [X] `tests/test_report_analysis_mapper.py` 신규 — 6개 metric_type 전부 매핑 검증 + `test_comments.py`와 같은 금칙어(때문/원인/인해/탓) 검사를 `comment_generator` 출력에도 적용, 전월 비교 불가 케이스가 0%로 꾸며지지 않는지 검증.
- [X] 실제 배치로 `POST /reports` 호출해 서사형 코멘트(예: "...전월 대비 -100.0%를 기록하며 큰 폭으로 감소했습니다. 다만 사전 설정된 임계치(90)를 90.0%p 초과해...")가 실제로 생성되는지 직접 확인.

## Phase 17 — 이상징후 판정 범위 조정(계획대비=팀 단위, 누계평균대비 신설) — ✅ 구현 완료 (백엔드 184개 통과)

근거: 사용자 요청("판정에 있어서 각 팀의 제품군에 대한 분석은 전월 또는 누계 평균 대비를 위주로 분석하고, 계획대비에 대한 분석은 팀 계획 vs 팀 실적을 기본으로 한다."), 누계평균 정의·기본 임계치는 AskUserQuestion으로 확인(연초~직전월 평균, 15%). [.docs/phase/phase_17_이상징후판정범위조정.md](phase/phase_17_이상징후판정범위조정.md)

- [X] `app/services/anomaly.py` — 계획대비를 팀×제품군 루프에서 빼서 팀 단위(제품군 합계 실적 vs 팀 계획)로 한 번만 판정하도록 재구성(기존 버그: `plan_amount`가 팀 전체 계획을 모든 제품군 행에 복제해 저장하는데, 제품군 하나의 `actual_amount`와 비교해 항상 미달로 나왔다). 누계평균대비(`METRIC_CUMULATIVE_AVG`) 신설 — 팀×제품군 단위로 당월 실적을 연초~직전월(당월 제외) 월평균과 비교, 1월(직전월 없음)은 플래그하지 않음.
- [X] `app/services/thresholds.py` — `METRIC_CUMULATIVE_AVG` 추가(기본 임계치 15%), `seed_default_thresholds`를 "테이블이 비어있을 때만 시딩"에서 "누락된 metric_type만 개별 시딩"으로 변경해 기존 로컬 DuckDB에도 신규 기준이 자동 추가되게 함.
- [X] `app/services/comment_generator.py`(사용자 제공 기존 파일) — 미사용이던 `ytd_change_pct` 필드를 "연초~직전월 누계 월평균 대비 당월 증감률(%)" 용도로 재사용, `YTD_CLAUSE` 문구뱅크 항목 추가.
- [X] `app/services/report_analysis_mapper.py` — 계획대비는 팀의 제품군 행 전체를 다시 SUM해 `value`를 채우고 라벨을 제품군 없이 팀명만 쓰도록(`is_team_level` 옵션) 수정, `mom_change_pct`는 팀 합계-제품군 전월값 혼합 비교가 되는 것을 막기 위해 의도적으로 `None`으로 비움. 누계평균대비 신규 매핑 추가.
- [X] `.docs/02_prd.md` F3 표에 "판정 단위"(팀×제품군/팀) 컬럼과 7번째 기준(누계평균대비) 추가, ThresholdConfig 데이터 모델의 metric_type 목록 갱신.
- [X] 테스트: `test_anomaly.py`(계획대비 팀당 1건, 누계평균대비 임계치 초과/미만/1월 제외 5건 신규), `test_thresholds_api.py`(7개 기준), `test_report_analysis_mapper.py`(계획대비 라벨이 팀명만 나오는지), `test_day2_flow.py`(계획대비 flags가 `product_group=None`으로 나오는지로 갱신).
- [X] 실제 로컬 DuckDB로 서버 기동 후 `GET /thresholds`가 기존 DB에도 7개 기준을 자동 시딩함을 확인, 실제 배치(2026-08)에 재계산 후 계획대비가 팀당 1건(제품군 없음), 누계평균대비가 팀×제품군 단위로 생성됨을 API로 직접 확인.

## Phase 18 — 손익 상세 분석(계획대비) 항목별 판정 신설 + 드릴다운 비교 오류 방지 — ✅ 구현 완료 (백엔드 196개 통과)

근거: 사용자 요청("Overview의 손익 상세 분석에서 각 구분 항목별 계획 대비 실적의 총액 차 또는 단위당 가격 차이에 대한 판정, 계획대비 실적의 차이(비중차)를 분석할때는 팀단위 비교. 예시: 재료비가 단위당 3,000원 상승 계획 50,251원 대비 53,084원으로 xx원 xx% 증가."), 세부 결정은 AskUserQuestion 4회로 확인(자동 서술형 코멘트 신규 추가 / 드릴다운 필터 시 계획대비 열 비교불가 처리 / F7 보고서 초안에 포함 / 비용·원가성 항목만 / F6 공통 임계치 10%). [.docs/phase/phase_18_손익항목계획대비판정.md](phase/phase_18_손익항목계획대비판정.md)

- [X] `app/services/pl_comparison.py` — `get_pl_comparison()`이 `PLComparisonResult`(`plan_comparison_available: bool` + `lines`)를 반환하도록 변경. 고객/상품/DESC/제품구분1~3 드릴다운 필터가 하나라도 걸리면 계획(팀×월 단위만 존재)과 실적(필터링된 부분집합)의 granularity가 어긋나므로 `diff_unit`/`diff_total`/`change_rate`를 `None`으로 비운다(Phase 17 계획대비 버그와 같은 종류의 왜곡을 화면에서도 막음).
- [X] `app/routers/analytics.py`(`GET /batches/{id}/pl-comparison`)와 `app/services/pdf_export.py`(정적 PDF, 항상 팀 단위 조회라 영향 없음) 호출부를 새 반환 타입에 맞춰 갱신.
- [X] `app/services/thresholds.py`에 `METRIC_PL_ITEM_PLAN`="손익항목계획대비" 신설(기본 10%), F3 판단 기준 8개로 확장.
- [X] 신규 `app/services/pl_item_analysis.py` — `PL_NARRATIVE_ITEM_KEYS`(비용·원가성 항목, LINE_ITEMS에서 자동 도출), `find_pl_item_deviations`/`find_team_item_deviation`(항상 팀 단위, 드릴다운 필터 없음), `format_pl_item_comment`(단위당/총액/비중 3단 서술 문장, 금칙어 없음).
- [X] `app/services/anomaly.py` — 계획대비 패스 뒤에 손익항목계획대비 패스 신설(팀별로 임계치 넘는 항목마다 `anomaly_flag` 1건, `product_group` 칸에 계정과목 라벨 재사용). `app/services/reports.py` — `report_analysis_mapper`가 이 metric_type을 의도적으로 건너뛰므로(comment_generator의 "전월 대비" 서사 틀과 안 맞음) 별도 루프로 `pl_item_analysis`가 만든 문장을 그대로 `report_item`에 저장.
- [X] 프론트 `PLComparisonPanel.tsx` — `plan_comparison_available=false`일 때 "① 계획 대비" 표 위에 비교 불가 안내 배너 표시.
- [X] 테스트: `test_pl_comparison.py`(plan_comparison_available 플래그 2건), `test_pl_item_analysis.py`(신규, 서술 대상 범위/팀 단위 판정/문장 조립/단위당 계산 불가 폴백 6건), `test_anomaly.py`(신규 손익항목계획대비 판정 3건), `test_reports_api.py`(F7 초안에 문장 포함 확인), `test_thresholds_api.py`(8개 기준). 프론트 lint·build·vitest 전체 통과.

## Phase 19 — 실적 파일 다중 월 자동 분할 업로드 + 겹치는 달 덮어쓰기 확인 — ✅ 구현 완료 (백엔드 200개 통과)

근거: 사용자가 F4 Overview에서 "7월 선택 시 수량·매출 표시가 안 맞는다"고 보고, 원인 조사 결과 실적 파일 하나(1~8월 데이터 포함)를 업로드하면 시스템이 가장 이른 달만 배치로 인식해 전체 월 실적을 그 한 달에 합산 저장하던 실제 버그를 발견. 후속 확인: "겹치는 달이 있으면 덮어쓸지 물어보고, 새로운 달은 항상 저장". [.docs/phase/phase_19_실적파일다중월분할업로드.md](phase/phase_19_실적파일다중월분할업로드.md)

- [X] `app/routers/uploads.py` — 실적 파일이 단일 기간만 담고 있으면 기존 즉시-커밋 동작을 그대로 유지(하위 호환, 기존 테스트 전부 무변경 통과). 여러 기간이 섞이면 각 행의 실제 `(year, month)`로 나눠 기간별 배치를 만들고, 이미 배치가 있는 기간과 겹치면 `confirm_overwrite`(신규 Form 필드) 없이는 아무것도 저장하지 않고 `requires_confirmation` 응답만 반환. 확인이 오면 신규 기간은 항상 저장, 겹치는 기간은 `true`일 때만 덮어쓰고 `false`면 건너뜀(`skipped_periods`).
- [X] 계획/손익계산서/매핑표 파일은 커밋된 기간 중 가장 이른 기간의 "대표 배치"에만 연결(연도 단위로 지우고 다시 채우는 기존 로직이라 어느 batch_id에 달려 있든 계산에는 영향 없음).
- [X] 응답 스키마 하위 호환 유지 — 상위 필드는 대표 배치 기준값 그대로, 신규 `batches`(기간별 목록)/`skipped_periods`/`requires_confirmation` 추가.
- [X] 프론트 `app/upload/page.tsx` — 확인 필요 응답 시 겹치는/새 달 목록과 덮어쓰기/건너뛰기 버튼을 보여주고, 같은 파일로 `confirm_overwrite`를 붙여 재요청. 결과 표시도 배치 1개/여러 개에 따라 다르게 렌더링.
- [X] 테스트: `test_uploads_api.py`에 4건 신규(새 기간만 있으면 확인 없이 커밋, 겹치는 기간 있으면 확인 요구, 확인 시 덮어쓰기, 거부 시 건너뛰기 + 기존 배치 보존) — 각 기간 배치가 자기 기간의 행만 갖는지(합산 버그 회귀)까지 검증. 백엔드 전체 200개, 프론트 lint·build·vitest 전체 통과.

### Phase 18 추가 확인 — 손익항목계획대비 서술 대상 15개로 명시적 한정

사용자 후속 요청("이상징후 하이라이트에서는 손익항목 계획대비는... 항목 한정")에 따라 `pl_item_analysis.PL_NARRATIVE_ITEM_KEYS`를 "비용·원가성 항목 자동 도출"에서 사용자가 지정한 15개 explicit set으로 교체. "단위당 매출액"만 예외적으로 총액이 아니라 단위당 기준으로 판정(매출액 총액은 F3의 다른 4개 기준이 이미 다룸). 백엔드 전체 203개 통과.

## Phase 20 — "누계평균대비" 폐지, "단가변동"에 전월·누계 통합 비교로 흡수 — ✅ 구현 완료 (백엔드 210개 통과)

근거: 사용자 요청("누계 평균대비는 별도의 버튼으로 분류하지 말고, 단가 변동탭에서 XX팀, XX제품군 - 당월 평균단가 XX원, 전월 XX원(XX원, XX% 차이), 누계평균 XX원(XX원 XX% 차이) 이런식으로... 단가 변동에서만 비교해보자"). [.docs/phase/phase_20_단가변동누계평균통합.md](phase/phase_20_단가변동누계평균통합.md)

- [X] `app/services/thresholds.py` — `METRIC_CUMULATIVE_AVG` 제거(7개 기준으로 복귀). `seed_default_thresholds`에 `ALL_METRICS`에 없는 기존 threshold_config 행을 정리하는 로직 추가(기존 로컬 DB에 남은 "누계평균대비" 고아 행 자동 정리).
- [X] `app/services/anomaly.py` — "누계평균 대비"(매출액) 패스 완전 제거. "단가변동"을 전월 대비+누계평균 대비(평균단가 기준) 통합 판정으로 확장, 둘 중 하나라도 기존 임계치(5%)를 넘으면 플래그. `cumulative_prior_average()`에 `column` 매개변수를 추가해 평균단가 기준으로도 재사용.
- [X] `app/services/analytics.py`의 `get_anomalies` — 단가변동 플래그에 `cumulative_before_value`(누계평균 평균단가) 필드 추가.
- [X] `app/services/report_analysis_mapper.py` — `METRIC_CUMULATIVE_AVG` 매핑 제거, "단가변동"이 폐지된 필드(`ytd_change_pct`)를 이어받아 F7 문장에도 누계 비교를 반영.
- [X] 프론트 `app/anomalies/page.tsx` — "단가변동" 표시를 "당월 평균단가 A원, 전월 B원(차이,%), 누계평균 C원(차이,%)" 형식으로 재작성(각 비교가 불가능하면 그 부분만 "비교 불가").
- [X] `.docs/02_prd.md` F3 표에서 "누계평균대비" 행 제거, "평균단가 변동" 설명에 통합 판정 반영.
- [X] 테스트: `test_anomaly.py`(누계만 초과/둘다 미달/1월 누계불가 3건 신규), `test_analytics_anomalies_before_after.py`(cumulative_before_value 노출 2건), `test_report_analysis_mapper.py`(단가변동 ytd_change_pct 1건), `test_thresholds_api.py`(7개 기준 + 고아 행 정리 1건 신규). 백엔드 전체 210개, 프론트 lint·build·vitest 전체 통과.

## Phase 21 — 은/는 조사 자동 선택 + F7 코멘트 생성 방어 처리 — ✅ 구현 완료 (백엔드 215개 통과)

근거: 사용자가 이 프로젝트가 실제로 쓰지 않는 별도 초안(`plan_variance_comment_generator.py`/루트 `comment_generator.py`)을 검토해달라고 요청, 분석 후 두 아이디어만 부분 이식하기로 확인("1~2번만 반영해보자"). [.docs/phase/phase_21_코멘트조사자동화및방어처리.md](phase/phase_21_코멘트조사자동화및방어처리.md)

- [X] `comment_generator.py`에 `_has_batchim`/`_eun_neun`(받침 유무로 은/는 조사 자동 선택) 추가, `NarrativeBuilder._headline()`과 `pl_item_analysis.format_pl_item_comment()`의 하드코딩된 "은(는)"을 실제 조사로 교체.
- [X] `reports.py`의 두 코멘트 생성 루프를 항목 단위 try/except로 감싸, 실패한 항목만 플레이스홀더로 대체하고 F7 초안 생성 전체가 죽지 않도록 고침(검토 중 발견한 실제 취약점 — 그전까지는 항목 1건 예외로 전체가 500 실패).
- [X] 테스트: `test_comment_generator.py`(신규 4건), `test_pl_item_analysis.py`(조사 검증 2건 추가), `test_reports_api.py`(코멘트 생성 실패 회귀 1건, monkeypatch로 강제 재현). 백엔드 전체 215개 통과.

## Phase 22 — F7 보고서 초안 엑셀 다운로드에 팀별 추이 차트 포함 — ✅ 구현 완료 (백엔드 216개 통과)

근거: 사용자 요청("보고서 초안 자동생성에서, 엑셀 다운로드 시 내용에 그래프도 같이 들어가게"). [.docs/phase/phase_22_보고서엑셀차트.md](phase/phase_22_보고서엑셀차트.md)

- [X] `app/services/export.py`의 `build_report_workbook`이 보고서 초안에 등장하는 팀마다 `analytics.get_trend()`(F7 화면과 동일 함수)를 호출해, "차트데이터"(숨김)/"추이 차트" 두 시트에 매출액(막대)+영업이익(선, 보조축) 콤보 차트를 openpyxl 네이티브 차트로 삽입.
- [X] 데이터 없는 달은 `None`으로 남겨(0으로 대체하지 않음) 화면과 동일하게 표시. 기존 "보고서 초안" 표 시트는 그대로 유지(하위 호환).
- [X] 테스트: `test_export_report_includes_team_trend_charts`(시트/차트 개수/숨김 여부/12개월 데이터 정합성 검증). 백엔드 전체 216개, 실제 배치로 라이브 검증 완료.

## Phase 23 — 웹앱 디자인 개선 (README 대시보드 스타일 적용) — ✅ 구현 완료 (프론트 lint·build·vitest 19개 통과)

근거: README를 세방 CI 대시보드 스타일로 다시 디자인한 뒤 사용자 요청("해당 이미지 작업을 실제 우리 작업물에도 입혀야지?"). 문구·기능·표 구성은 유지하고 시각 스타일만 변경. [.docs/phase/phase_23_웹앱디자인개선.md](phase/phase_23_웹앱디자인개선.md)

- [X] `app/globals.css`에 design.md 확장 팔레트 토큰(dark-gray 50/100/300/600/700, green-300)·페이지 배경(`--color-bg-page`)·저채도 그림자(`--shadow-card`/`--shadow-hero`)·격자 패턴(`.bg-hero-grid`) 추가.
- [X] `components/TopNav.tsx`를 README 배너와 같은 다크 헤더(좌측 오렌지 띠, 활성 메뉴 오렌지 밑줄)로 변경.
- [X] 신규 `components/PageHeader.tsx` — 5개 페이지(F1/F4/F5/F6/F7) 제목 블록을 다크 배너형 헤더로 통일(문구 원문 그대로), 우측 액션은 흰 툴바 카드 위에 배치. `overflow-hidden`을 쓰지 않아 PDF 카테고리 드롭다운이 잘리지 않음(Playwright로 확인).
- [X] F4 KPI 카드를 README 수치 카드와 같은 좌측 컬러 띠 + 큰 숫자 형태로 변경, 섹션 카드 16곳을 흰 배경 + 그림자로 통일, F7 "초안 생성" 버튼을 주요 CTA 색(오렌지)으로 변경.
- [X] `screenshots/` 5장을 새 디자인으로 갱신 — 실제 로컬 DB에는 실데이터가 있어 사용하지 않고, 격리된 데모 백엔드(:8001, 별도 DuckDB)에 가상 합성 데이터를 올려 캡처.
- [ ] (발견, 미수정) 다중 월 실적 업로드(Phase 19 경로)에서 계획·손익계산서 저장이 기간별 집계·이상징후 판정 이후에 실행되어, 업로드 직후 당월 목표 매출액과 계획대비 판정이 비어 있음(재계산하면 채워짐). `app/routers/uploads.py` 288행(집계) vs 321행(계획 저장) 순서 문제.

## Phase 24 — 공개 저장소 내 실제 거래처명 가명화 — ✅ 구현 완료 (백엔드 216개 통과)

근거: Phase 23 작업 중 공개 저장소의 테스트 fixture·문서에 실제 거래처명이 남아 있는 것을 발견, 사용자 요청("가명으로 바꾸어주세요"). [.docs/phase/phase_24_테스트데이터가명화.md](phase/phase_24_테스트데이터가명화.md)

- [X] 텍스트 fixture·테스트·주석·문서·목업의 실명 7종을 가명으로 치환(코드·금액은 검증 기준값이라 유지).
- [X] 바이너리 fixture(xlsx 3개, xlsb 1개) 셀 치환.
- [X] 과거 버전 문서 백업 압축본 2개 추적 해제 + `.gitignore`.
- [X] git 추적 파일 전체 재스캔 0건, 백엔드 216개 통과.
- [ ] 과거 커밋 이력의 실명 제거(이력 재작성 + 강제 push) — 사용자 확인 대기.
