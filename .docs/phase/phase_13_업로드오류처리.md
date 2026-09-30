# Phase 13 작업 계획서 — 업로드(연동) 실패 시 원인을 화면에 표시

- 근거: 사용자 요청(원문) — "연동이 실패했을 때(파일이 없거나, 형식이 다르거나) 웹앱이 죽지 않고 '어떤 이유로 연동이 안 됐는지'를 화면에 보여주도록 만들어줘."

## 배경/동기

이번 세션 전체에서 반복적으로 겪은 패턴: 실제 파일 구조가 예상과 달라(부문/손익센터 컬럼 차이, 지점코드/업체코드 시트명 차이, 헤더가 2행에 걸친 구조 등) 사용자가 "알 수 없는 오류"만 보고 원인을 알 수 없었던 사례가 여러 번 있었다(CLAUDE.md에 각각 기록됨). 그때마다 새 케이스를 하나씩 찾아 특정 예외 처리를 추가해왔지만(`RawColumnValidationError`, `MappingValidationError`, `PlanValidationError`, `TeamPLValidationError`, `BranchValidationError` 등), **아직 예상하지 못한 새로운 파일 구조**가 들어오면 여전히 어디에도 잡히지 않는 예외가 발생해 FastAPI 기본 처리("Internal Server Error", 원인 불명)로 이어질 수 있다.

또한 Day 5에 실제로 겪은 사례(F7 동시 요청 버그)에서 확인했듯, 처리되지 않은 예외는 CORS 미들웨어 응답 경로를 타면서 브라우저에 "CORS policy에 의해 차단됨"으로 나타나 원인 추적이 더 어려워지는 문제도 있다.

## 범위

**구현**:
1. `app/main.py`에 전역 예외 핸들러(`@app.exception_handler(Exception)`)를 추가해, 어디서도 잡히지 않은 예외가 발생해도 항상 CORS 헤더가 포함된 JSON 응답(`{"detail": "..."}`)으로 원인을 내려준다 — 프론트가 이미 `detail` 필드를 읽어 화면에 표시하는 경로(`lib/api.ts`의 `request()`)를 그대로 탄다. 서버 콘솔에도 전체 트레이스백을 로그로 남긴다(디버깅용, 사용자에게는 노출하지 않음).
2. 기존에 "이미 알려진 실패 유형"만 잡던 두 지점을 원본 파일이 아예 열리지 않는 경우(형식이 다르거나 손상된 파일)까지 잡도록 넓힌다 — `plan.py`/`team_pl.py`가 이미 쓰고 있는 "workbook 열기 자체를 try/except로 감싸 사용자 메시지로 변환" 패턴을 그대로 따른다:
   - `app/services/mapping.py`의 `parse_mapping_upload` — `pd.ExcelFile`/`.parse()` 실패를 잡아 `MappingValidationError`로 변환.
   - `app/services/validation.py`의 `read_dataframe`(실적 파일) — `pd.read_csv`/`pd.read_excel` 실패를 잡아 신규 `FileParseError`로 변환, `app/routers/uploads.py`가 이를 파일명과 함께 400으로 응답.
3. 프론트는 이미 `ApiError.message`를 화면에 그대로 보여주고 있어(F1 업로드 화면의 붉은 오류 박스) 추가 UI 작업은 필요 없다 — 단, 백엔드가 새로 내려주는 메시지가 실제로 그 박스에 보이는지 실제 업로드로 확인한다.

**범위 밖(이번에 하지 않음)**:
- `refine_actual_records`의 행 단위 예외(이미 `is_calc_error`로 흡수하는 기존 패턴) 재설계 — 이미 충분히 견고하다고 판단.
- 네트워크 자체 단절(백엔드 프로세스 다운) 시 프론트 메시지 문구 개선 — 요청 범위(파일 연동 실패)와 다른 별개 사안이라 이번엔 다루지 않는다.

## 방법

1. `main.py`: `from fastapi.responses import JSONResponse`, `import logging, traceback` 추가 후 전역 핸들러 등록.
2. `mapping.py`: `parse_mapping_upload`의 워크북 열기 부분을 try/except로 감싼다.
3. `validation.py`: `FileParseError(ValueError)` 클래스 추가, `read_dataframe`의 판다스 호출부를 try/except로 감싼다.
4. `uploads.py`: 실적/매핑표 로딩 지점의 except 튜플에 `FileParseError` 추가.
5. 테스트: 전역 핸들러 회귀 테스트(임시 라우트로 고의 예외 유발 또는 실제 손상 파일 업로드), 손상된 xlsx/mapping 파일 업로드 시 400 + 명확한 메시지 회귀 테스트.

## 완료 기준

- 확장자는 맞지만 내용이 손상된 파일(예: 텍스트를 xlsx로 이름만 바꾼 경우)을 업로드해도 서버가 500 크래시 없이 400 + 원인 메시지를 반환하고, 프론트 화면에 그 메시지가 표시된다.
- 어디서도 예상하지 못한 예외가 나도(전역 핸들러 테스트로 검증) 브라우저에 "CORS 오류"가 아니라 실제 원인 메시지가 보인다.
- 백엔드 전체 pytest 통과.
