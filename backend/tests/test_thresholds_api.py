def test_get_thresholds_returns_seven_criteria(client):
    # Phase 18에서 "손익항목계획대비"가 7번째로 추가됐다(.docs/phase/
    # phase_18_손익항목계획대비판정.md, 사용자 확인). Phase 17에서 신설했던
    # "누계평균대비"는 Phase 20에서 폐지되고 "단가변동"에 흡수됐다(.docs/phase/
    # phase_20_단가변동누계평균통합.md).
    response = client.get("/thresholds")
    assert response.status_code == 200
    thresholds = response.json()["thresholds"]
    assert len(thresholds) == 7
    metric_types = {t["metric_type"] for t in thresholds}
    assert metric_types == {
        "전월대비", "전년대비", "계획대비", "흑자전환", "단가변동", "판관비급증",
        "손익항목계획대비",
    }
    assert "누계평균대비" not in metric_types


def test_get_thresholds_removes_orphaned_metric_from_existing_db(client, test_db):
    # Phase 20에서 "누계평균대비"를 ALL_METRICS에서 뺐는데, 이미 그 기준을 시딩해둔
    # 기존 로컬 DB에는 고아 행으로 남아있을 수 있다 — seed_default_thresholds가
    # 조회 때마다 이런 행을 정리해야 한다(app/db.py의 COLUMN_MIGRATIONS와 같은 취지).
    import uuid

    test_db.connection.execute(
        "INSERT INTO threshold_config (config_id, metric_type, threshold_value, threshold_low, threshold_high, updated_at) "
        "VALUES (?, '누계평균대비', 15.0, NULL, NULL, '2026-01-01')",
        [str(uuid.uuid4())],
    )
    response = client.get("/thresholds")
    assert response.status_code == 200
    metric_types = {t["metric_type"] for t in response.json()["thresholds"]}
    assert "누계평균대비" not in metric_types
    assert len(metric_types) == 7


def test_put_thresholds_updates_value(client):
    response = client.put("/thresholds", json={"updates": [{"metric_type": "전월대비", "threshold_value": 25}]})
    assert response.status_code == 200, response.text
    updated = {t["metric_type"]: t for t in response.json()["thresholds"]}
    assert updated["전월대비"]["threshold_value"] == 25

    refetched = client.get("/thresholds").json()["thresholds"]
    refetched_map = {t["metric_type"]: t for t in refetched}
    assert refetched_map["전월대비"]["threshold_value"] == 25


def test_put_thresholds_rejects_unknown_metric(client):
    response = client.put("/thresholds", json={"updates": [{"metric_type": "없는기준", "threshold_value": 1}]})
    assert response.status_code == 400


def test_recompute_unknown_batch_returns_404(client):
    response = client.post("/batches/does-not-exist/recompute")
    assert response.status_code == 404
