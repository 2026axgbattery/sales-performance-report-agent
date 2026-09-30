"""손익항목계획대비 서술 문장 회귀 테스트(.docs/phase/phase_18_손익항목계획대비판정.md).

find_pl_item_deviations는 anomaly.py가 플래그를 만들 때, find_team_item_deviation은
reports.py가 F7 초안을 만들 때(재조회) 각각 쓴다 — 둘 다 항상 팀 전체 실적 vs 팀 전체
계획으로만 비교하고, 드릴다운 필터는 절대 받지 않는다(사용자 확인: "팀단위 비교").
"""
import uuid

import pytest

from app.db import Database
from app.services.pl_item_analysis import (
    PL_NARRATIVE_ITEM_KEYS,
    find_pl_item_deviations,
    find_team_item_deviation,
    format_pl_item_comment,
)

FORBIDDEN_WORDS = ["때문", "원인", "인해", "탓"]


@pytest.fixture()
def db():
    database = Database(":memory:")
    yield database
    database.close()


def _make_batch(db, year, month) -> str:
    batch_id = "batch-1"
    db.connection.execute(
        "INSERT INTO upload_batch (batch_id, upload_date, target_year, target_month) VALUES (?, ?, ?, ?)",
        [batch_id, "2026-08-01", year, month],
    )
    return batch_id


def _insert_refined_row(db, batch_id, year, month, team, *, quantity, sales_final, cogs_final):
    db.connection.execute(
        """
        INSERT INTO refined_sales_record (
            record_id, batch_id, file_id, year, month, team, customer_code, customer_name,
            product_code, product_desc, product_group, product_group_1, product_group_2, is_mapped,
            sales_final, quantity, cogs_final, is_calc_error
        ) VALUES (?, ?, 'file-1', ?, ?, ?, 'C0000001', 'test',
                   'P0001', 'desc', 'GB 소형', 'GB', 'GB 소형계열', true,
                   ?, ?, ?, false)
        """,
        [str(uuid.uuid4()), batch_id, year, month, team, sales_final, quantity, cogs_final],
    )


def _insert_plan(db, team, year, month, account_item, amount):
    db.connection.execute(
        "INSERT INTO team_pl_record (record_id, file_id, batch_id, team, account_item, year, month, amount)"
        " VALUES (?, 'file-1', 'batch-1', ?, ?, ?, ?, ?)",
        [str(uuid.uuid4()), team, account_item, year, month, amount],
    )


def test_pl_narrative_item_keys_matches_user_confirmed_15_item_list():
    # 사용자가 명시적으로 한정한 15개 항목(재료비/노무비/경비/판관비 세부 소계 +
    # 매출원가/판관비 계 + 단위당 매출액) — 상위 소계("재료비 계"/"노무비 계"/
    # "경비 계"/"총원가")와 수량/영업이익은 제외한다.
    assert PL_NARRATIVE_ITEM_KEYS == {
        "raw_material_total", "main_material_total", "other_material_supplies",
        "other_material_etc", "labor_direct", "labor_indirect", "expense_variable",
        "expense_fixed", "expense_outsourcing", "other_cogs", "sga_variable",
        "sga_fixed", "cogs_final", "sga_final", "sales_final",
    }
    assert "quantity" not in PL_NARRATIVE_ITEM_KEYS
    assert "operating_profit_final" not in PL_NARRATIVE_ITEM_KEYS
    assert "material_total" not in PL_NARRATIVE_ITEM_KEYS
    assert "labor_total" not in PL_NARRATIVE_ITEM_KEYS
    assert "expense_total" not in PL_NARRATIVE_ITEM_KEYS
    assert "total_cost" not in PL_NARRATIVE_ITEM_KEYS


def test_find_pl_item_deviations_only_team_level_ignores_drilldown(db):
    batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", quantity=100, sales_final=1_000_000, cogs_final=555_000)
    _insert_plan(db, "차량대리점", 2026, 7, "매출수량", 100)
    _insert_plan(db, "차량대리점", 2026, 7, "매출원가(A)Tot", 500_000)  # +11%

    deviations = find_pl_item_deviations(db, batch_id, threshold_pct=10.0)
    cogs_devs = [d for d in deviations if d.key == "cogs_final"]
    assert len(cogs_devs) == 1
    dev = cogs_devs[0]
    assert dev.team == "차량대리점"
    assert dev.plan_total == pytest.approx(500_000)
    assert dev.actual_total == pytest.approx(555_000)
    assert dev.diff_total == pytest.approx(55_000)
    assert dev.change_rate_pct == pytest.approx(11.0)
    assert dev.plan_unit == pytest.approx(5_000)  # 500,000 / 100
    assert dev.actual_unit == pytest.approx(5_550)  # 555,000 / 100


def test_find_pl_item_deviations_under_threshold_excluded(db):
    batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", quantity=100, sales_final=1_000_000, cogs_final=505_000)
    _insert_plan(db, "차량대리점", 2026, 7, "매출원가(A)Tot", 500_000)  # +1%

    deviations = find_pl_item_deviations(db, batch_id, threshold_pct=10.0)
    assert not [d for d in deviations if d.key == "cogs_final"]


def test_find_team_item_deviation_recomputes_by_team_and_label(db):
    batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", quantity=100, sales_final=1_000_000, cogs_final=555_000)
    _insert_plan(db, "차량대리점", 2026, 7, "매출수량", 100)
    _insert_plan(db, "차량대리점", 2026, 7, "매출원가(A)Tot", 500_000)

    dev = find_team_item_deviation(db, batch_id, "차량대리점", "매출원가")
    assert dev is not None
    assert dev.diff_total == pytest.approx(55_000)

    assert find_team_item_deviation(db, batch_id, "차량대리점", "존재하지않는항목") is None


def test_format_pl_item_comment_includes_unit_and_total_and_ratio_without_forbidden_words(db):
    batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", quantity=100, sales_final=1_000_000, cogs_final=555_000)
    _insert_plan(db, "차량대리점", 2026, 7, "매출수량", 100)
    _insert_plan(db, "차량대리점", 2026, 7, "매출원가(A)Tot", 500_000)

    dev = find_team_item_deviation(db, batch_id, "차량대리점", "매출원가")
    comment = format_pl_item_comment(dev)

    assert "차량대리점" in comment
    assert "매출원가" in comment
    assert "단위당" in comment
    assert "5,000" in comment  # 계획 단위당
    assert "5,550" in comment  # 실적 단위당
    assert "55,000" in comment  # 총액 차이
    assert "11.0%" in comment
    # Phase 21(.docs/phase/phase_21_코멘트조사자동화및방어처리.md) — "매출원가"는 받침이
    # 없어 "는"이 맞다("은(는)" 그대로 노출하던 이전 문구가 아니어야 한다).
    assert "매출원가는" in comment
    assert "은(는)" not in comment
    for word in FORBIDDEN_WORDS:
        assert word not in comment


def test_format_pl_item_comment_falls_back_to_total_only_when_quantity_zero(db):
    batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", quantity=0, sales_final=1_000_000, cogs_final=555_000)
    _insert_plan(db, "차량대리점", 2026, 7, "매출원가(A)Tot", 500_000)

    dev = find_team_item_deviation(db, batch_id, "차량대리점", "매출원가")
    assert dev.plan_unit is None and dev.actual_unit is None

    comment = format_pl_item_comment(dev)
    assert "단위당" not in comment


# ── "단위당 매출액"만 총액이 아니라 단위당 기준으로 판정하는 예외 케이스 ──
# (사용자 확인: "이상징후 하이라이트에서는 손익항목 계획대비는... 단위당 매출액으로
# 항목 한정" — 매출액 총액은 이미 다른 F3 기준이 다루므로 여기서는 단위당 판가만 본다)


def test_sales_final_deviation_is_judged_by_unit_price_not_total(db):
    batch_id = _make_batch(db, 2026, 7)
    # 총액은 계획(1,000,000) 대비 실적(1,050,000)으로 +5%(총액 기준으로는 임계치 10% 미달)
    # 이지만, 수량이 계획보다 훨씬 늘어 단위당 판가는 계획 10,000원 대비 실적 8,000원으로
    # -20%(단위당 기준 임계치 10% 초과) — 단위당 기준으로 판정해야 이 케이스가 잡힌다.
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", quantity=131.25, sales_final=1_050_000, cogs_final=0)
    _insert_plan(db, "차량대리점", 2026, 7, "매출수량", 100)
    _insert_plan(db, "차량대리점", 2026, 7, "매출액(Total)", 1_000_000)

    deviations = find_pl_item_deviations(db, batch_id, threshold_pct=10.0)
    sales_devs = [d for d in deviations if d.key == "sales_final"]
    assert len(sales_devs) == 1
    dev = sales_devs[0]
    assert dev.plan_unit == pytest.approx(10_000)
    assert dev.actual_unit == pytest.approx(8_000)
    assert dev.change_rate_pct == pytest.approx(-20.0)  # 단위당 기준(총액 기준 +5%가 아님)


def test_sales_final_comment_only_mentions_unit_price(db):
    batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", quantity=131.25, sales_final=1_050_000, cogs_final=0)
    _insert_plan(db, "차량대리점", 2026, 7, "매출수량", 100)
    _insert_plan(db, "차량대리점", 2026, 7, "매출액(Total)", 1_000_000)

    dev = find_team_item_deviation(db, batch_id, "차량대리점", "매출액")
    comment = format_pl_item_comment(dev)

    assert "단위당 매출액" in comment
    assert "10,000" in comment
    assert "8,000" in comment
    assert "-20.0%" in comment
    # 총액/비중 문장은 만들지 않는다(매출액 총액은 다른 F3 기준이 이미 다룸).
    assert "총액 기준으로는" not in comment
    assert "비중은" not in comment
    # Phase 21 — "액"은 받침이 있어 "은"이 맞다.
    assert "단위당 매출액은" in comment
    assert "은(는)" not in comment
    for word in FORBIDDEN_WORDS:
        assert word not in comment


def test_sales_final_without_quantity_plan_is_not_judged(db):
    # 계획 쪽 "매출수량"이 없으면(plan_unit 계산 불가) 단위당 판정 자체가 불가능하므로
    # 아무 것도 플래그하지 않는다(0으로 대체하지 않음).
    batch_id = _make_batch(db, 2026, 7)
    _insert_refined_row(db, batch_id, 2026, 7, "차량대리점", quantity=100, sales_final=2_000_000, cogs_final=0)
    _insert_plan(db, "차량대리점", 2026, 7, "매출액(Total)", 1_000_000)

    deviations = find_pl_item_deviations(db, batch_id, threshold_pct=10.0)
    assert not [d for d in deviations if d.key == "sales_final"]
