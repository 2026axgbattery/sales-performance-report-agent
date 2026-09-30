# Phase 26 — 데모용 백엔드 외부 배포 (Render)

## 배경 / 동기

프론트엔드를 Vercel에 배포하려면 `NEXT_PUBLIC_API_BASE_URL`에 인터넷에서 접속되는 https 백엔드 주소가 필요하다.
백엔드는 지금까지 로컬(`127.0.0.1:8000`)에서만 돌았다. 사용자 선택: "B로 진행" — 무료 호스팅(Render)에
**더미 데이터만 담은 데모용 백엔드**를 올려 고정 주소(`https://<이름>.onrender.com`)를 얻는다.
(Cloudflare 고정 터널은 계정에 도메인이 없어 불가, 임시 터널은 주소가 매번 바뀜.)

## 범위

- 포함
  - `app/db.py` — `get_db()`가 환경변수 `APP_DB_PATH`가 있으면 그 경로의 DB를 쓴다(없으면 기존 `backend/data/app.duckdb` 그대로)
  - `app/main.py` — CORS 허용 주소를 환경변수로 추가할 수 있게 한다
    (`CORS_ALLOW_ORIGINS`: 쉼표 구분 목록, `CORS_ALLOW_ORIGIN_REGEX`: Vercel 미리보기 주소처럼 바뀌는 주소용 정규식).
    기본값(localhost:3000/3100)은 유지
  - 신규 `backend/scripts/seed_demo.py` — 가상 합성 실적(가공 거래처·제품, 1~8월) + 더미 판매계획을 앱의 업로드 API로
    넣는다. 이미 배치가 있으면 건너뛴다(재시작마다 중복 방지). **`APP_DB_PATH`가 없으면 실행을 거부**해 실제 데이터가 든
    로컬 DB에 가상 데이터가 섞이는 사고를 막는다
  - `backend/demo_data/판매계획_더미데이터.xlsx` — 루트의 더미 파일 복사본(Render가 `backend/`만 기준으로 빌드해도 쓸 수 있게)
  - 저장소 루트 `render.yaml` — Render 무료 웹 서비스 설정(빌드/시작 명령, 헬스체크, 환경변수)
  - 테스트: 환경변수별 CORS 설정, `APP_DB_PATH` 반영, 시드 스크립트(배치 8개 생성·재실행 시 중복 없음·경로 없으면 거부)
- 제외
  - 실제 운영 데이터 업로드(데모 백엔드에는 가상 데이터만)
  - 다중 월 업로드 시 계획 저장 순서 버그 수정(Phase 23에서 발견, 사용자 결정 대기) — 시드 스크립트는 업로드 후 배치별 재계산으로 우회
  - PDF 한글 폰트: 현재 Windows 내장 맑은 고딕에 의존하므로 Linux(Render)에서는 PDF 한글이 깨질 수 있음 → 남은 문제로 기록

## 방법

- Render 무료 플랜은 재시작 시 디스크가 초기화되므로, 시작 명령에서 시드 → uvicorn 순으로 실행해 매번 데모 데이터를 다시 채운다
  (`APP_DB_PATH=/tmp/demo.duckdb`)
- 시드는 `fastapi.testclient.TestClient`로 앱 자신의 `POST /uploads`를 호출해, 실제 업로드와 같은 정제·집계·판정 경로를 탄다

## 완료 기준

- 백엔드 pytest 전체 통과(기존 216개 + 신규)
- 로컬에서 `APP_DB_PATH`를 임시 경로로 두고 시드 → uvicorn 기동 → `/health`·`/batches` 응답 확인
- 사용자가 Render에서 서비스를 만든 뒤 받은 주소를 Vercel `NEXT_PUBLIC_API_BASE_URL`에 넣을 수 있게 안내

## 완료 보고

- 변경: `app/db.py`(`APP_DB_PATH`), `app/main.py`(`cors_settings()` — `CORS_ALLOW_ORIGINS`/`CORS_ALLOW_ORIGIN_REGEX`),
  신규 `scripts/seed_demo.py`·`scripts/__init__.py`·`demo_data/판매계획_더미데이터.xlsx`, 루트 `render.yaml`
- 테스트: 신규 `tests/test_deploy_config.py` 6개(기본 CORS, 환경변수 CORS, `APP_DB_PATH` 반영, 경로 없으면 시드 거부,
  시드 데이터에 템플릿 거래처명 미포함, 8개월 생성 + 당월 목표 채움 + 재실행 시 중복 없음). 백엔드 전체 222개 통과
- 로컬 모의 실행(Render 시작 명령과 동일): 시드 1회차 배치 8개 생성 → 2회차 건너뜀 → uvicorn `/health` 정상,
  `/batches` 8개. CORS는 Vercel 운영·미리보기 주소만 허용하고 그 외 origin은 차단됨을 확인
- 남은 일(사용자): Render에서 저장소 연결 → 서비스 생성 → 받은 주소를 Vercel `NEXT_PUBLIC_API_BASE_URL`에 입력
- 남은 문제: PDF 한글 폰트(맑은 고딕)가 Linux에 없어 Render에서 PDF 다운로드 시 한글이 깨질 수 있음, 무료 플랜 절전(첫 요청 지연)
