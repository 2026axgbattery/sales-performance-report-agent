"""F4 Overview 탭 3종(팀별/제품군별/거래처별) 회귀 테스트 — .docs/phase/phase_14_월별실적분석탭.md.

pl_comparison.py(계획 대비)와 달리 순수 실적 집계라 계획/목표 데이터는 조회하지 않는다.
"""
import pytest

from app.services.monthly_analysis import (
    get_customer_monthly_analysis,
    get_product_group_monthly_analysis,
    get_team_monthly_analysis,
)
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


def test_team_monthly_analysis_computes_mtd_and_ytd_in_million_won(client, test_db):
    batch_id = _seed_three_months(client)

    result = get_team_monthly_analysis(test_db, batch_id)
    assert result["year"] == 2026

    cha = next(t for t in result["teams"] if t["team"] == "차량대리점")
    assert len(cha["months"]) == 12

    july = next(m for m in cha["months"] if m["month"] == 7)
    # 727885(원) 전체 팀 합계는 test_analytics_api.py에서 이미 검증된 값 — 백만원 변환만 확인.
    assert july["metrics"]["actual_amount"] == pytest.approx(727885 / 1_000_000)
    assert july["metrics"]["profit_rate"] is not None
    # 픽스처는 표준매출원가(S)를 매출원가(A)와 같은 값으로 채웠으므로 두 값이 일치해야 한다.
    assert july["metrics"]["mfg_cost"] == pytest.approx(july["metrics"]["standard_cogs"])

    june = next(m for m in cha["months"] if m["month"] == 6)
    assert june["metrics"]["actual_amount"] == pytest.approx(600000 / 1_000_000)

    january = next(m for m in cha["months"] if m["month"] == 1)
    assert january["metrics"] is None  # 업로드되지 않은 달은 값이 없다

    # "팀 요약"(연간 합계)은 6월+7월 배치를 합산한 값이어야 한다.
    assert cha["summary"]["actual_amount"] == pytest.approx((600000 + 727885) / 1_000_000)
    assert result["total"]["actual_amount"] == pytest.approx(
        sum(t["summary"]["actual_amount"] for t in result["teams"])
    )


def test_product_group_monthly_analysis_groups_by_team_with_subtotals(client, test_db):
    batch_id = _seed_three_months(client)

    result = get_product_group_monthly_analysis(test_db, batch_id)
    assert result["year"] == 2026 and result["month"] == 7

    cha_group = next(g for g in result["groups"] if g["team"] == "차량대리점")
    assert len(cha_group["rows"]) >= 1
    # 소계는 그 팀의 모든 제품군 행 합과 같아야 한다.
    assert cha_group["subtotal"]["mtd"]["actual_amount"] == pytest.approx(
        sum(r["mtd"]["actual_amount"] for r in cha_group["rows"])
    )
    assert result["total"]["mtd"]["actual_amount"] == pytest.approx(
        sum(g["subtotal"]["mtd"]["actual_amount"] for g in result["groups"])
    )


def test_customer_monthly_analysis_groups_by_team_with_subtotals(client, test_db):
    batch_id = _seed_three_months(client)

    result = get_customer_monthly_analysis(test_db, batch_id)
    cha_group = next(g for g in result["groups"] if g["team"] == "차량대리점")
    assert cha_group["subtotal"]["mtd"]["actual_amount"] == pytest.approx(
        sum(r["mtd"]["actual_amount"] for r in cha_group["rows"])
    )


def test_monthly_analysis_unknown_batch_returns_404(client):
    for path in ("team", "product-group", "customer"):
        response = client.get(f"/batches/does-not-exist/monthly-analysis/{path}")
        assert response.status_code == 404


def test_monthly_analysis_api_endpoints_return_expected_shape(client):
    batch_id = _seed_three_months(client)

    team_resp = client.get(f"/batches/{batch_id}/monthly-analysis/team")
    assert team_resp.status_code == 200, team_resp.text
    assert "teams" in team_resp.json() and "total" in team_resp.json()

    pg_resp = client.get(f"/batches/{batch_id}/monthly-analysis/product-group")
    assert pg_resp.status_code == 200, pg_resp.text
    assert "groups" in pg_resp.json()

    cust_resp = client.get(f"/batches/{batch_id}/monthly-analysis/customer")
    assert cust_resp.status_code == 200, cust_resp.text
    assert "groups" in cust_resp.json()


def test_product_group_monthly_analysis_team_filter_narrows_groups(client):
    batch_id = _seed_three_months(client)

    all_teams = {g["team"] for g in client.get(f"/batches/{batch_id}/monthly-analysis/product-group").json()["groups"]}
    assert len(all_teams) > 1  # 필터링이 실제로 뭔가를 줄이는지 확인하려면 2개 이상이어야 함

    response = client.get(f"/batches/{batch_id}/monthly-analysis/product-group", params={"team": "차량대리점"})
    assert response.status_code == 200, response.text
    groups = response.json()["groups"]
    assert {g["team"] for g in groups} == {"차량대리점"}


def test_customer_monthly_analysis_team_and_part_filters(client, test_db):
    # mapping_with_branch.xlsx가 PCC01179 -> part="대리점"으로 지점코드를 매핑한다
    # (tests/test_uploads_api.py::test_upload_mapping_with_branch_sheet_populates_region_office_part 참고).
    upload = _upload(client, [("actual_sample.csv", "실적"), ("mapping_with_branch.xlsx", "매핑표")])
    assert upload.status_code == 200, upload.text
    batch_id = upload.json()["batch_id"]

    team_only = client.get(f"/batches/{batch_id}/monthly-analysis/customer", params={"team": "차량대리점"})
    assert team_only.status_code == 200, team_only.text
    assert {g["team"] for g in team_only.json()["groups"]} == {"차량대리점"}

    part_only = client.get(f"/batches/{batch_id}/monthly-analysis/customer", params={"part": "대리점"})
    assert part_only.status_code == 200, part_only.text
    # part로 필터링하면 그 파트에 매핑된 거래처(PCC01179의 고객)만 남아야 한다.
    all_customers = {r["customer"] for g in part_only.json()["groups"] for r in g["rows"]}
    assert all_customers  # 최소 하나는 있어야 한다
    unfiltered_customers = {
        r["customer"] for g in client.get(f"/batches/{batch_id}/monthly-analysis/customer").json()["groups"] for r in g["rows"]
    }
    assert all_customers <= unfiltered_customers
    assert len(all_customers) < len(unfiltered_customers)


def test_monthly_analysis_filter_options_returns_teams_and_parts(client):
    batch_id = _upload(client, [("actual_sample.csv", "실적"), ("mapping_with_branch.xlsx", "매핑표")]).json()["batch_id"]

    response = client.get(f"/batches/{batch_id}/monthly-analysis/filters")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "차량대리점" in body["teams"]
    assert "대리점" in body["parts"]


def test_monthly_analysis_filters_unknown_batch_returns_404(client):
    response = client.get("/batches/does-not-exist/monthly-analysis/filters")
    assert response.status_code == 404
