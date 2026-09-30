import asyncio
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fastapi.middleware.cors import CORSMiddleware

from app.routers import analytics, exports, reports, thresholds, uploads

app = FastAPI(title="영업실적·손익 분석 및 보고서 자동 생성 Agent API")

logger = logging.getLogger("app")


# 파일 업로드(F1) 등에서 예상 못한 파일 구조를 만나면(.docs/phase/phase_13_업로드오류처리.md
# 참고) 각 서비스 모듈이 최대한 구체적인 사용자 메시지로 미리 변환하지만, 그래도 어디서도
# 잡히지 않는 예외가 생길 수 있다. FastAPI 기본 처리("Internal Server Error", 원인 불명)로
# 새어나가면 사용자가 원인을 전혀 알 수 없다.
#
# 이걸 `@app.exception_handler(Exception)`으로 등록하지 않는다 — Starlette는 상태코드
# 500이나 bare Exception용 핸들러를 등록하면 ExceptionMiddleware가 아니라 가장 바깥쪽인
# ServerErrorMiddleware로 옮겨버린다. ServerErrorMiddleware는 CORSMiddleware보다도 바깥에
# 있어서, 그렇게 등록한 핸들러가 만든 응답에는 CORS 헤더가 붙지 않는다 — 결국 브라우저에는
# 실제 오류 대신 "CORS policy에 의해 차단됨"으로 나타난다(Day 5에서 실제로 겪은 증상과 같은
# 근본 원인). 대신 평범한 HTTP 미들웨어로 만들어 CORSMiddleware보다 안쪽(더 먼저 등록)에
# 두면, 이 미들웨어가 만든 응답도 CORSMiddleware를 정상적으로 통과해 헤더가 붙는다.
@app.middleware("http")
async def handle_unexpected_exception(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001 — 의도적으로 모든 예외를 잡는 마지막 안전망
        logger.error("처리되지 않은 예외: %s %s\n%s", request.method, request.url.path, traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"서버에서 예상하지 못한 오류가 발생했습니다 ({type(exc).__name__}: {exc}). "
                "파일 형식이나 구조가 예상과 다를 수 있습니다."
            },
        )


# get_db()가 프로세스 전역으로 공유하는 duckdb.Connection 하나를 반환하는데, DuckDB
# Connection은 스레드 세이프하지 않다. FastAPI는 동기 라우트를 스레드풀에서 실행하므로,
# F7 보고서 화면처럼 여러 GET 요청을 동시에(Promise.all) 보내면 두 스레드가 같은
# 커넥션에서 쿼리를 인터리빙하며 서로의 결과 행을 오염시킨다(실제로 겪은 증상:
# get_trend에서 "not enough values to unpack" — 다른 요청의 결과가 섞여 들어옴).
# 로컬 1인 사용자 도구이므로 요청을 완전히 직렬화하는 것으로 근본 해결한다.
_db_lock = asyncio.Lock()


@app.middleware("http")
async def serialize_db_access(request: Request, call_next):
    async with _db_lock:
        return await call_next(request)


# CORSMiddleware는 반드시 마지막(=가장 바깥쪽)에 등록한다 — 위 두 미들웨어가 만드는
# 응답(정상/에러 모두)이 전부 이 미들웨어를 통과해야 CORS 헤더가 붙는다.
# MVP는 로컬에서 Next.js(3000, 포트 충돌 시 3100)와 FastAPI(8000)를 별도 프로세스로 띄워 데모한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3100"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads.router)
app.include_router(thresholds.router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(exports.router)


@app.get("/health")
def health():
    return {"status": "ok"}
