import uuid
from datetime import datetime

import pytest

from app.db import Database
from app.services.pl_comparison import PLComparisonError, get_pl_comparison


def _insert_refined_row_full(
    db, batch_id, year, month, team, *,
    quantity, sales_final, material_total, labor_total, expense_total, sga_final, cogs_final,
):
    db.connection.execute(
        """
        INSERT INTO refined_sales_record (
            record_id, batch_id, file_id, year, month, team, customer_code, customer_name,
            product_code, product_desc, product_group, product_group_1, product_group_2, is_mapped,
            sales_final, quantity, material_total, labor_total, expense_total, sga_final, cogs_final, is_calc_error
        ) VALUES (?, ?, 'file-1', ?, ?, ?, 'C0000001', 'test',
                   'P0001', 'desc', 'GB 소형', 'GB', 'GB 소형계열', true,
                   ?, ?, ?, ?, ?, ?, ?, false)
        """,
        [
            str(uuid.uuid4()), batch_id, year, month, team,
            sales_final, quantity, material_total, labor_total, expense_total, sga_final, cogs_final,
        ],
    )


@pytest.fixture()
def db():
    database = Database(":memory:")
    yield database
    database.close()


def _make_batch(db, year, month) -> str:
    batch_id = str(uuid.uuid4())
    db.connection.execute(
        "INSERT INTO upload_batch (batch_id, upload_date, target_year, target_month) VALUES (?, ?, ?, ?)",
        [batch_id, datetime.now(), year, month],
    )
    return batch_id


def _insert_refined_row(
    db, batch_id, year, month, team, *,
    quantity, sales_final, material_total, sga_final,
    customer_name="test", product_code="P0001", product_desc="desc",
    product_group="GB 소형", product_group_1="GB", product_group_2="GB 소형계열",
):
    db.connection.execute(
        """
        INSERT INTO refined_sales_record (
            record_id, batch_id, file_id, year, month, team, customer_code, customer_name,
            product_code, product_desc, product_group, product_group_1, product_group_2, is_mapped,
            sales_final, quantity, material_total, sga_final, is_calc_error
        ) VALUES (?, ?, 'file-1', ?, ?, ?, 'C0000001', ?, ?, ?, ?, ?, ?, true,
                   ?, ?, ?, ?, false)
        """,
        [
            str(uuid.uuid4()), batch_id, year, month, team, customer_name,
            product_code, product_desc, product_group, product_group_1, product_group_2,
            sales_final, quantity, material_total, sga_final,
        ],
    )


def _insert_plan(db, team, year, month, account_item, amount):
    db.connection.execute(
        "INSERT INTO team_pl_record (record_id, file_id, batch_id, team, account_item, year, month, amount)"
        " VALUES (?, 'file-1', 'batch-1', ?, ?, ?, ?, ?)",
        [str(uuid.uuid4()), team, account_item, year, month, amount],
    )


def test_get_pl_comparison_computes_unit_ratio_and_change_rate(db):
    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=100, sales_final=1_000_000, material_total=400_000, sga_final=100_000,
    )
    _insert_plan(db, "차량대리점", 2026, 8, "매출수량", 80)
    _insert_plan(db, "차량대리점", 2026, 8, "매출액(Total)", 800_000)
    _insert_plan(db, "차량대리점", 2026, 8, "판관비(Total)", 90_000)

    results = get_pl_comparison(db, batch_id, team=["차량대리점"]).lines
    by_key = {r.key: r for r in results}

    sales = by_key["sales_final"]
    assert sales.plan_total == pytest.approx(800_000)
    assert sales.actual_total == pytest.approx(1_000_000)
    assert sales.plan_unit == pytest.approx(800_000 / 80)  # 10,000
    assert sales.actual_unit == pytest.approx(1_000_000 / 100)  # 10,000
    assert sales.plan_ratio == pytest.approx(100.0)  # 매출액 자기 자신 대비 100%
    assert sales.diff_total == pytest.approx(200_000)
    assert sales.change_rate == pytest.approx(200_000 / 800_000)

    sga = by_key["sga_final"]
    assert sga.actual_ratio == pytest.approx(100_000 / 1_000_000 * 100)  # 10%


def test_get_pl_comparison_all_teams_when_team_is_none(db):
    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=50, sales_final=500_000, material_total=100_000, sga_final=20_000,
    )
    _insert_refined_row(
        db, batch_id, 2026, 8, "모티브",
        quantity=30, sales_final=300_000, material_total=60_000, sga_final=10_000,
    )
    _insert_plan(db, "차량대리점", 2026, 8, "매출액(Total)", 400_000)
    _insert_plan(db, "모티브", 2026, 8, "매출액(Total)", 250_000)

    results = get_pl_comparison(db, batch_id, team=None).lines
    sales = next(r for r in results if r.key == "sales_final")

    assert sales.actual_total == pytest.approx(800_000)
    assert sales.plan_total == pytest.approx(650_000)


def test_get_pl_comparison_rejects_unknown_team(db):
    batch_id = _make_batch(db, 2026, 8)
    with pytest.raises(PLComparisonError):
        get_pl_comparison(db, batch_id, team=["존재하지않는팀"])


def test_get_pl_comparison_rejects_unknown_batch(db):
    with pytest.raises(PLComparisonError):
        get_pl_comparison(db, "no-such-batch", team=None)


def test_get_pl_comparison_handles_missing_plan_data_without_crashing(db):
    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=10, sales_final=100_000, material_total=40_000, sga_final=10_000,
    )
    # 계획 데이터가 전혀 없는 경우 (team_pl_record 미업로드)
    results = get_pl_comparison(db, batch_id, team=["차량대리점"]).lines
    sales = next(r for r in results if r.key == "sales_final")

    assert sales.plan_total == 0.0
    assert sales.plan_unit is None
    assert sales.change_rate is None
    assert sales.actual_total == pytest.approx(100_000)


def test_pl_comparison_api_returns_lines(client, test_db):
    batch_id = _make_batch(test_db, 2026, 8)
    _insert_refined_row(
        test_db, batch_id, 2026, 8, "차량대리점",
        quantity=10, sales_final=100_000, material_total=40_000, sga_final=10_000,
    )
    _insert_plan(test_db, "차량대리점", 2026, 8, "매출액(Total)", 90_000)

    response = client.get(f"/batches/{batch_id}/pl-comparison", params={"team": "차량대리점"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["team"] == "차량대리점"
    sales = next(line for line in body["lines"] if line["key"] == "sales_final")
    assert sales["actual_total"] == pytest.approx(100_000)
    assert sales["plan_total"] == pytest.approx(90_000)


def test_pl_comparison_api_defaults_to_national_when_team_omitted(client, test_db):
    batch_id = _make_batch(test_db, 2026, 8)
    _insert_refined_row(
        test_db, batch_id, 2026, 8, "차량대리점",
        quantity=10, sales_final=100_000, material_total=40_000, sga_final=10_000,
    )

    response = client.get(f"/batches/{batch_id}/pl-comparison")
    assert response.status_code == 200, response.text
    assert response.json()["team"] == "국내"


def test_pl_comparison_api_404_for_unknown_batch(client):
    response = client.get("/batches/no-such-batch/pl-comparison")
    assert response.status_code == 404


def test_pl_comparison_api_400_for_unknown_team(client, test_db):
    batch_id = _make_batch(test_db, 2026, 8)
    response = client.get(f"/batches/{batch_id}/pl-comparison", params={"team": "없는팀"})
    assert response.status_code == 400


def test_get_pl_comparison_computes_prev_month_comparison(db):
    prev_batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(
        db, prev_batch_id, 2026, 7, "차량대리점",
        quantity=80, sales_final=800_000, material_total=300_000, sga_final=50_000,
    )
    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=100, sales_final=1_000_000, material_total=400_000, sga_final=100_000,
    )

    results = get_pl_comparison(db, batch_id, team=["차량대리점"]).lines
    sales = next(r for r in results if r.key == "sales_final")

    assert sales.prev_month_available is True
    assert sales.prev_month_total == pytest.approx(800_000)
    assert sales.diff_prev_month_total == pytest.approx(200_000)
    assert sales.change_rate_prev_month == pytest.approx(200_000 / 800_000)


def test_get_pl_comparison_handles_january_prev_month_as_prior_december(db):
    prev_batch_id = _make_batch(db, 2025, 12)
    _insert_refined_row(
        db, prev_batch_id, 2025, 12, "차량대리점",
        quantity=10, sales_final=100_000, material_total=10_000, sga_final=1_000,
    )
    batch_id = _make_batch(db, 2026, 1)
    _insert_refined_row(
        db, batch_id, 2026, 1, "차량대리점",
        quantity=10, sales_final=150_000, material_total=10_000, sga_final=1_000,
    )

    results = get_pl_comparison(db, batch_id, team=["차량대리점"]).lines
    sales = next(r for r in results if r.key == "sales_final")

    assert sales.prev_month_available is True
    assert sales.prev_month_total == pytest.approx(100_000)


def test_get_pl_comparison_prev_month_unavailable_without_crashing(db):
    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=10, sales_final=100_000, material_total=10_000, sga_final=1_000,
    )

    results = get_pl_comparison(db, batch_id, team=["차량대리점"]).lines
    sales = next(r for r in results if r.key == "sales_final")

    assert sales.prev_month_available is False
    assert sales.prev_month_total is None
    assert sales.change_rate_prev_month is None


def test_get_pl_comparison_applies_drilldown_filters(db):
    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=50, sales_final=500_000, material_total=100_000, sga_final=10_000,
        customer_name="고객A", product_code="P0001", product_group_1="GB",
    )
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=30, sales_final=300_000, material_total=60_000, sga_final=5_000,
        customer_name="고객B", product_code="P0002", product_group_1="AGM",
    )

    results = get_pl_comparison(db, batch_id, team=["차량대리점"], product_group_1=["GB"]).lines
    sales = next(r for r in results if r.key == "sales_final")
    assert sales.actual_total == pytest.approx(500_000)

    results_customer = get_pl_comparison(db, batch_id, customer=["고객B"]).lines
    sales_customer = next(r for r in results_customer if r.key == "sales_final")
    assert sales_customer.actual_total == pytest.approx(300_000)


def test_plan_comparison_unavailable_when_drilldown_filter_applied(db):
    # Phase 18(.docs/phase/phase_18_손익항목계획대비판정.md, 사용자 확인) — 드릴다운
    # 필터(고객/상품/DESC/제품구분1~3)가 걸리면 계획(팀×월 단위만 존재)과 실적(필터링된
    # 부분집합)의 granularity가 어긋나므로 계획대비 diff 3종을 비교불가 처리한다.
    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=50, sales_final=500_000, material_total=100_000, sga_final=10_000,
        customer_name="고객A", product_group_1="GB",
    )
    _insert_plan(db, "차량대리점", 2026, 8, "매출액(Total)", 400_000)

    team_only = get_pl_comparison(db, batch_id, team=["차량대리점"])
    assert team_only.plan_comparison_available is True
    sales_team_only = next(r for r in team_only.lines if r.key == "sales_final")
    assert sales_team_only.diff_total == pytest.approx(100_000)
    assert sales_team_only.change_rate is not None

    filtered = get_pl_comparison(db, batch_id, team=["차량대리점"], customer=["고객A"])
    assert filtered.plan_comparison_available is False
    sales_filtered = next(r for r in filtered.lines if r.key == "sales_final")
    assert sales_filtered.diff_total is None
    assert sales_filtered.diff_unit is None
    assert sales_filtered.change_rate is None
    # 실적 자체는 그대로 보여준다(필터링된 값이 숨겨지는 게 아니라, 계획 비교값만 숨김).
    assert sales_filtered.actual_total == pytest.approx(500_000)


def test_pl_comparison_api_exposes_plan_comparison_available(client, test_db):
    batch_id = _make_batch(test_db, 2026, 8)
    _insert_refined_row(
        test_db, batch_id, 2026, 8, "차량대리점",
        quantity=10, sales_final=100_000, material_total=10_000, sga_final=1_000,
        customer_name="고객A",
    )

    team_only = client.get(f"/batches/{batch_id}/pl-comparison", params={"team": "차량대리점"})
    assert team_only.json()["plan_comparison_available"] is True

    filtered = client.get(
        f"/batches/{batch_id}/pl-comparison", params={"team": "차량대리점", "customer": "고객A"}
    )
    assert filtered.json()["plan_comparison_available"] is False


def test_get_pl_comparison_supports_multi_select_filters(db):
    # 사용자 확인: 드릴다운 필터는 여러 값을 동시에 선택할 수 있어야 한다(OR로 묶임).
    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=50, sales_final=500_000, material_total=100_000, sga_final=10_000,
        customer_name="고객A", product_code="P0001", product_group_1="GB",
    )
    _insert_refined_row(
        db, batch_id, 2026, 8, "모티브",
        quantity=30, sales_final=300_000, material_total=60_000, sga_final=5_000,
        customer_name="고객B", product_code="P0002", product_group_1="AGM",
    )
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량OE",
        quantity=20, sales_final=200_000, material_total=40_000, sga_final=3_000,
        customer_name="고객C", product_code="P0003", product_group_1="ES 소형",
    )

    # 팀 2개(차량대리점+모티브) 다중 선택 — 차량OE는 제외되어야 한다.
    results = get_pl_comparison(db, batch_id, team=["차량대리점", "모티브"]).lines
    sales = next(r for r in results if r.key == "sales_final")
    assert sales.actual_total == pytest.approx(800_000)

    # 제품구분1 2개(GB+AGM) 다중 선택도 동일하게 OR로 묶인다.
    results_group = get_pl_comparison(db, batch_id, product_group_1=["GB", "AGM"]).lines
    sales_group = next(r for r in results_group if r.key == "sales_final")
    assert sales_group.actual_total == pytest.approx(800_000)


def test_get_pl_comparison_filter_options_lists_actual_values(db):
    from app.services.pl_comparison import get_pl_comparison_filter_options

    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=50, sales_final=500_000, material_total=100_000, sga_final=10_000,
        customer_name="고객A", product_code="P0001", product_group_1="GB",
    )
    _insert_refined_row(
        db, batch_id, 2026, 8, "모티브",
        quantity=30, sales_final=300_000, material_total=60_000, sga_final=5_000,
        customer_name="고객B", product_code="P0002", product_group_1="AGM",
    )

    options = get_pl_comparison_filter_options(db, batch_id)
    assert options["teams"] == ["모티브", "고정형", "차량대리점", "차량OE"]
    assert set(options["customer"]) == {"고객A", "고객B"}
    assert set(options["product_group_1"]) == {"GB", "AGM"}


def test_pl_comparison_api_returns_prev_month_and_supports_filters(client, test_db):
    prev_batch_id = _make_batch(test_db, 2026, 7)
    _insert_refined_row(
        test_db, prev_batch_id, 2026, 7, "차량대리점",
        quantity=10, sales_final=90_000, material_total=10_000, sga_final=1_000,
    )
    batch_id = _make_batch(test_db, 2026, 8)
    _insert_refined_row(
        test_db, batch_id, 2026, 8, "차량대리점",
        quantity=10, sales_final=100_000, material_total=10_000, sga_final=1_000,
        product_group_1="GB",
    )

    response = client.get(
        f"/batches/{batch_id}/pl-comparison", params={"team": "차량대리점", "product_group_1": "GB"}
    )
    assert response.status_code == 200, response.text
    sales = next(line for line in response.json()["lines"] if line["key"] == "sales_final")
    assert sales["prev_month_available"] is True
    assert sales["prev_month_total"] == pytest.approx(90_000)


def test_pl_comparison_filters_api_returns_options(client, test_db):
    batch_id = _make_batch(test_db, 2026, 8)
    _insert_refined_row(
        test_db, batch_id, 2026, 8, "차량대리점",
        quantity=10, sales_final=100_000, material_total=10_000, sga_final=1_000,
        customer_name="고객A",
    )

    response = client.get(f"/batches/{batch_id}/pl-comparison/filters")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "고객A" in body["customer"]
    assert body["teams"] == ["모티브", "고정형", "차량대리점", "차량OE"]


def test_get_pl_comparison_includes_other_cogs_and_total_cost(db):
    # 참고 파일(2026년 08월 4. 손익분석(2단계 배포용)_구조파악용.xlsb) "검색용" 시트의
    # "1) 계획 대비" 표에서 실측된 잔여/합산 행 — cogs_final(매출원가 최종마감)은
    # refinement.py가 원본 컬럼을 그대로 채택해 재료비+노무비+경비 합과 정확히
    # 일치하지 않으므로, 그 차액이 "기타(상품구매,재고실사차이 등)" 행이 되고,
    # 총원가는 매출원가+판관비다.
    batch_id = _make_batch(db, 2026, 8)
    _insert_refined_row_full(
        db, batch_id, 2026, 8, "차량대리점",
        quantity=10, sales_final=1_000_000,
        material_total=300_000, labor_total=100_000, expense_total=50_000,
        cogs_final=500_000,  # 재료비+노무비+경비(450,000)보다 50,000 크다
        sga_final=200_000,
    )

    results = get_pl_comparison(db, batch_id, team=["차량대리점"]).lines
    by_key = {r.key: r for r in results}

    other_cogs = by_key["other_cogs"]
    assert other_cogs.actual_total == pytest.approx(50_000)  # 500,000 - (300,000+100,000+50,000)

    total_cost = by_key["total_cost"]
    assert total_cost.actual_total == pytest.approx(700_000)  # cogs_final(500,000) + sga_final(200,000)

    # 순서: ...경비 계, 기타(잔여), 매출원가... / ...판관비 계, 총원가, 영업이익 순으로 삽입된다.
    keys_in_order = [r.key for r in results]
    assert keys_in_order.index("other_cogs") == keys_in_order.index("cogs_final") - 1
    assert keys_in_order.index("total_cost") == keys_in_order.index("operating_profit_final") - 1


def test_get_pl_comparison_expands_labor_direct_and_sga_variable_breakdown(db):
    # 사용자 확인: 직접노무비를 변동직접/고정직접으로 세분화하고, 변동판관비를
    # 차량유지비·운반비·수출비용·시험설치비·판매보증비·불량제품손실·해상운임으로
    # 세분화하며, 원재료비_니켈·원재료비_리튬은 항상 0이라 목록에서 숨긴다.
    batch_id = _make_batch(db, 2026, 8)
    value_columns = [
        "sales_final", "quantity",
        "labor_variable_direct", "labor_fixed_direct", "labor_direct",
        "sga_vehicle", "sga_delivery", "sga_export", "sga_installation", "sga_warranty",
        "sga_defect_loss", "sga_ocean_freight", "sga_variable",
        "raw_material_nickel", "raw_material_lithium", "raw_material_total",
    ]
    values = [
        1_000_000, 10,
        200_000, 300_000, 500_000,
        1_000, 2_000, 3_000, 4_000, 5_000,
        6_000, 7_000, 28_000,
        999_999, 888_888, 0,  # 니켈·리튬은 실제로 0이 아니어도(테스트 목적) 숨겨져야 함
    ]
    assert len(value_columns) == len(values)
    db.connection.execute(
        f"""
        INSERT INTO refined_sales_record (
            record_id, batch_id, file_id, year, month, team, customer_code, customer_name,
            product_code, product_desc, product_group, product_group_1, product_group_2, is_mapped,
            {", ".join(value_columns)}, is_calc_error
        ) VALUES (?, ?, 'file-1', ?, ?, ?, 'C0000001', 'test',
                   'P0001', 'desc', 'GB 소형', 'GB', 'GB 소형계열', true,
                   {", ".join(["?"] * len(values))}, false)
        """,
        [str(uuid.uuid4()), batch_id, 2026, 8, "차량대리점", *values],
    )

    results = get_pl_comparison(db, batch_id, team=["차량대리점"]).lines
    by_key = {r.key: r for r in results}
    labels_by_key = {r.key: r.label for r in results}

    assert by_key["labor_variable_direct"].actual_total == pytest.approx(200_000)
    assert by_key["labor_fixed_direct"].actual_total == pytest.approx(300_000)
    assert labels_by_key["labor_direct"] == "직접노무비 계"

    assert by_key["sga_vehicle"].actual_total == pytest.approx(1_000)
    assert by_key["sga_ocean_freight"].actual_total == pytest.approx(7_000)
    assert labels_by_key["sga_variable"] == "변동판관비 계"
    assert labels_by_key["sga_fixed"] == "고정판관비 계"

    assert "raw_material_nickel" not in by_key
    assert "raw_material_lithium" not in by_key
