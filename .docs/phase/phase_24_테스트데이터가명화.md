# Phase 24 — 공개 저장소 내 실제 거래처명 가명화

## 배경 / 동기

Phase 23 작업 중, 이미 공개 저장소에 올라간 테스트 fixture(`backend/tests/fixtures/actual_sample.csv` 등)와 문서에
실제 거래처명이 남아 있는 것을 발견했다. 사용자 요청: "가명으로 바꾸어주세요".

## 범위

- 치환 대상(이름만): 거래처명 6종 + 제품명 속 고객 표기 1종 → 가명
  (가명: 가나자동차 주식회사(GN Motors …), (주)샘플전지대전점, (주)샘플배터리부산, (주)예시글로벌, GB 400R(GN))
- **실명↔가명 대응표는 공개 저장소에 두지 않는다** — 로컬 전용 `.docs/private/가명화_매핑표.md`에만 보관(`.gitignore` 제외)
- 대상 파일
  - 텍스트: 테스트 CSV fixture 5개, `test_identifiers.py`, `test_pdf_export.py`, `pdf_export.py` 주석, `CLAUDE.md`,
    `.docs/03_데이터정제.md`, `output/f4-overview.html`
  - 바이너리: `actual_sample.xlsb`(Excel COM으로 셀 치환 후 같은 형식으로 저장), `actual_sample_header_row2.xlsx`,
    `mapping_with_branch.xlsx`, `mapping_with_upche_code.xlsx`(openpyxl 셀 치환)
  - 백업 압축본 `.docs.zip`, `.docs/김영우_docs.zip` — 과거 버전 문서라 실명이 그대로 들어 있고 현재 `.docs/`와 중복이므로
    저장소 추적에서만 제외(`git rm --cached` + `.gitignore`), 로컬 파일은 삭제하지 않는다
- 제외
  - 제품코드(PCC01179 등)·거래처코드(210111x 등): 다수의 테스트 단언과 `.docs/03_데이터정제.md`의 엑셀 검증 행이
    참조하는 식별자이고 이름이 아니므로 유지
  - 금액 값: 정제 로직 회귀 기준값(실제 엑셀 결과와 대조)이므로 유지
  - git 이력 정리(과거 커밋에 남은 실명 제거): 강제 push가 필요한 파괴적 작업이라 사용자 확인 후 별도 진행

## 방법

- 긴 문자열부터 순서대로 치환(부분 문자열 충돌 방지). 원본의 "잘린 거래처명" 특성(닫는 괄호 없음)은 테스트 의도라 유지
- 치환 후 저장소 전체(텍스트 + xlsx/xlsb 내부 + 압축본 제외 확인)를 실명 키워드로 재스캔해 0건 확인

## 완료 기준

- 실명 키워드 재스캔 0건 (node_modules 등 외부 패키지 제외)
- 백엔드 pytest 전체 통과(216개), 프론트 lint·build·test 통과

## 완료 보고

- 치환 완료: 텍스트 14개 파일(계획 외로 재스캔에서 추가 발견된 `mapping_sample.csv`·`mapping_duplicate_key.csv`·
  `test_branch.py` 포함), xlsx fixture 3개(openpyxl 셀 치환), `actual_sample.xlsb`(Excel COM `Range.Replace` 후 같은 형식 저장)
- 백업 압축본 2개는 `git rm --cached` + `.gitignore`로 추적 해제(로컬 파일은 그대로)
- 재스캔: git 추적 파일 174개 전체(텍스트, xlsx/xlsb 내부 포함)에서 실명 키워드 0건
- 점검: 백엔드 pytest 216개 통과. 프론트 코드는 변경 없음(목업 HTML만 수정)이라 lint·build는 생략
- 남은 일: 과거 커밋 이력에는 실명이 그대로 남아 있음 — 이력 재작성 + 강제 push 여부는 사용자 확인 필요
