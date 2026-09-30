"""전역 예외 핸들러(app/main.py) 회귀 테스트 — .docs/phase/phase_13_업로드오류처리.md.

어디서도 잡히지 않는 예외가 나도 서버가 크래시하거나 원인 불명의 빈 500을 주지 않고,
CORS 헤더가 붙은 정상 JSON 응답으로 원인을 내려주는지 확인한다. 이미 알려진 실패
유형(파일 형식 오류 등)은 각 서비스 모듈이 더 구체적인 메시지로 미리 잡아내므로,
여기서는 "그 어떤 서비스 코드도 예상하지 못한 예외"를 흉내내기 위해 F3 집계 단계를
몽키패치로 실패시킨다.
"""
from tests.conftest import FIXTURES_DIR


def test_unhandled_exception_returns_structured_500_with_reason(client, monkeypatch):
    def _boom(db, batch_id):
        raise RuntimeError("정말 예상하지 못한 내부 오류")

    monkeypatch.setattr("app.routers.uploads.compute_aggregates_for_batch", _boom)

    files = [
        ("files", ("actual_sample.csv", open(FIXTURES_DIR / "actual_sample.csv", "rb"), "text/csv")),
        ("files", ("mapping_sample.csv", open(FIXTURES_DIR / "mapping_sample.csv", "rb"), "text/csv")),
    ]
    data = {"file_types": ["실적", "매핑표"]}
    # 프론트(app/globals.css 기준 :3000/:3100)가 보내는 것과 동일하게 Origin 헤더를 실어,
    # CORS 미들웨어를 실제로 거치는 경로로 요청한다.
    response = client.post(
        "/uploads", files=files, data=data, headers={"Origin": "http://localhost:3100"}
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "RuntimeError" in detail
    assert "정말 예상하지 못한 내부 오류" in detail
    # 처리되지 않은 예외가 CORS 헤더 없이 새어나가 브라우저에 "CORS policy에 의해
    # 차단됨"으로 나타났던 Day 5 증상의 회귀 테스트 — 예외 핸들러의 응답도 CORS
    # 미들웨어를 정상적으로 통과해 이 헤더가 붙어야 한다.
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3100"
