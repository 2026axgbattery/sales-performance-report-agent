"""Day 2 종단 테스트: 여러 달치 업로드 -> F3 이상징후 자동 계산 -> F6 임계치 변경 후 재계산."""
from tests.conftest import FIXTURES_DIR


def _upload(client, filenames_and_types, mime="text/csv"):
    files = [
        ("files", (name, open(FIXTURES_DIR / name, "rb"), mime))
        for name, _ in filenames_and_types
    ]
    data = {"file_types": [ftype for _, ftype in filenames_and_types]}
    return client.post("/uploads", files=files, data=data)


def _flags(test_db, batch_id):
    rows = test_db.connection.execute(
        "SELECT team, product_group, metric_type FROM anomaly_flag WHERE batch_id = ?",
        [batch_id],
    ).fetchall()
    return {(r[0], r[1], r[2]) for r in rows}


def test_multi_month_upload_produces_expected_anomaly_flags(client, test_db):
    # 2025-07 (전년 동월 기준 데이터)
    r1 = _upload(client, [("actual_prev_year.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    assert r1.status_code == 200, r1.text

    # 2026-06 (전월 기준 데이터)
    r2 = _upload(client, [("actual_prev_month.csv", "실적")])
    assert r2.status_code == 200, r2.text

    # 2026-07 (당월, 계획 포함)
    r3 = _upload(client, [("actual_sample.csv", "실적"), ("plan_sample.xlsx", "계획")])
    assert r3.status_code == 200, r3.text
    body = r3.json()
    batch_id = body["batch_id"]
    assert body["anomaly_count"] > 0

    flags = _flags(test_db, batch_id)

    assert ("차량대리점", "GB 소형", "전월대비") in flags  # 60만 -> 71.8만, +19.6%
    assert ("차량대리점", "GB 소형", "전년대비") in flags  # 50만 -> 71.8만, +43.6%
    # Phase 17부터 계획대비는 팀 단위로만 판정한다(product_group=None="팀 전체") — 목표 90만 대비 79.8% 달성
    assert ("차량대리점", None, "계획대비") in flags

    # 모티브는 계획 대비 100% 정확히 달성 -> 계획대비 플래그 없음
    assert ("모티브", None, "계획대비") not in flags
    # 모티브는 전월 대비 변화가 작아(-2%) 플래그 없음
    assert ("모티브", "원자재", "전월대비") not in flags
    # 모티브는 전년 동월 데이터가 없어 "비교 불가" -> 플래그 없음(스킵)
    assert ("모티브", "원자재", "전년대비") not in flags


def test_threshold_change_and_recompute_changes_flags(client, test_db):
    r1 = _upload(client, [("actual_prev_year.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    assert r1.status_code == 200, r1.text
    r2 = _upload(client, [("actual_prev_month.csv", "실적")])
    assert r2.status_code == 200, r2.text
    r3 = _upload(client, [("actual_sample.csv", "실적"), ("plan_sample.xlsx", "계획")])
    assert r3.status_code == 200, r3.text
    batch_id = r3.json()["batch_id"]

    assert ("차량대리점", "GB 소형", "전월대비") in _flags(test_db, batch_id)

    # F6: 전월대비 임계치를 크게 완화
    put_resp = client.put(
        "/thresholds", json={"updates": [{"metric_type": "전월대비", "threshold_value": 1000}]}
    )
    assert put_resp.status_code == 200, put_resp.text

    # 재업로드 없이 재계산만 트리거 (F6 화면에서 저장 직후 호출하는 것과 동일한 API)
    recompute_resp = client.post(f"/batches/{batch_id}/recompute")
    assert recompute_resp.status_code == 200, recompute_resp.text

    assert ("차량대리점", "GB 소형", "전월대비") not in _flags(test_db, batch_id)
    # 임계치를 건드리지 않은 다른 기준(전년대비)은 그대로 유지되어야 한다
    assert ("차량대리점", "GB 소형", "전년대비") in _flags(test_db, batch_id)
