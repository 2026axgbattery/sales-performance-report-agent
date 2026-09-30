# Phase 23 — 웹앱 디자인 개선 (README 대시보드 스타일 적용)

## 배경 / 동기

GitHub README를 세방 CI 색상 기반 대시보드 느낌(다크 배너, 좌측 컬러 띠 KPI 카드)으로 다시 디자인한 뒤,
사용자 요청: "해당 이미지 작업을 실제 우리 작업물에도 입혀야지?" — README에만 쓴 시각 언어를 실제 웹앱 화면에도
동일하게 적용한다. 직전 요청의 조건("앞에서 했던 전체적인 내용과 양식은 건드리지 않고")을 그대로 이어받아,
**화면의 문구·기능·표 구성·데이터 흐름은 바꾸지 않고 시각 스타일만** 바꾼다.

## 범위

- 포함
  - `components/TopNav.tsx` — 흰 헤더를 README 배너와 같은 다크(sebang-dark-gray 700→500) 헤더로 변경, 활성 메뉴는 오렌지 강조
  - 신규 `components/PageHeader.tsx` — 각 페이지 상단 제목/설명/우측 액션(배치 선택·다운로드)을 README 배너 스타일
    (다크 카드 + 격자 패턴 + 좌측 오렌지 띠)로 통일. 5개 페이지(F1/F4/F5/F6/F7)의 기존 제목 블록을 이 컴포넌트로 교체하되
    제목·설명 문구는 원문 그대로 전달
  - F4 KPI 요약 카드 — README 수치 카드(stats.svg)와 같은 좌측 컬러 띠 + 큰 숫자 형태
  - 섹션 카드 공통 — 페이지 배경을 sebang-dark-gray-50(`#EFF0F0`)으로 바꿔 카드와 대비를 주고,
    카드에 design.md가 허용한 저채도 그림자(`0 2px 8px rgba(51,63,72,0.12)` 계열) 적용
- 제외
  - 문구·표 컬럼·기능·API·데이터 계산 로직 변경 없음
  - 차트 종류/색상 규칙(이상징후 good/bad 색 기준 포함) 변경 없음

## 방법

- 색상·그림자·라운드는 전부 `.docs/design.md` 토큰과 규칙을 따른다
  - 그림자는 저채도 다크그레이만(§ Elevation), 라운드는 card 8px / large card 16px
  - 금지 사항 1: 한 화면에서 오렌지·그린을 동시에 "주 강조색"으로 쓰지 않는다 → 주 강조는 오렌지(활성 메뉴·헤더 띠),
    그린은 기존처럼 성공/상승 상태 표시에만 사용
- 신규 토큰은 `app/globals.css`의 `:root`에 design.md 확장 팔레트 값(dark-gray 50/600/700 등)으로만 추가
- 다크 헤더 위에 놓이는 기존 액션 요소(BatchPicker select, 다운로드 링크 등)는 컴포넌트 수정 없이
  `PageHeader` 액션 영역에서 흰 배경을 부여해 가독성을 확보

## 완료 기준

- 5개 페이지 모두 새 헤더/카드 스타일로 렌더링되고, 기존 문구·기능이 그대로 동작
- `npm run lint`, `npm run build`, `npm run test -- --run` 통과
- 실제 브라우저(dev 서버 + 백엔드)로 각 페이지를 열어 캡처 확인, `screenshots/` 갱신

## 완료 보고

- 변경 파일: `app/globals.css`, `app/layout.tsx`, `components/TopNav.tsx`, 신규 `components/PageHeader.tsx`,
  5개 페이지(`app/{upload,overview,anomalies,thresholds,reports}/page.tsx`), 월별 분석·손익 상세 패널 4개(카드 클래스만)
- 점검: `npm run lint` 통과, `npm run test -- --run` 19개 통과, `npm run build` 통과(타입 체크 포함)
- 브라우저 확인(Playwright + Edge): 5개 페이지 렌더링, PDF 카테고리 드롭다운이 헤더에 잘리지 않고 펼쳐짐,
  팀 행 클릭 시 추이 차트 표시, 보고서 초안 생성 동작, 콘솔 오류 0건
- 스크린샷: 로컬 DB(`backend/data/app.duckdb`)에 실제 운영 데이터가 들어 있어 그대로 캡처하면 공개 저장소에 실데이터가
  노출되므로 사용하지 않았다. 코드 변경 없이 별도 DuckDB 파일로 기동한 데모 백엔드(:8001)에 가상 합성 실적
  (가공 거래처·제품, 1~8월) + 기존 `판매계획_더미데이터.xlsx`만 올려 캡처했다.
- 부수 발견(미수정, 디자인 범위 밖): 다중 월 실적 업로드 시 계획 저장이 집계 이후에 실행되어 당월 목표 매출액·계획대비
  판정이 비어 있다가 재계산해야 채워진다(`app/routers/uploads.py` 집계 288행 → 계획 저장 321행 순서).

## 후속 변경 — 헤더 로고 교체

- 사용자 요청("EB를 두번째 이미지로 대체?")에 따라 `components/TopNav.tsx`의 "EB" 텍스트 박스를 ROCKET 엠블럼 이미지로 교체했다.
- 사용자가 준 사진에서 원형 엠블럼만 잘라 바깥(빨간 배경)을 투명하게 처리한 256px PNG를 `frontend/public/rocket-emblem.png`로 두고,
  `next/image`로 40px 크기로 표시한다. 점검: lint·vitest 19개·build 통과, 브라우저에서 이미지 로드 확인.
