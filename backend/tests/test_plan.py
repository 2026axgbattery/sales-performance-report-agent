import pytest

from tests.conftest import FIXTURES_DIR

from app.services.plan import PlanValidationError, parse_plan_workbook


def _read(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def test_parse_plan_workbook_computes_amount_from_price_times_quantity():
    entries = parse_plan_workbook(_read("plan_sample.xlsx"))
    by_team = {e.team: e for e in entries}

    assert by_team["차량대리점"].month == 7
    assert by_team["차량대리점"].unit_price == 900000
    assert by_team["차량대리점"].quantity == 1
    assert by_team["차량대리점"].planned_amount == 900000  # 판가 x 수량

    assert by_team["모티브"].planned_amount == 50000


def test_parse_plan_workbook_resolves_hq_report_group_via_factor_sheet():
    entries = parse_plan_workbook(_read("plan_sample.xlsx"))
    by_team = {e.team: e for e in entries}

    assert by_team["차량대리점"].product_type == "제품A"
    assert by_team["차량대리점"].hq_report_group == "그룹A"
    assert by_team["모티브"].hq_report_group == "그룹B"


def test_parse_plan_workbook_keeps_customer_and_rep_fields():
    entries = parse_plan_workbook(_read("plan_sample.xlsx"))
    row = next(e for e in entries if e.team == "차량대리점")

    assert row.customer_code == "9000001"
    assert row.customer_name == "테스트고객1"
    assert row.sales_rep == "테스트담당"


def test_parse_plan_workbook_rejects_non_excel_content():
    with pytest.raises(PlanValidationError):
        parse_plan_workbook(b"not an excel file")
