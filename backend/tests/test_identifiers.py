import pytest

from app.services.identifiers import (
    apply_cell_22_9_conversion,
    apply_quantity_exception,
    parse_customer,
    parse_product,
    parse_profit_center,
)


def test_parse_customer_matches_verified_excel_example():
    code, name = parse_customer("210111x    가나자동차 주식회사(GN Motors C")
    assert code == "210111x"
    assert name == "가나자동차 주식회사(GN Motors C"


def test_parse_product_matches_verified_excel_example():
    code, desc = parse_product("PCC01179           GB 400R(GN)(BCI-BH)")
    assert code == "PCC01179"
    assert desc == "GB 400R(GN)(BCI-BH)"


def test_quantity_exception_r_prefix_zeroes_out():
    assert apply_quantity_exception("R00012345", 8) == 0.0


def test_quantity_exception_qzz_prefix_zeroes_out():
    assert apply_quantity_exception("QZZ123", 4) == 0.0


def test_quantity_exception_normal_code_unaffected():
    assert apply_quantity_exception("PCC01179", 5) == 5.0


def test_parse_profit_center_extracts_leading_5_digit_code_from_composite_value():
    # 실제 운영 파일(2026-08 Raw Data)에서 확인된 형식 — 코드 뒤에 설명 텍스트가 붙는다.
    assert parse_profit_center("20342 모티브사업부") == 20342


def test_parse_profit_center_accepts_plain_numeric_string():
    # 테스트 픽스처처럼 설명 없이 코드만 있는 경우도 그대로 지원해야 한다.
    assert parse_profit_center("20313") == 20313


def test_parse_profit_center_accepts_plain_int():
    assert parse_profit_center(20345) == 20345


def test_parse_profit_center_rejects_non_numeric_prefix():
    with pytest.raises(ValueError):
        parse_profit_center("모티브사업부")


def test_cell_22_9_conversion_applies_only_to_v_battery_set():
    # 실제 운영 파일(2026-08) BZ열 "수량(22.9cell)" 검증 결과 (.docs/03_데이터정제.md §4.7)
    assert apply_cell_22_9_conversion("V전지:Set", 3) == pytest.approx(3 * 22.9)


def test_cell_22_9_conversion_applies_to_v_battery_set_oe_variant():
    # 실제 수식(클로드 실적 데이터 분석용_2.xlsx) 확인 결과 "V전지:set/oe"도 트리거된다.
    assert apply_cell_22_9_conversion("V전지:set/oe", 2) == pytest.approx(2 * 22.9)


def test_cell_22_9_conversion_is_case_insensitive():
    # 엑셀 문자열 비교는 기본적으로 대소문자를 가리지 않는다 — 실제 수식이
    # `=IF(OR(N="V전지:SET", N="V전지:set/oe"), ...)`로 대문자 SET을 쓴다.
    assert apply_cell_22_9_conversion("V전지:SET", 3) == pytest.approx(3 * 22.9)
    assert apply_cell_22_9_conversion("v전지:set", 3) == pytest.approx(3 * 22.9)


def test_cell_22_9_conversion_leaves_other_groups_unchanged():
    assert apply_cell_22_9_conversion("GB 소형", 5) == 5
    assert apply_cell_22_9_conversion(None, 5) == 5
