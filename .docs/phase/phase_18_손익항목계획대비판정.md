# Phase 18 작업 계획서 — 손익 상세 분석(계획대비) 항목별 판정 신설 + 드릴다운 비교 오류 방지

- 근거: 사용자 요청(원문) — "Overview의 손익 상세 분석에서 각 구분 항목별 계획 대비 실적의 총액 차 또는 단위당 가격 차이에 대한 판정, 계획대비 실적의 차이(비중차)를 분석할때는 팀단위 비교. 예시 : 재료비가 단위당 3,000원 상승 계획 50,251원 대비 53,084원으로 xx원 xx% 증가."
- 사용자 확인(AskUserQuestion, 2026-09-28):
  1. 자동 서술형 코멘트를 새로 만드는 것이 맞다(계산 로직만 고치는 게 아님).
  2. 드릴다운 필터(고객/상품/DESC/제품구분1~3)가 걸려 있으면 화면의 "계획대비" 열은 비교불가 처리한다(필터링된 실적을 팀 전체 계획과 비교하는 것은 잘못된 비교이므로).
  3. 서술형 코멘트는 F7 보고서 초안에 포함한다(화면에는 표시하지 않는다).
  4. 서술 대상은 38개 손익 계정과목 중 매출액/수량/영업이익을 뺀 비용·원가성 항목만.
  5. F6에 신설할 공통 임계치("손익항목계획대비") 기본값은 ±10%(전월대비와 동일 수준).

## 배경/동기

`app/services/pl_comparison.py`(손익 상세 분석, F4 하단 탭)는 계획(`team_pl_record`)을 팀×월 단위로만 조회하고, 드릴다운 필터(고객/상품/DESC/제품구분1~3)는 실적(`refined_sales_record`) 쪽에만 적용된다(기존 설계, 문서화됨). 따라서 필터가 걸린 상태에서는 "필터링된 실적" vs "팀 전체 계획"을 비교하게 되어, Phase 17에서 수정한 F3 계획대비의 버그(제품군 하나의 실적을 팀 전체 계획과 비교)와 같은 종류의 왜곡이 화면에 남아있다.

또한 이 표는 지금까지 숫자만 보여줄 뿐, "어떤 항목이 계획 대비 얼마나 벗어났는지"를 문장으로 정리해주지 않는다. 사용자는 이 표의 각 계정과목(재료비/노무비/경비/판관비 세부)에 대해 팀 단위로 총액차·단위당가격차·비중차를 판정해 F7 보고서에 문장으로 포함하길 원한다.

## 범위

**구현**:
1. `app/services/pl_comparison.py`: `get_pl_comparison()`이 "드릴다운 필터가 하나라도 걸려 있는지" 여부를 `plan_comparison_available: bool`로 함께 반환하도록 변경(팀 필터만 있는 경우는 계획도 팀 단위로 조회되므로 True 유지, 고객/상품/DESC/제품구분1~3 중 하나라도 값이 있으면 False). False일 때는 `diff_unit`/`diff_total`/`change_rate` 세 필드를 `None`으로 비운다(실적은 그대로 보여주되, 잘못된 계획 비교값만 숨긴다).
2. `app/routers/analytics.py`의 `GET /batches/{id}/pl-comparison` 응답에 `plan_comparison_available` 필드 추가.
3. 프론트 `PLComparisonPanel.tsx`: `plan_comparison_available=false`일 때 "① 계획 대비" 표의 계획대비 3개 열을 "비교 불가"로 표시하고, 안내 문구를 추가한다.
4. `app/services/thresholds.py`에 `METRIC_PL_ITEM_PLAN = "손익항목계획대비"` 신설(단일 `threshold_value`, 기본 10.0).
5. 신규 `app/services/pl_item_analysis.py`:
   - `PL_NARRATIVE_ITEM_KEYS` = `pl_comparison.LINE_ITEMS`의 key 전체에서 `{quantity, sales_final, operating_profit_final}`를 뺀 나머지(비용·원가성 항목, 자동 도출 — 하드코딩 목록을 따로 유지하지 않는다).
   - `find_pl_item_deviations(db, batch_id, threshold_pct)`: `pl_comparison.TEAMS` 4개 팀 각각에 대해 드릴다운 필터 없이 `get_pl_comparison(db, batch_id, team=[team])`을 호출하고(=항상 팀 전체 실적 vs 팀 계획, 사용자 확인 "팀단위 비교"), `PL_NARRATIVE_ITEM_KEYS`에 속하고 `plan_total != 0`이며 `|change_rate*100| >= threshold_pct`인 라인만 추려 반환한다.
   - `format_pl_item_comment(dev)`: "{팀} {항목}은(는) 단위당 계획 A원 대비 실적 B원으로 C원 상승/하락했습니다. 총액 기준으로는 계획 D원 대비 실적 E원으로 F원(G%) 증가/감소했습니다."(단위당 계산 불가 시 그 문장 생략) + 매출액 대비 비중(계획→실적, %p 변동) 문장을 이어 붙인다. "때문/원인/인해/탓" 등 원인 추정 어휘를 쓰지 않는다.
6. `app/services/anomaly.py`: 기존 팀 단위 계획대비 패스 뒤에 새 패스 추가 — `find_pl_item_deviations`로 임계치를 넘는 항목마다 `anomaly_flag` 1건을 저장한다(`team`=팀, `product_group`=항목 라벨(예: "재료비 계") 재사용, `metric_type`="손익항목계획대비", `actual_value`=증감율(%), `impact_amount`=총액차). F5 이상징후 화면에도 자연히 노출된다(기존 파이프라인 재사용).
7. `app/services/report_analysis_mapper.py`: `METRIC_PL_ITEM_PLAN`은 `_METRIC_NAME_AND_CATEGORY`에 추가하지 않아 `build_analysis_records`가 자동으로 건너뛴다(이 유형은 comment_generator의 "전월 대비" 서사 틀과 맞지 않는 전용 문장이 필요하기 때문 — 의도적 설계, 주석으로 명시).
8. `app/services/reports.py`의 `create_report_draft`에 별도 루프 추가: `metric_type='손익항목계획대비'`인 `anomaly_flag`마다 `pl_item_analysis`로 문장을 다시 만들어(팀+항목 라벨로 `get_pl_comparison` 재조회, 다른 F7 코멘트들이 `aggregated_result`를 result_id로 재조회하는 것과 같은 패턴) `report_item`에 저장한다.
9. `.docs/02_prd.md` F3 표에 8번째 기준 추가, CLAUDE.md 아키텍처 설명 갱신.

**범위 밖**:
- 매출액/수량/영업이익 항목은 이번 서술 대상이 아니다(F3의 기존 5개 기준이 이미 다룸).
- "국내"(전체 팀 합계) 단위 서술은 만들지 않는다 — 4개 실제 팀 단위로만 판정한다(팀별 보고 원칙과 일치).

## 방법·완료 기준

- 드릴다운 필터가 걸린 상태로 `GET /pl-comparison`을 호출하면 `plan_comparison_available=false`와 함께 `diff_unit`/`diff_total`/`change_rate`가 모두 null로 온다. 팀 필터만 있거나 필터가 전혀 없으면 `true`.
- 실제 배치에서 재료비/노무비 등 항목이 팀 계획 대비 ±10% 이상 벗어나면 `anomaly_flag`에 `손익항목계획대비` 유형으로 잡히고, F7 초안에 해당 팀 섹션 아래 문장이 포함된다(금칙어 없음).
- 백엔드 전체 pytest, 프론트 lint·build·vitest 통과.

## 완료 보고

- 백엔드 전체 pytest 196개(신규 15개 포함: `test_pl_comparison.py` 2건, `test_pl_item_analysis.py` 6건, `test_anomaly.py` 3건, `test_reports_api.py` 1건, 기존 임계치 개수 테스트 갱신) 전부 통과. 프론트 lint·build(타입체크 포함)·vitest(17개) 전부 통과.
- 실제 로컬 DuckDB(2026-08 배치)에 재계산 실행 후 `GET /batches/{id}/anomalies`로 손익항목계획대비 플래그가 팀×계정과목 라벨(`product_group` 칸에 "매출원가"/"재료비 계" 등 재사용) 단위로 다수 생성됨을 확인했다. `GET /pl-comparison`에 드릴다운 필터를 추가하면 `plan_comparison_available`이 `true`→`false`로 바뀌는 것도 실제 API 호출로 확인했다.
- `POST /reports`로 F7 초안을 생성해 실제 문장을 확인했다 — 예: "고정형 매출원가는 단위당 계획 60,165원 대비 실적 91,785원으로 31,620원 상승했습니다. 총액 기준으로는 계획 7,523,000,000원 대비 실적 11,833,952,870원으로 4,310,952,870원(+57.3%) 증가했습니다. 매출액 대비 비중은 계획 72.0%에서 실적 79.8%로 +7.8%p 높아졌습니다." `report_item` 개수(118)가 `anomaly_flag` 개수(118)와 정확히 1:1로 일치함을 확인했다(기존 invariant 유지).

## 추가 확인(사용자 후속 요청) — 서술 대상 항목을 15개로 명시적 한정

- 사용자 원문: "이상징후 하이라이트에서는 손익항목 계획대비는 원재료비 계, 주재료비 계, 부재료비, 기타재료비 계, 직접노무비 계, 간접노무비, 변동경비, 고정경비, 외주가공비, 기타(상품구매, 재고실사차이 등), 변동판관비 계, 고정판관비 계, 매출원가, 판관비 계, 단위당 매출액 으로 항목 한정."
- `pl_item_analysis.PL_NARRATIVE_ITEM_KEYS`를 "비용·원가성 항목 전체 자동 도출" 방식에서 위 15개 키만 담은 explicit set으로 교체했다(재료비 계/노무비 계/경비 계/총원가 등 상위 소계는 제외).
- "단위당 매출액"은 유일하게 매출/수량/이익 계열 항목이 포함된 경우라, 매출액 총액이 아니라 **단위당(매출액÷매출수량) 기준으로만** 판정·서술하도록 예외 처리했다(총액은 F3의 다른 4개 기준이 이미 다루므로 중복 방지). `_metric_pct()`가 이 분기를 담당하고, `format_pl_item_comment()`도 이 항목만 단위당 문장 하나로 끝낸다(총액/비중 문장 생략).
- 테스트: `test_pl_item_analysis.py`에 명시적 15개 키 검증 + "단위당 매출액" 전용 판정/문장/수량계획 없을 때 미판정 3건 추가. 기존 `test_anomaly.py`/`test_reports_api.py`의 단순 fixture(재료비/노무비/경비 소계를 채우지 않음)에서는 "기타(상품구매,재고실사차이 등)"이 매출원가와 우연히 같은 값이 되어 함께 플래그되는 것을 확인, 검증을 `product_group="매출원가"`로 좁혀 회귀를 막았다. 백엔드 전체 203개 통과.

## 추가 확인(사용자 후속 버그 리포트) — F5 화면에 계획/실적이 전부 "0.0억"으로 보이던 버그

- 증상(사용자 확인 스크린샷): F5 이상징후 하이라이트에서 "손익항목계획대비" 항목들(매출원가/원재료비 계 등)이 전부 "계획 0.0억 대비 실적 0.0억으로 0.0억 증가했습니다"로 보이는데, 영향 금액(우측)은 -27.4억처럼 정상적인 큰 값이었다.
- 원인: `app/services/analytics.py`의 `_before_after_for_flag()`가 `dev.plan_unit is not None`이면 무조건 단위당 값(plan_unit/actual_unit)을 반환했는데, `plan_unit`은 팀의 계획 매출수량이 업로드돼 있으면 **"단위당 매출액"이 아닌 다른 14개 항목에서도 항상 채워진다**(모든 항목이 같은 팀 계획수량으로 나눠지므로). 그래서 매출원가처럼 총액이 수백억인 항목도 "총액÷팀 계획수량"이라는 작은 단가(예: 5,000원)로 뒤바뀌어 `formatEok`가 "0.0억"으로 표시했다.
- 수정: `pl_item_analysis._UNIT_BASIS_KEYS`를 공개(`UNIT_BASIS_KEYS`)로 바꿔, `_before_after_for_flag`가 `dev.key in UNIT_BASIS_KEYS`(=sales_final)일 때만 단위당 값을 쓰도록 조건을 추가했다.
- 회귀 테스트: 기존 `test_before_after_for_pl_item_plan_uses_unit_price_for_sales_and_total_for_cost`에 팀 계획 매출수량("매출수량" 계획 행)을 추가해야 이 버그가 실제로 재현됨을 확인(계획 매출수량이 없으면 우연히 버그가 드러나지 않아 기존 테스트가 놓치고 있었다) — Edit 도구로 되돌려 테스트가 실패함을 확인한 뒤 복구. 실제 배치로도 매출원가 계획/실적이 169.0억/141.6억으로 정상 표시됨을 확인했다.
