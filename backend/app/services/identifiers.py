"""'상품', '고객', '손익 센터' 원본 필드의 코드+명칭 파싱.

docs/03_데이터정제.md §4.1:
  거래처코드 = LEFT(고객, 7)
  고객(명)   = SUBSTITUTE(SUBSTITUTE(고객, 거래처코드, ""), "    ", "")
  상품(코드) = TRIM(LEFT(상품, 11))
  DESC      = TRIM(SUBSTITUTE(상품, 상품코드, ""))

'손익 센터'도 같은 "코드+설명" 패턴이다 — 실제 운영 파일(2026-08)에서 값 앞
5자리 숫자가 손익센터 코드이고 뒤에 설명 텍스트가 붙는 것을 사용자가 확인해줬다
(§4.1에서 검증했던 07월 참고 파일은 순수 정수였는데, 실제 운영 파일은 이 패턴이다).
"""
from __future__ import annotations


def parse_customer(raw_customer: str) -> tuple[str, str]:
    """원본 '고객' 필드 -> (거래처코드, 고객명)"""
    raw_customer = raw_customer or ""
    code = raw_customer[:7]
    name = raw_customer.replace(code, "", 1).replace("    ", "").strip()
    return code, name


def parse_product(raw_product: str) -> tuple[str, str]:
    """원본 '상품' 필드 -> (제품코드, DESC)"""
    raw_product = raw_product or ""
    code = raw_product[:11].strip()
    desc = raw_product.replace(code, "", 1).strip()
    return code, desc


def parse_profit_center(raw_value) -> int:
    """원본 '손익 센터' 필드 -> 손익센터 코드(정수). 값 앞 5자리 숫자가 코드다."""
    if isinstance(raw_value, bool):
        raise ValueError(f"손익 센터 값이 올바르지 않습니다: {raw_value!r}")
    if isinstance(raw_value, (int, float)):
        return int(raw_value)
    text = str(raw_value).strip()
    code = text[:5]
    if not code.isdigit():
        raise ValueError(f"손익 센터 값에서 5자리 코드를 찾을 수 없습니다: {raw_value!r}")
    return int(code)


# 매출수량 예외 규칙 (docs/03_데이터정제.md §4.6): R 또는 QZZ로 시작하는 제품코드는 매출수량을 0으로 처리
_ZERO_QUANTITY_PREFIXES = ("R", "QZZ")


def apply_quantity_exception(product_code: str, raw_quantity: float) -> float:
    if product_code and (product_code.startswith("QZZ") or product_code.startswith("R")):
        return 0.0
    return float(raw_quantity)


# 수량(22.9cell) 환산 (docs/03_데이터정제.md §4.7): 실제 운영 파일(2026-08) BZ열에서
# 확인됨 — 전체 6029행 중 제품구분1(보고4용)="V전지:Set"(모티브팀 지게차용 배터리)인
# 546행만 매출수량 × 22.9로 환산되고, 그 외 모든 행은 매출수량과 동일(환산 없음).
# Raw Data의 용량(단위당)/연량(단위당) 등 어떤 컬럼에도 22.9라는 값이 없어(PIJ 계열
# 확인 결과 250~950V 등 전압값), 특정 제품 속성에서 유도되는 값이 아니라 "V전지:Set"
# 제품군 전체에 적용되는 고정 환산 계수로 판단된다.
#
# `클로드 실적 데이터 분석용_2.xlsx`의 실제 수식(캐시값이 아니라 수식 원문을 그대로
# 읽은 것)으로 재검증한 결과, 조건이 `=IF(OR(N="V전지:SET", N="V전지:set/oe"), ...)`다.
# 즉 (1) 대소문자를 안 가린다(엑셀의 문자열 비교는 기본적으로 대소문자 무시) — 파이썬은
# 대소문자를 가리므로 대소문자 무시 비교로 맞춰야 한다. (2) "V전지:Set" 외에
# "V전지:set/oe"라는 두 번째 트리거 값이 있다 — 이전엔 한 파일에서만 확인해 놓쳤다.
_CELL_22_9_PRODUCT_GROUPS = ("v전지:set", "v전지:set/oe")
_CELL_22_9_RATIO = 22.9


def apply_cell_22_9_conversion(product_group_1: str | None, quantity: float) -> float:
    if product_group_1 is not None and product_group_1.strip().lower() in _CELL_22_9_PRODUCT_GROUPS:
        return quantity * _CELL_22_9_RATIO
    return quantity
