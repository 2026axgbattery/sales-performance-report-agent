# Phase 15 작업 계획서 — Overview PDF 카테고리 선택 다운로드 + F7 정제 데이터 전체 다운로드

- 근거: 사용자 요청(원문) — "overview에서 pdf 다운로드하면, 아래의 각 탭의 것도 내용이 담겨서 출력이 될수 있께 해줘. 대신 내가 다운로드하고 싶은 카테고리를 체크할수 있게 하면 좋겠네" / "f7의 다운로드 버튼을 하나 추가해줘. (raw와 맵핑을 거쳐 정제된 실적 Re-arrange용 수식 시트 전체, xlsx 양식)"

## 범위

**구현**:
1. `app/services/pdf_export.py` — 기존에는 "팀별 목표 대비 실적"(KPI+계획대비/전월대비 캡션+두 표) 한 섹션만 만들었다. 이걸 `team_matrix` 섹션으로 이름 붙이고, F4 아래 탭 4개에 대응하는 섹션 4개를 추가한다: `monthly_team`(월별 실적 분석-팀별), `monthly_product_group`(제품군별), `monthly_customer`(거래처별), `pl_comparison`(손익 상세 분석, 필터 없는 "국내" 전체 기준). `build_overview_pdf(db, batch_id, sections=None)`가 `sections`(생략 시 전체)에 포함된 섹션만 순서대로 그린다.
2. `GET /batches/{id}/export/overview`에 `sections` 쿼리 파라미터(다중 선택, 생략 시 전체) 추가.
3. 프론트: PDF 다운로드 버튼을 눌렀을 때 카테고리 체크박스(5개 섹션, 기본 전체 선택)를 보여주는 작은 드롭다운으로 바꾸고, 확정 시 선택된 섹션만 쿼리 파라미터로 담아 다운로드한다.
4. F7(보고서) 화면에 "실적 Re-arrange 전체 다운로드(xlsx)" 버튼 신규 추가 — `refined_sales_record`의 모든 컬럼(raw+매핑을 거쳐 정제된 결과, 컬럼명은 `.docs/03_데이터정제.md`/`refinement.py` 주석에서 실측한 이름 그대로)을 한 시트로 내려준다. 새 서비스 함수는 `app/services/refinement.py`에 새로 공개한 `REFINED_ROW_COLUMNS`(RefinedRow 필드 순서에서 도출 — 기존 `uploads.py`가 손으로 유지하던 목록을 여기로 옮겨 두 곳이 어긋나지 않게 함)를 그대로 재사용한다.

**범위 밖**:
- pl_comparison 섹션은 필터(고객/상품/제품구분 등) 없이 "국내" 전체 기준으로만 출력한다 — PDF는 정적 산출물이라 화면의 인터랙티브 드릴다운을 그대로 재현하지 않는다.
- 월별 실적 분석(팀별) PDF 표는 화면과 동일하게 팀×1~12월 전체를 나열한다(요약 행 포함) — 너무 길면 페이지가 여러 장으로 늘어나는 것은 허용한다(reportlab이 자동 페이지 분할).

## 방법

1. `pdf_export.py`: 섹션별 빌더 함수로 리팩터링, `SECTION_KEYS`/`SECTION_LABELS` 상수 추가.
2. `app/routers/exports.py`: `sections: Optional[list[str]] = Query(default=None)` 추가.
3. 프론트 `lib/api.ts`: `overviewExportUrl(batchId, sections?)` 시그니처 확장.
4. 프론트 신규 컴포넌트 `OverviewPdfDownloadButton.tsx` — 체크박스 드롭다운(기본 전체 선택) + 다운로드 링크, `app/overview/page.tsx`의 기존 `<a>` 자리를 대체.
5. 테스트: 섹션 선택에 따라 PDF 페이지/텍스트가 달라지는지 확인, `sections` 생략 시 기존처럼 전체 포함, F7 refined export 테스트.

## 완료 기준

- Overview PDF 다운로드에서 5개 섹션을 체크박스로 선택할 수 있고, 선택한 섹션만 PDF에 포함된다(기본은 전체 선택).
- F7에 실적 Re-arrange 전체(xlsx) 다운로드 버튼이 추가되고, 다운로드한 파일에 정제 컬럼 전체가 한글 라벨로 담겨 있다.
- 백엔드 전체 pytest, 프론트 lint·build·vitest 통과.
