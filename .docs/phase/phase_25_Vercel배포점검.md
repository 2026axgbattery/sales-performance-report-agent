# Phase 25 — Vercel 배포 전 프론트엔드 점검

## 배경 / 동기

사용자 요청: `frontend/`(Next.js)를 Vercel에 배포하기 전에 점검. 개발 PC는 Windows(파일 시스템이 대소문자를 구분하지 않음)이고
Vercel 빌드 서버는 Linux(구분함)라, 로컬에서만 통과하는 문제를 미리 찾는다.

## 범위

1. `npm run build` 프로덕션 빌드 성공 여부 — 실패 시 원인 한 줄 + 수정
2. import 경로 대소문자와 실제 파일명 일치 여부(`@/` 별칭·상대 경로·`public/` 정적 자산 참조 포함, git에 기록된 파일명 기준도 함께 확인)
3. 사용 중인 환경변수 키 목록(값은 출력하지 않음)
4. `.env*` 파일이 git에 커밋되지 않았는지
5. 결과를 통과 / 고친 것 / 남은 문제로 정리

## 방법

- 대소문자 점검은 스크립트로 모든 `.ts/.tsx/.mjs` 파일의 import를 해석해, 경로의 각 단계를 `readdir` 결과와 **정확히** 비교한다
  (Windows에서 `existsSync`는 대소문자가 달라도 참이라 쓸 수 없다). git이 기억하는 파일명(`git ls-files`)과 디스크 파일명도 비교한다
  (Windows에서 파일명 대소문자만 바꾸면 git에 반영되지 않는 경우가 있음).
- 환경변수는 코드의 `process.env.*` 사용처와 `.env*` 파일의 키 이름만 추출한다(`=` 뒤는 잘라낸다).

## 완료 기준

- 1~4 항목 각각 결과 확인, 발견한 문제는 수정 또는 "남은 문제"로 명시

## 완료 보고

- 빌드: `next build` exit 0, 오류·경고 없음, 7개 라우트 전부 정적 생성
- 대소문자: import·정적 자산 참조 44개 + git 추적 파일 42개 모두 일치. 점검 스크립트가 실제로 불일치를 잡는지
  일부러 틀린 샘플(`@/components/topnav`, `/Logo.png`)로 검증함
- 환경변수: 코드에서 쓰는 키는 `NEXT_PUBLIC_API_BASE_URL` 1개(`frontend/.env.local`에만 정의)
- `.env*`: 현재 커밋 없음, 과거 이력에도 없음, `frontend/.gitignore`의 `.env*` 규칙으로 무시됨
- 고친 것: 없음
- 남은 문제(코드 문제가 아니라 배포 구성·정책 결정 사항)
  - Vercel 프로젝트의 Root Directory를 `frontend`로 지정해야 함(저장소 루트에 package.json 없음)
  - `NEXT_PUBLIC_API_BASE_URL` 미설정 시 기본값 `http://127.0.0.1:8000`으로 빌드되어 접속자 PC의 localhost를 호출함.
    빌드 시점에 값이 박히므로 Vercel 환경변수에 넣은 뒤 재배포 필요
  - 백엔드(FastAPI+DuckDB)는 Vercel에 함께 올라가지 않음 → 별도 호스팅 필요, CORS `allow_origins`가 localhost만 허용,
    https 페이지에서 http 백엔드 호출은 브라우저가 차단(mixed content)
  - 정책: PRD의 "김영우 책임 1인 전용"·"로컬 데모가 완료 기준"(NG6)·다중 사용자 권한 제외(NG1)와 충돌 — 로그인 없이
    인터넷에 공개되면 실적 데이터가 노출될 수 있음
