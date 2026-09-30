# Phase 12 작업 계획서 — 계획대비 표에 전월대비 추가 및 Overview 드릴다운 필터

- 근거: 사용자 요청(원문) — "전월대비도 추가해주고, 이미지의 표와 같이 overview 쪽에서 드릴다운과 필터 항목을 추가하여 해당 표를 분석에 활용할 수 있게 화면을 구현하면 좋겠다. 필터는 팀, 년, 월, 고객, 상품, desc, 제품구분1~3 항목이 있으면 어떤가 싶어. 계획(손익계산서) 부분은 팀, 월 을 구분하여 필터링 할수 있게 동작하면 좋겠다"
- 배경: Phase 11에서 구현한 `pl-comparison`(계획대비) 화면 참고 이미지에 "전월 실적" 피벗 블록이 별도로 존재함을 확인 — 계획대비 외에 전월대비도 같은 표 안에 필요하다는 근거.

## 범위

**구현**:
1. `pl_comparison.py`의 `get_pl_comparison`에 전월 실적(prev_month) 합계·단위당·비중·계획대비와 동일한 방식의 전월대비(단위당/총액/증감율)를 추가한다. 1월은 전년 12월을 전월로 취급한다(`_prev_period`). 전월 데이터가 없으면 `prev_month_available=False`로 표시하고 0으로 대체하지 않는다(F3 이상징후 판정과 동일한 원칙).
2. 드릴다운 필터(고객/상품코드/DESC/제품구분1~3)를 `get_pl_comparison`에 추가한다. **필터는 실적(`refined_sales_record`) 쪽에만 적용한다** — 계획(`team_pl_record`)은 팀×계정과목×월 단위로만 존재해 그 이하로 쪼갤 수 없기 때문에(사용자 확인: "계획(손익계산서) 부분은 팀, 월 을 구분하여 필터링"), 계획 쪽은 팀·년월 선택만 받는다.
3. 필터 드롭다운에 넣을 실제 값 목록을 반환하는 신규 엔드포인트(`GET /batches/{id}/pl-comparison/filters`)를 추가한다.
4. 프론트엔드에 `components/PLComparisonPanel.tsx`(신규)를 만들어 팀/고객/상품/DESC/제품구분1~3 드롭다운 + 계획·실적·계획대비·전월대비 13개 컬럼 표를 렌더링하고, `app/overview/page.tsx`에 배치한다. 년/월 필터는 이미 Overview 자체가 배치(=년월) 단위 화면이라 별도 구현 없이 배치 선택으로 대체한다.

**범위 밖(이번에 하지 않음)**:
- 전년동월대비를 이 표에 추가하는 것 — 사용자가 요청한 것은 전월대비까지다.
- 계획 쪽 드릴다운(고객/상품 단위 계획) — `team_pl_record`가 팀×월 단위로만 존재해 데이터 자체가 없다.

## 방법

1. `backend/app/services/pl_comparison.py`: `PLLineComparison`에 `prev_month_*`/`diff_prev_month_*`/`change_rate_prev_month` 필드 추가, `_prev_period` 헬퍼 추가, `FILTER_COLUMNS`로 동적 WHERE 절 구성(`_build_refined_filter`), `get_pl_comparison_filter_options` 추가.
2. `backend/app/routers/analytics.py`: 기존 `/pl-comparison`에 쿼리 파라미터(customer/product_code/desc/product_group_1~3) 추가, `/pl-comparison/filters` 신규 라우트 추가.
3. 프론트엔드: `lib/api.ts`에 타입/함수 추가, `components/PLComparisonPanel.tsx` 신규 작성, `app/overview/page.tsx`에서 `key={batchId}`로 배치 전환 시 전체 리마운트(내부 필터 상태를 `useEffect` 안에서 초기화하지 않기 위해 — `react-hooks/set-state-in-effect` 대응).
4. 테스트: 전월대비 계산(1월 wraparound 포함, 전월 데이터 없을 때), 필터 적용, 필터 옵션 API, 프론트 lint/build/vitest.

## 완료 기준

- 계획대비와 동일한 정밀도로 전월대비 수치가 계산되고, 전월 데이터가 없는 배치(예: 최초 업로드)에서도 크래시 없이 "비교 불가"로 표시된다.
- Overview 화면에서 7개 필터(팀/고객/상품/DESC/제품구분1~3)로 실적 쪽만 좁혀 계획대비/전월대비 표를 다시 조회할 수 있다.
- 백엔드 pytest, 프론트 lint/build/vitest 전체 통과.
