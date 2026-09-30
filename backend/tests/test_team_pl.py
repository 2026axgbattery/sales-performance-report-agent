import pytest

from tests.conftest import FIXTURES_DIR

from app.services.team_pl import TeamPLValidationError, parse_team_pl_workbook


def _read(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def _by_item(entries, team, month):
    return {e.account_item: e.amount for e in entries if e.team == team and e.month == month}


def test_parse_team_pl_workbook_computes_subtotals_from_formula_ranges():
    entries = parse_team_pl_workbook(_read("team_pl_sample.xlsx"))
    row = _by_item(entries, "모티브", 1)

    assert row["매출액(Total)"] == 1000
    assert row["매출원가(A)Tot"] == 200  # SUM(원가 세부 항목) 직접 계산
    assert row["매출총이익(A)"] == 800  # 매출액 - 매출원가
    assert row["판관비(Total)"] == 50  # SUM(판관비 세부 항목) 직접 계산
    assert row["영업이익(A)"] == 750  # 매출총이익 - 판관비


def test_parse_team_pl_workbook_covers_all_team_sheets_and_months():
    entries = parse_team_pl_workbook(_read("team_pl_sample.xlsx"))
    teams = {e.team for e in entries}
    months = {e.month for e in entries}

    assert teams == {"모티브", "고정형"}
    assert months == set(range(1, 13))
    assert all(e.year == 2026 for e in entries)


def test_parse_team_pl_workbook_rejects_non_excel_content():
    with pytest.raises(TeamPLValidationError):
        parse_team_pl_workbook(b"not an excel file")


def test_parse_team_pl_workbook_long_format_uses_given_year():
    # 실제 업로드 형식(손익계산서_더미용.xlsx) — 시트 1개, 팀×월 행, 계정과목 열.
    # 파일 자체엔 연도 정보가 없어 실적 파일의 target_year를 그대로 받는다.
    entries = parse_team_pl_workbook(_read("team_pl_long_format_sample.xlsx"), year=2026)

    assert all(e.year == 2026 for e in entries)
    row = _by_item(entries, "모티브", 1)
    assert row["매출액(Total)"] == 1000
    assert row["매출원가(A)Tot"] == 400
    assert row["판관비(Total)"] == 100
    assert row["영업이익(A)"] == 500

    teams = {e.team for e in entries}
    assert teams == {"모티브", "고정형"}


def test_parse_team_pl_workbook_long_format_requires_year():
    with pytest.raises(TeamPLValidationError):
        parse_team_pl_workbook(_read("team_pl_long_format_sample.xlsx"))
