# Phase 14 작업 계획서 — F4 Overview 손익 상세 분석 영역을 탭으로 확장

- 근거: 사용자가 제공한 참고 이미지 3장(팀별/월별 몬쓸리, "7. 월별 실적 분석_제품군별", "8. 팀별 실적 분석_거래처별")과 사용자 요청 원문 — "F4 OVERVIEW에서 손익 상세 분석의 위치에 내용을 탭 형태로 해서... 탭 종류: 월별 실적 분석(팀별), 월별 실적 분석(제품군별), 월별 실적 분석(거래처별), 손익 상세 분석(현재 화면 구성 그대로)".
- 블로킹 질문 3개에 대한 사용자 확정 답변(2026-09-28):
  - 제조원가 = **실제 매출원가**(기존 `cogs_final`, Raw "매출원가(A)Tot" 원본 그대로).
  - 표준매출원가 = **실적 파일에 이미 있는 컬럼**(Raw "매출원가(S)Tot" — `.docs/03_데이터정제.md` §2.1에서 확인된, 지금까지 안 쓰던 Standard(S) 계열 컬럼을 신규로 단순 복사).
  - 가격변동율 = **이번 탭 컬럼 구성에서 제외**(정의를 만들지 않는다).

## 범위

**구현**:
1. `refinement.py`/`db.py`: `RefinedRow`/`refined_sales_record`에 `standard_cogs`(표준매출원가, Raw "매출원가(S)Tot" 단순 복사) 필드 신규 추가.
2. 신규 서비스 `app/services/monthly_analysis.py` — 계획 대비가 아니라 **순수 실적 집계**다(요청된 컬럼 목록에 목표/계획 항목이 전혀 없음). 당월(현재 배치)과 금년 누계(연초~해당 월, `analytics.py`의 `get_cumulative_teams`와 같은 "여러 배치의 `refined_sales_record`를 연초~선택월로 직접 합산" 패턴)를 함께 반환한다.
   - 팀별: 팀 단위 집계 + 합계 행. 컬럼: 수량/매출액/영업이익/이익률/판관비/판관비율/제조원가/제조원가율/표준매출원가.
   - 제품군별: 팀×제품구분2(`product_group_2`) 집계, 팀별 "OO 요약" 소계 행 + 전체 합계 행(참고 이미지의 그룹 구조). 컬럼: 수량/매출액/영업이익/이익률/판매가/제조원가율/판관비율.
   - 거래처별: 팀×고객(`customer_name`) 집계, 팀별 소계 행 + 전체 합계 행. 컬럼: 수량/매출액/영업이익/영업이익%.
   - 금액류(매출액/영업이익/판관비/제조원가/표준매출원가)는 **백만원 단위**로 변환해 반환한다(참고 이미지 단위 표기 "단위 : EA,백만원"). 판매가(=매출액÷수량)도 같은 표 단위 기준을 따라 백만원/EA로 반환한다.
3. `app/routers/analytics.py`에 `GET /batches/{id}/monthly-analysis/{team|product-group|customer}` 3개 신규 엔드포인트.
4. 프론트: `app/overview/page.tsx`의 현재 `PLComparisonPanel` 자리를 탭 컨테이너로 바꾸고, `월별 실적 분석(팀별/제품군별/거래처별)` 3개 신규 화면 + `손익 상세 분석`(기존 `PLComparisonPanel`, 변경 없음) 탭으로 구성한다.

**범위 밖(이번에 하지 않음)**:
- 가격변동율 — 사용자가 명시적으로 이번 컬럼 구성에서 제외를 확인.
- "산전팀"(고정형+모티브 합산) 같은 합성 그룹 — 참고 이미지·요청 문구 어디에도 이 3개 탭에 대한 합성 그룹 언급이 없어 추가하지 않는다(기존 F4 목표 대비 매트릭스와는 별개 화면).
- 참고 이미지 1장(팀×월 12행 나열 + "산전용 요약" 포함)은 다른 원본 참고자료로 보고 이번 탭의 실제 레이아웃 기준으로 삼지 않는다 — 실제 채택 레이아웃은 사용자 요청 원문의 컬럼 목록 + 나머지 두 참고 이미지(당월/금년누계 2단 헤더, 팀별 소계 행)를 따른다.

## 방법

1. `.docs/03_데이터정제.md`에 "매출원가(S)Tot" 신규 확인 사실 기록.
2. `app/services/refinement.py`: `REQUIRED_RAW_COLUMNS`에 "매출원가(S)Tot" 추가, `RefinedRow.standard_cogs` 추가, `refine_row`에서 단순 복사.
3. `app/db.py`: `refined_sales_record.standard_cogs` 컬럼 + `COLUMN_MIGRATIONS` 추가.
4. `app/routers/uploads.py`: `_REFINED_ROW_COLUMNS`에 `standard_cogs` 추가.
5. `app/services/monthly_analysis.py` 신규 — 3개 조회 함수 + 백만원 변환 헬퍼.
6. `app/routers/analytics.py`: 3개 엔드포인트 추가.
7. `frontend/lib/api.ts`: 타입 + 함수 3종 추가.
8. `frontend/components/`에 탭 컨테이너(`OverviewDetailTabs.tsx` 가칭)와 3개 신규 패널 컴포넌트 추가, `app/overview/page.tsx`에서 교체.
9. 테스트: 신규 필드(회귀), 3개 조회 함수 단위 테스트(당월/누계 합산, 소계·합계 행 검증), API 테스트, 프론트 lint/build/vitest.
10. 기존 fixture(`actual_sample.csv` 등)에 "매출원가(S)Tot" 컬럼을 실측 없이 추가해야 하므로, 기존 값과 동일한 값(A계열과 동일하게 둠 — 테스트용 더미이므로 실제 표준원가 차이는 반영하지 않음, 실제 파일에서는 서로 다른 값일 수 있다는 점을 문서에 남긴다)으로 채운다.

## 완료 기준

- 3개 신규 탭이 당월/금년 누계 값을 정확히 계산하고(단위 테스트), 팀별 탭은 팀+합계, 제품군별/거래처별 탭은 팀별 소계+전체 합계 구조로 표시된다.
- 표준매출원가 필드 추가가 기존 회귀 테스트(`test_refine_matches_verified_excel_row1` 등)를 깨지 않는다.
- 백엔드 전체 pytest, 프론트 lint·build·vitest 통과.
