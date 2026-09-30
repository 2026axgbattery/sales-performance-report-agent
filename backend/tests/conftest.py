from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import Database, get_db
from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def test_db():
    db = Database(":memory:")
    yield db
    db.close()


@pytest.fixture()
def client(test_db):
    app.dependency_overrides[get_db] = lambda: test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def open_fixture(name: str):
    return open(FIXTURES_DIR / name, "rb")
