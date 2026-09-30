"""Phase 26 — 외부 데모 배포 설정(DB 경로·CORS·시드) 회귀 테스트."""
import pytest
from fastapi.testclient import TestClient

import app.db as db_module
from app.db import Database, get_db
from app.main import app, cors_settings
from scripts import seed_demo


def test_cors_settings_defaults_to_localhost_only(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOW_ORIGIN_REGEX", raising=False)
    origins, regex = cors_settings()
    assert origins == ["http://localhost:3000", "http://localhost:3100"]
    assert regex is None


def test_cors_settings_adds_env_origins_and_regex(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", " https://a.vercel.app/ , https://b.example.com ")
    monkeypatch.setenv("CORS_ALLOW_ORIGIN_REGEX", r"^https://x[a-z0-9-]*\.vercel\.app$")
    origins, regex = cors_settings()
    assert origins[-2:] == ["https://a.vercel.app", "https://b.example.com"]
    assert regex == r"^https://x[a-z0-9-]*\.vercel\.app$"


def test_get_db_uses_app_db_path(monkeypatch, tmp_path):
    target = tmp_path / "demo.duckdb"
    monkeypatch.setenv("APP_DB_PATH", str(target))
    monkeypatch.setattr(db_module, "_default_db", None)
    try:
        db = get_db()
        assert db.path == str(target)
        assert target.exists()
    finally:
        db_module._default_db.close()
        monkeypatch.setattr(db_module, "_default_db", None)


def test_seed_demo_refuses_without_app_db_path(monkeypatch):
    monkeypatch.delenv("APP_DB_PATH", raising=False)
    assert seed_demo.main() == 1


def test_seed_demo_frames_contain_no_real_names():
    actual, mapping_df = seed_demo.build_demo_frames()
    assert len(actual) == 8 * 10 * 3  # 8개월 × 제품 10종 × 거래처 3곳
    text = actual.to_csv() + mapping_df.to_csv()
    for real_name in ("가나자동차", "샘플전지대전점"):  # 템플릿 행의 거래처명이 새어 나오지 않아야 함
        assert real_name not in text


@pytest.fixture
def demo_client():
    db = Database(":memory:")
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def test_seed_demo_creates_eight_months_with_plan_and_is_idempotent(demo_client):
    assert seed_demo.seed(demo_client) == 8
    batches = demo_client.get("/batches").json()["batches"]
    assert sorted((b["year"], b["month"]) for b in batches) == [(2026, m) for m in range(1, 9)]

    # 재계산 덕분에 당월 목표 매출액이 채워져 있어야 한다
    august = next(b for b in batches if b["month"] == 8)
    matrix = demo_client.get(f"/batches/{august['batch_id']}/overview").json()["team_matrix"]
    assert all(row["mtd"]["plan_amount"] for row in matrix)

    # 재시작(재실행) 시 중복 업로드하지 않는다
    assert seed_demo.seed(demo_client) == 0
    assert len(demo_client.get("/batches").json()["batches"]) == 8
