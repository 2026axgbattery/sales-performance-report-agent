"""F7 화면이 여러 팀의 추이를 Promise.all로 동시에 요청하면서 실제로 겪은 버그의
회귀 테스트. DuckDB Connection은 스레드 세이프하지 않아, 동시 요청이 같은
커넥션에서 쿼리를 인터리빙하면 서로의 결과 행이 섞인다(app/main.py의
serialize_db_access 미들웨어로 해결). TestClient는 기본적으로 순차 실행되므로,
실제 스레드로 동시에 요청을 보내야 이 문제가 재현/검증된다.
"""
from concurrent.futures import ThreadPoolExecutor

from tests.conftest import FIXTURES_DIR


def _upload(client, filenames_and_types, mime="text/csv"):
    files = [
        ("files", (name, open(FIXTURES_DIR / name, "rb"), mime))
        for name, _ in filenames_and_types
    ]
    data = {"file_types": [ftype for _, ftype in filenames_and_types]}
    return client.post("/uploads", files=files, data=data)


def _seed_three_months(client):
    r1 = _upload(client, [("actual_prev_year.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    assert r1.status_code == 200, r1.text
    r2 = _upload(client, [("actual_prev_month.csv", "실적")])
    assert r2.status_code == 200, r2.text
    r3 = _upload(client, [("actual_sample.csv", "실적"), ("plan_sample.xlsx", "계획")])
    assert r3.status_code == 200, r3.text
    return r3.json()["batch_id"]


def test_concurrent_trend_requests_do_not_corrupt_each_others_results(client):
    batch_id = _seed_three_months(client)

    def fetch(team):
        return client.get(f"/batches/{batch_id}/trend", params={"team": team})

    teams = ["차량대리점", "모티브"] * 10  # 반복해서 경쟁 창(race window)을 여러 번 노출시킨다
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(fetch, teams))

    for team, response in zip(teams, responses):
        assert response.status_code == 200, f"{team}: {response.status_code} {response.text}"
        body = response.json()
        assert body["team"] == team
        assert len(body["months"]) == 12
