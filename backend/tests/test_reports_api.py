import uuid

from tests.conftest import FIXTURES_DIR

FORBIDDEN_WORDS = ["때문", "원인", "인해", "탓"]


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


def test_create_report_draft_survives_comment_generation_failure_for_one_item(client, monkeypatch):
    # Phase 21(.docs/phase/phase_21_코멘트조사자동화및방어처리.md) — 항목 1건에서
    # 예외가 나도 F7 초안 생성 전체가 죽지 않고, 그 항목만 플레이스홀더로 대체된 채
    # 나머지 항목은 정상 생성돼야 한다(uploads.py/refinement.py와 같은 원칙).
    import app.services.reports as reports_module

    batch_id = _seed_three_months(client)
    anomalies = client.get(f"/batches/{batch_id}/anomalies").json()["anomalies"]
    assert len(anomalies) > 1  # 실패 1건 + 정상 나머지를 구분해 검증하려면 2건 이상 필요

    original_generate_comment = reports_module.generate_comment
    call_count = {"n": 0}

    def flaky_generate_comment(record):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("강제로 발생시킨 테스트용 예외")
        return original_generate_comment(record)

    monkeypatch.setattr(reports_module, "generate_comment", flaky_generate_comment)

    response = client.post("/reports", json={"batch_id": batch_id})
    assert response.status_code == 200, response.text
    items = response.json()["items"]

    # 전체 개수는 그대로 유지된다(실패한 항목도 건너뛰지 않고 플레이스홀더로 채움).
    assert len(items) == len(anomalies)
    failed = [i for i in items if "코멘트 생성 실패" in i["auto_comment"]]
    assert len(failed) == 1
    succeeded = [i for i in items if i not in failed]
    assert len(succeeded) == len(anomalies) - 1
    for item in succeeded:
        assert "코멘트 생성 실패" not in item["auto_comment"]


def test_create_report_draft_has_one_item_per_anomaly_flag(client):
    batch_id = _seed_three_months(client)
    anomalies = client.get(f"/batches/{batch_id}/anomalies").json()["anomalies"]

    response = client.post("/reports", json={"batch_id": batch_id})
    assert response.status_code == 200, response.text
    draft = response.json()

    assert draft["batch_id"] == batch_id
    assert draft["status"] == "초안"
    assert len(draft["items"]) == len(anomalies)
    assert len(anomalies) > 0

    for item in draft["items"]:
        assert item["auto_comment"]
        assert item["user_comment"] is None
        assert item["chart_ref"] == item["team"]


def test_get_report_draft_returns_same_items(client):
    batch_id = _seed_three_months(client)
    created = client.post("/reports", json={"batch_id": batch_id}).json()

    fetched = client.get(f"/reports/{created['draft_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["items"] == created["items"]


def test_create_report_for_unknown_batch_returns_404(client):
    response = client.post("/reports", json={"batch_id": "does-not-exist"})
    assert response.status_code == 404


def test_get_unknown_report_returns_404(client):
    response = client.get("/reports/does-not-exist")
    assert response.status_code == 404


def test_report_items_sorted_by_impact_amount_desc(client):
    batch_id = _seed_three_months(client)
    draft = client.post("/reports", json={"batch_id": batch_id}).json()
    impacts = [abs(i["impact_amount"] or 0) for i in draft["items"]]
    assert impacts == sorted(impacts, reverse=True)


def test_patch_report_item_updates_user_comment_background_note_and_exclusion(client):
    batch_id = _seed_three_months(client)
    draft = client.post("/reports", json={"batch_id": batch_id}).json()
    item = draft["items"][0]

    response = client.patch(
        f"/reports/{draft['draft_id']}/items/{item['item_id']}",
        json={"user_comment": "수정된 코멘트", "background_note": "특이 거래처 이슈", "is_excluded": True},
    )
    assert response.status_code == 200, response.text
    updated = next(i for i in response.json()["items"] if i["item_id"] == item["item_id"])
    assert updated["user_comment"] == "수정된 코멘트"
    assert updated["background_note"] == "특이 거래처 이슈"
    assert updated["is_excluded"] is True
    assert updated["auto_comment"] == item["auto_comment"]  # 자동 코멘트 원본은 보존


def test_patch_report_item_partial_update_leaves_other_fields_untouched(client):
    batch_id = _seed_three_months(client)
    draft = client.post("/reports", json={"batch_id": batch_id}).json()
    item_id = draft["items"][0]["item_id"]

    client.patch(f"/reports/{draft['draft_id']}/items/{item_id}", json={"is_excluded": True})
    response = client.patch(f"/reports/{draft['draft_id']}/items/{item_id}", json={"background_note": "메모"})

    updated = next(i for i in response.json()["items"] if i["item_id"] == item_id)
    assert updated["is_excluded"] is True  # 이전 PATCH의 값이 유지됨
    assert updated["background_note"] == "메모"


def test_patch_unknown_report_item_returns_404(client):
    batch_id = _seed_three_months(client)
    draft = client.post("/reports", json={"batch_id": batch_id}).json()

    response = client.patch(
        f"/reports/{draft['draft_id']}/items/does-not-exist", json={"is_excluded": True}
    )
    assert response.status_code == 404


def test_report_draft_includes_pl_item_plan_deviation_comment(client, test_db):
    # Phase 18(.docs/phase/phase_18_손익항목계획대비판정.md) — 손익 상세 분석 계정과목이
    # 팀 계획 대비 임계치를 넘으면 F7 초안에 전용 문장이 포함돼야 한다.
    batch_id = "batch-pl-item"
    test_db.connection.execute(
        "INSERT INTO upload_batch (batch_id, upload_date, target_year, target_month) VALUES (?, ?, ?, ?)",
        [batch_id, "2026-08-01", 2026, 7],
    )
    test_db.connection.execute(
        """
        INSERT INTO refined_sales_record (
            record_id, batch_id, file_id, year, month, team, customer_code, customer_name,
            product_code, product_desc, product_group, product_group_1, product_group_2, is_mapped,
            sales_final, quantity, cogs_final, is_calc_error
        ) VALUES (?, ?, 'file-1', 2026, 7, '차량대리점', 'C0000001', 'test',
                   'P0001', 'desc', 'GB 소형', 'GB', 'GB 소형계열', true,
                   1000000, 100, 555000, false)
        """,
        [str(uuid.uuid4()), batch_id],
    )
    test_db.connection.execute(
        "INSERT INTO team_pl_record (record_id, file_id, batch_id, team, account_item, year, month, amount)"
        " VALUES (?, 'file-1', ?, '차량대리점', '매출원가(A)Tot', 2026, 7, 500000)",
        [str(uuid.uuid4()), batch_id],
    )
    test_db.connection.execute(
        "INSERT INTO team_pl_record (record_id, file_id, batch_id, team, account_item, year, month, amount)"
        " VALUES (?, 'file-1', ?, '차량대리점', '매출수량', 2026, 7, 100)",
        [str(uuid.uuid4()), batch_id],
    )
    from app.services.aggregation import compute_aggregates_for_batch
    from app.services.anomaly import evaluate_anomalies

    compute_aggregates_for_batch(test_db, batch_id)
    assert evaluate_anomalies(test_db, batch_id) > 0

    response = client.post("/reports", json={"batch_id": batch_id})
    assert response.status_code == 200, response.text
    items = response.json()["items"]

    # 이 fixture는 material_total/labor_total/expense_total을 채우지 않아 "기타(상품구매,
    # 재고실사차이 등)"도 cogs_final과 우연히 같은 값으로 같이 플래그된다 — cogs_final
    # (매출원가) 항목만 골라 검증한다.
    pl_items = [
        i for i in items if i["metric_type"] == "손익항목계획대비" and i["product_group"] == "매출원가"
    ]
    assert len(pl_items) == 1
    comment = pl_items[0]["auto_comment"]
    assert "매출원가" in comment
    assert "차량대리점" in comment
    for word in FORBIDDEN_WORDS:
        assert word not in comment


def test_batch_delete_cascades_to_report_draft(client, test_db):
    batch_id = _seed_three_months(client)
    draft = client.post("/reports", json={"batch_id": batch_id}).json()

    test_db.delete_batch(batch_id)

    remaining_items = test_db.connection.execute(
        "SELECT COUNT(*) FROM report_item WHERE draft_id = ?", [draft["draft_id"]]
    ).fetchone()[0]
    remaining_draft = test_db.connection.execute(
        "SELECT COUNT(*) FROM report_draft WHERE draft_id = ?", [draft["draft_id"]]
    ).fetchone()[0]
    assert remaining_items == 0
    assert remaining_draft == 0
