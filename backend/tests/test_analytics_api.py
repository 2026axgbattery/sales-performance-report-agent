import pytest

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


def test_list_batches_returns_uploaded_periods(client):
    _seed_three_months(client)
    response = client.get("/batches")
    assert response.status_code == 200
    periods = {(b["year"], b["month"]) for b in response.json()["batches"]}
    assert periods == {(2025, 7), (2026, 6), (2026, 7)}


def test_overview_returns_team_rollup_and_summary(client):
    batch_id = _seed_three_months(client)
    response = client.get(f"/batches/{batch_id}/overview")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["year"] == 2026
    assert body["month"] == 7
    teams = {t["team"]: t for t in body["teams"]}

    cha = teams["차량대리점"]
    # 177885(PCC01179) + 540000(PCC04736) + 10000(XPZ99999, 미매핑이지만 팀 합계에는 포함)
    assert cha["actual_amount"] == 727885
    assert cha["prev_month_available"] is True
    assert cha["prev_month_change_pct"] == pytest.approx((727885 - 600000) / 600000 * 100)
    assert cha["prev_year_month_available"] is True
    # plan_amount(900000)은 팀 단위 값이 제품군별 행(매핑/미매핑)에 중복 저장되므로
    # SUM이 아닌 1회만 반영되어야 한다: 727885 / 900000 = 80.87%
    assert cha["plan_amount"] == 900000
    assert cha["achievement_rate"] == pytest.approx(727885 / 900000 * 100)

    # 팀별 순위(매출 내림차순) 정렬 확인
    amounts = [t["actual_amount"] for t in body["teams"]]
    assert amounts == sorted(amounts, reverse=True)

    assert body["summary"]["total_actual_amount"] == sum(t["actual_amount"] for t in body["teams"])
    assert body["summary"]["total_quantity"] == sum(t["quantity"] for t in body["teams"])
    assert body["summary"]["total_profit_rate"] == pytest.approx(
        body["summary"]["total_profit"] / body["summary"]["total_actual_amount"] * 100
    )

    # Overview 상단 요약 카드의 "전월 대비" 문구가 매출·영업이익·이익률을 함께
    # 비교할 수 있도록, 전월 매출·영업이익 원시 합계도 summary에 노출된다.
    assert body["summary"]["prev_month_available"] is True
    expected_prev_amount = sum(
        t["prev_month_amount"] for t in body["teams"] if t["prev_month_available"]
    )
    expected_prev_profit = sum(
        t["prev_month_profit"] for t in body["teams"] if t["prev_month_available"]
    )
    assert body["summary"]["prev_month_total_amount"] == pytest.approx(expected_prev_amount)
    assert body["summary"]["prev_month_total_profit"] == pytest.approx(expected_prev_profit)
    assert body["summary"]["prev_month_total_profit_rate"] == pytest.approx(
        expected_prev_profit / expected_prev_amount * 100
    )


def test_overview_includes_cumulative_ytd_totals(client):
    batch_id = _seed_three_months(client)
    response = client.get(f"/batches/{batch_id}/overview")
    assert response.status_code == 200, response.text
    body = response.json()

    cumulative = body["cumulative"]
    assert cumulative["up_to_month"] == 7
    cumulative_teams = {t["team"]: t for t in cumulative["teams"]}

    cha = cumulative_teams["차량대리점"]
    # 2026년 1~7월 중 실제 데이터가 있는 달은 6월(600000)+7월(727885)뿐이다.
    assert cha["actual_amount"] == pytest.approx(600000 + 727885)
    assert cumulative["total"]["actual_amount"] == pytest.approx(
        sum(t["actual_amount"] for t in cumulative["teams"])
    )


def test_overview_unknown_batch_returns_404(client):
    response = client.get("/batches/does-not-exist/overview")
    assert response.status_code == 404


def test_trend_returns_12_months_with_gaps_as_null(client):
    batch_id = _seed_three_months(client)
    response = client.get(f"/batches/{batch_id}/trend", params={"team": "차량대리점"})
    assert response.status_code == 200, response.text
    months = response.json()["months"]
    assert len(months) == 12

    june = next(m for m in months if m["month"] == 6)
    july = next(m for m in months if m["month"] == 7)
    january = next(m for m in months if m["month"] == 1)

    assert june["actual_amount"] == 600000
    assert july["actual_amount"] == 727885
    assert january["actual_amount"] is None  # 데이터 없는 달은 비어 있음


def test_anomalies_sorted_by_impact_amount_desc(client):
    batch_id = _seed_three_months(client)
    response = client.get(f"/batches/{batch_id}/anomalies")
    assert response.status_code == 200, response.text
    anomalies = response.json()["anomalies"]
    assert len(anomalies) > 0

    impacts = [abs(a["impact_amount"]) for a in anomalies]
    assert impacts == sorted(impacts, reverse=True)

    metric_types = {a["metric_type"] for a in anomalies}
    assert "전월대비" in metric_types
    assert "계획대비" in metric_types

    # 사용자 요청("전월 얼마에서 당월 얼마로 얼마 변동, 이렇게 표현하면 좋겠어") —
    # F5가 "전/후" 원시 값을 그대로 보여줄 수 있도록 before_value/after_value를
    # 유형별로 정확히 채워야 한다(전월대비는 전월 실적 vs 당월 실적, 계획대비는
    # 팀 계획 vs 팀 실적 — actual_value/impact_amount만으로는 역산이 위험한 유형도
    # 있어 그대로 재조회한 값이어야 한다).
    prev_month_flag = next(a for a in anomalies if a["metric_type"] == "전월대비" and a["team"] == "차량대리점")
    assert prev_month_flag["after_value"] - prev_month_flag["before_value"] == pytest.approx(
        prev_month_flag["impact_amount"]
    )
    assert (prev_month_flag["after_value"] - prev_month_flag["before_value"]) / prev_month_flag[
        "before_value"
    ] * 100 == pytest.approx(prev_month_flag["actual_value"])

    plan_flag = next(a for a in anomalies if a["metric_type"] == "계획대비" and a["team"] == "차량대리점")
    assert plan_flag["before_value"] == pytest.approx(900000)  # 팀 계획(plan_amount)
    assert plan_flag["after_value"] == pytest.approx(727885)  # 팀 실적 합계(제품군 전체)
    assert plan_flag["after_value"] / plan_flag["before_value"] * 100 == pytest.approx(plan_flag["actual_value"])
