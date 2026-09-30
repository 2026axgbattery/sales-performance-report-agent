import pandas as pd
import pytest

from app.services.mapping import ProductMappingTable
from app.services.refinement import RawColumnValidationError, refine_actual_records
from tests.conftest import FIXTURES_DIR


@pytest.fixture()
def mapping_table():
    df = pd.read_csv(FIXTURES_DIR / "mapping_sample.csv", dtype=str)
    return ProductMappingTable.from_dataframe(df)


@pytest.fixture()
def actual_df():
    return pd.read_csv(FIXTURES_DIR / "actual_sample.csv", dtype=str, keep_default_na=False, na_values=[""])


def test_refine_matches_verified_excel_row1(actual_df, mapping_table):
    """docs/03_데이터정제.md §4 Row4(PCC01179) 실제 Re-arrange 결과와 대조."""
    result = refine_actual_records(actual_df, mapping_table)
    row = result.rows[0]

    assert (row.year, row.month) == (2026, 7)
    assert row.team == "차량대리점"
    assert row.customer_code == "210111x"
    assert row.product_code == "PCC01179"
    assert row.product_group == "GB 소형"
    assert row.is_mapped is True

    assert row.sales_adjustment == pytest.approx(0)  # K = L-I-J = 177885-159935-17950
    assert row.raw_material_total == pytest.approx(82083)  # V
    assert row.main_material_total == pytest.approx(17745)  # Z
    assert row.operating_profit_pre_adjust == pytest.approx(10227)  # BM
    assert row.operating_profit_final == pytest.approx(10227)  # BN
    assert row.quantity == pytest.approx(5)
    assert row.is_calc_error is False


def test_refine_matches_verified_excel_row2(actual_df, mapping_table):
    """docs/03_데이터정제.md §4 Row5(PCC04736) 실제 Re-arrange 결과와 대조."""
    result = refine_actual_records(actual_df, mapping_table)
    row = result.rows[1]

    assert row.team == "차량대리점"
    assert row.product_group == "GB 소형"
    assert row.raw_material_total == pytest.approx(199768)
    assert row.main_material_total == pytest.approx(38638)
    assert row.operating_profit_pre_adjust == pytest.approx(169762)
    assert row.operating_profit_final == pytest.approx(169762)
    assert row.quantity == pytest.approx(10)


def test_refine_applies_san_jeon_mapping_prefix_for_motive_team(actual_df, mapping_table):
    """모티브 팀(20342)은 매핑표 조회 시 '산전' 접두사를 사용한다 (검증된 quirk)."""
    result = refine_actual_records(actual_df, mapping_table)
    row = result.rows[2]

    assert row.team == "모티브"
    assert row.is_mapped is True
    assert row.product_group == "원자재"


def test_refine_flags_unmapped_product_without_dropping_it(actual_df, mapping_table):
    result = refine_actual_records(actual_df, mapping_table)
    row = result.rows[3]

    assert row.product_code == "XPZ99999"
    assert row.is_mapped is False
    assert row.product_group is None
    # 미매핑이어도 집계에서 제외하지 않는다 (PRD F2 요구사항)
    assert row in result.rows


def test_refine_applies_quantity_exception_for_r_prefixed_code_and_defaults_team(actual_df, mapping_table):
    result = refine_actual_records(actual_df, mapping_table)
    row = result.rows[4]

    assert row.product_code.startswith("R")
    assert row.quantity == 0.0  # 원본 매출수량 8 -> 예외 규칙으로 0
    assert row.team == "차량OE"  # 손익센터 99999는 else 분기


def test_unmapped_and_total_counts(actual_df, mapping_table):
    result = refine_actual_records(actual_df, mapping_table)
    assert result.total_count == 5
    assert result.unmapped_count == 2  # XPZ99999, R00012345


def test_refine_flags_blank_period_as_calc_error_without_crashing(actual_df, mapping_table):
    """실사용 중 실제로 발견된 크래시 — "기간/연도" 값이 비어있는(NaN) 행이 있으면
    전체 업로드가 500 에러로 죽었었다. 이제는 그 행만 계산오류로 표시하고 계속 진행한다."""
    df = actual_df.copy()
    df.loc[0, "기간/연도"] = ""

    result = refine_actual_records(df, mapping_table)
    row = result.rows[0]

    assert row.year == 0
    assert row.month == 0
    assert row.is_calc_error is True
    assert "기간" in row.calc_error_reason
    # 나머지 행은 영향받지 않는다
    assert result.rows[1].is_calc_error is False


def test_refine_raises_on_missing_required_columns(mapping_table):
    df = pd.read_csv(FIXTURES_DIR / "actual_missing_column.csv", dtype=str)
    with pytest.raises(RawColumnValidationError):
        refine_actual_records(df, mapping_table)


def test_refine_applies_22_9_cell_conversion_for_motive_v_battery_set(actual_df, mapping_table):
    """실제 운영 파일(2026-08) BZ열 "수량(22.9cell)" 검증 결과 — 모티브팀
    제품구분1(보고4용)="V전지:Set" 제품만 매출수량 x 22.9로 환산되고,
    그 외 제품은 매출수량과 동일하다 (.docs/03_데이터정제.md §4.7)."""
    row_dict = actual_df.iloc[0].to_dict()
    row_dict["상품"] = "PIJ00484T          VCD250-12V,W,12.0 V"
    row_dict["손익 센터"] = "20342"
    row_dict["매출수량"] = "3"
    df = pd.concat([actual_df, pd.DataFrame([row_dict])], ignore_index=True)

    result = refine_actual_records(df, mapping_table)
    row = result.rows[-1]

    assert row.team == "모티브"
    assert row.product_group == "V전지:Set"
    assert row.quantity_raw == pytest.approx(3)
    assert row.quantity == pytest.approx(3 * 22.9)


def test_refine_leaves_non_v_battery_set_quantity_unconverted(actual_df, mapping_table):
    result = refine_actual_records(actual_df, mapping_table)
    row = result.rows[0]

    assert row.product_group == "GB 소형"
    assert row.quantity_raw == pytest.approx(5)
    assert row.quantity == pytest.approx(5)  # V전지:Set이 아니므로 환산 없음


def test_refine_computes_verified_material_labor_expense_sga_subtotals(actual_df, mapping_table):
    """노무비·경비·판관비 세부 합산 규칙 — 실제 파일(2026-08 과제용) Raw Data와
    Re-arrange용 수식 시트를 6029행 전수 대조해 검증한 공식(불일치 0건)을
    그대로 재현한다 (.docs/phase/phase_11_팀별손익계산서비교.md)."""
    df = actual_df.copy()
    df.loc[0, "부재료비(A)"] = "100"
    df.loc[0, "포장비(A)"] = "10"
    df.loc[0, "부대품재료비(A)"] = "20"
    df.loc[0, "부산물공제(A)"] = "5"
    df.loc[0, "변동직접노무비(A)"] = "200"
    df.loc[0, "고정직접노무비(A)"] = "300"
    df.loc[0, "간접노무비(A)"] = "150"
    df.loc[0, "변동경비(A)"] = "40"
    df.loc[0, "고정경비(A)"] = "60"
    df.loc[0, "외주가공비(A)"] = "10"
    df.loc[0, "차량유지비"] = "1"
    df.loc[0, "운반비"] = "2"
    df.loc[0, "수출비용(A)"] = "3"
    df.loc[0, "시험설치비(A)"] = "4"
    df.loc[0, "판매보증비"] = "5"
    df.loc[0, "불량제품손실"] = "6"
    df.loc[0, "수출비용_해상운임("] = "7"
    df.loc[0, "임원급여"] = "10"
    df.loc[0, "직원급여"] = "20"
    df.loc[0, "임원상여"] = "1"
    df.loc[0, "직원상여"] = "2"
    df.loc[0, "임금"] = "0"
    df.loc[0, "제수당"] = "0"
    df.loc[0, "잡급"] = "0"
    df.loc[0, "퇴직급여"] = "3"
    df.loc[0, "대손상각비"] = "0"
    df.loc[0, "복리후생비"] = "8"
    df.loc[0, "접대비(A)"] = "9"
    df.loc[0, "지급수수료"] = "11"
    df.loc[0, "여비교통비"] = "1"
    df.loc[0, "통신비"] = "1"

    result = refine_actual_records(df, mapping_table)
    row = result.rows[0]

    assert row.other_material_supplies == pytest.approx(100)
    assert row.other_material_etc == pytest.approx(10 + 20 + 5)
    assert row.material_total == pytest.approx(
        row.raw_material_total + row.main_material_total + 100 + (10 + 20 + 5)
    )
    assert row.labor_variable_direct == pytest.approx(200)
    assert row.labor_fixed_direct == pytest.approx(300)
    assert row.labor_direct == pytest.approx(200 + 300)
    assert row.labor_total == pytest.approx(200 + 300 + 150)
    assert row.expense_total == pytest.approx(40 + 60 + 10)
    assert row.sga_vehicle == pytest.approx(1)
    assert row.sga_delivery == pytest.approx(2)
    assert row.sga_export == pytest.approx(3)
    assert row.sga_installation == pytest.approx(4)
    assert row.sga_warranty == pytest.approx(5)
    assert row.sga_defect_loss == pytest.approx(6)
    assert row.sga_ocean_freight == pytest.approx(7)
    assert row.sga_variable == pytest.approx(1 + 2 + 3 + 4 + 5 + 6 + 7)
    assert row.sga_personnel == pytest.approx(10 + 20 + 1 + 2 + 3)
    assert row.sga_fixed == pytest.approx(
        row.sga_personnel + 8 + 9 + 11 + row.sga_other
    )


def test_refine_puts_daesonsangakbi_in_sga_other_not_personnel(actual_df, mapping_table):
    """실제 수식(클로드 실적 데이터 분석용_2.xlsx) 확인 결과 판관인건비는 8개 항목
    (임원급여~퇴직급여)뿐이고, 대손상각비는 "기타-판관비" 잔여값 쪽으로 들어간다 —
    이전엔 판관인건비 9번째 항목으로 잘못 합산하고 있었다."""
    df = actual_df.copy()
    df.loc[0, "대손상각비"] = "999"

    result = refine_actual_records(df, mapping_table)
    row = result.rows[0]

    assert 999 not in [row.sga_personnel]
    assert row.sga_other >= 999
    # 대손상각비를 제외한 나머지 판관인건비 항목은 원래 픽스처 그대로 0이어야 한다
    assert row.sga_personnel == pytest.approx(0)


def test_refine_handles_real_world_profit_center_composite_value(actual_df, mapping_table):
    # 실제 운영 파일(2026-08 Raw Data)에서 확인된 형식 — "손익 센터" 값이 순수 정수가
    # 아니라 "코드+설명" 합성 형식이다. 픽스처는 순수 코드만 담고 있어, 실제 형식으로
    # 바꿔도 팀 분류 결과가 그대로인지 확인한다.
    df = actual_df.copy()
    df["손익 센터"] = df["손익 센터"] + " 테스트사업부"

    result = refine_actual_records(df, mapping_table)
    assert result.rows[0].team == "차량대리점"  # 원래 20313 코드와 동일하게 분류됨


def test_refine_uses_division_column_when_profit_center_absent(actual_df, mapping_table):
    """일부 실적 파일("Raw Data_업로드용.xlsb")은 "손익 센터"가 아니라 "부문" 컬럼으로
    팀을 구분한다(.docs/03_데이터정제.md §4.1 확장, 08월 실제 파일 7676행 전체 검증됨).
    두 컬럼 방식을 모두 지원하기로 확정했다(사용자 확인)."""
    df = actual_df.drop(columns=["손익 센터"])
    df["부문"] = [
        "2630 차량대리점팀",  # 원래 20313 -> 차량대리점
        "2630 차량대리점팀",  # 원래 20313 -> 차량대리점
        "2620 산전모티브팀",  # 원래 20342 -> 모티브
        "2630 차량대리점팀",  # 원래 20313 -> 차량대리점
        "2640 차량OE팀",  # 원래 99999(기타) -> 차량OE
    ]

    result = refine_actual_records(df, mapping_table)

    assert result.rows[0].team == "차량대리점"
    assert result.rows[2].team == "모티브"
    assert result.rows[2].is_mapped is True  # 산전 접두사 매핑도 그대로 동작
    assert result.rows[4].team == "차량OE"
    assert all(not r.is_calc_error for r in result.rows)


def test_refine_flags_unknown_division_value_as_calc_error(actual_df, mapping_table):
    df = actual_df.drop(columns=["손익 센터"])
    df["부문"] = "9999 알수없는팀"

    result = refine_actual_records(df, mapping_table)
    row = result.rows[0]

    assert row.team == "차량OE"  # DEFAULT_TEAM으로 계속 진행 (배치 전체를 크래시시키지 않음)
    assert row.is_calc_error is True
    assert "부문" in row.calc_error_reason


def test_validate_raw_columns_requires_profit_center_or_division(actual_df, mapping_table):
    df = actual_df.drop(columns=["손익 센터"])
    with pytest.raises(RawColumnValidationError) as exc_info:
        refine_actual_records(df, mapping_table)
    assert "손익 센터" in str(exc_info.value)
    assert "부문" in str(exc_info.value)
