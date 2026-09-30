"""F2. 데이터 정제 및 매핑 — 실적 Raw Data -> 정제된 실적 레코드.

이 모듈은 docs/03_데이터정제.md §4에서 검증한 "실적 Re-arrange용 수식" 시트의
컬럼별 산출 규칙을 파이썬으로 포팅한 것이다. 68개 전체 계정과목 중,
6가지 패턴(①원본 복사 ②식별자 파싱 ③코드매핑 ④VLOOKUP매핑 ⑤합산/차감/역산
⑥최종 손익 계산)을 모두 대표할 수 있는 핵심 컬럼만 우선 구현했다
(매출, 원재료비, 주재료비, 최종 손익, 매출수량 예외 규칙, 수량(22.9cell) 환산).

노무비·경비·판관비 세부 항목(§4.4·§4.5, .docs/phase/phase_11_팀별손익계산서비교.md)은
실제 파일(2026-08 과제용) Raw Data + Re-arrange용 수식 두 시트를 행 단위로
대조해 아래 합산 규칙 전부를 6029행 전수 검증(불일치 0건)했다 — 임의 추정이 아니다.
`클로드 실적 데이터 분석용_2.xlsx`(수식 원문을 그대로 담고 있는 파일)로 재검증해
판관인건비 항목 수를 8개로 정정했다(대손상각비는 여기 포함되지 않고 "기타-판관비"
쪽으로 흡수된다 — 실제 수식이 "기타-판관비 = 고정판관비 - (판관인건비+복리후생비+
접대비+지급수수료)" 잔여값이라 대손상각비가 자동으로 여기 남기 때문):
  - 재료비 계 = 원재료비 계 + 주재료비 계 + 부재료비 + 기타재료비(포장비+부대품재료비+부산물공제)
  - 노무비 계 = 직접노무비(변동직접+고정직접) + 간접노무비
  - 경비 계 = 변동경비 + 고정경비 + 외주가공비
  - 변동판관비 = 차량유지비+운반비+수출비용(A)+시험설치비(A)+판매보증비+불량제품손실+수출비용_해상운임(
  - 판관인건비 = 임원급여+직원급여+임원상여+직원상여+임금+제수당+잡급+퇴직급여 (8개 항목)
  - 고정판관비 = 판관인건비+복리후생비+접대비(A)+지급수수료+기타-판관비(대손상각비 포함 18개 항목 합)
  - 판관비(조정전) = 변동판관비 + 고정판관비 (기존 sga_pre_adjust=Raw!판관비A(조정전)와 동일 값)
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

import pandas as pd

from app.services.branch import BranchMappingTable
from app.services.identifiers import (
    apply_cell_22_9_conversion,
    apply_quantity_exception,
    parse_customer,
    parse_product,
    parse_profit_center,
)
from app.services.mapping import ProductMappingTable
from app.services.period import PeriodParseError, parse_period
from app.services.team import DEFAULT_TEAM, classify_team, classify_team_from_division

# Raw Data 시트에서 이 파이프라인이 실제로 사용하는 컬럼 (docs/03_데이터정제.md §2, §5 근거)
# "손익 센터"는 REQUIRED_RAW_COLUMNS에 넣지 않는다 — 실적 파일에 따라 "손익 센터" 또는
# "부문" 둘 중 하나로 팀을 구분하며(.docs/03_데이터정제.md §4.1 확장), TEAM_SOURCE_COLUMNS로
# 별도 검증한다.
TEAM_SOURCE_COLUMNS = ("손익 센터", "부문")

REQUIRED_RAW_COLUMNS = [
    "상품",
    "고객",
    "기간/연도",
    "매출액(Total)",
    "매출원가(A)Tot",
    # 표준매출원가(Phase 14, .docs/phase/phase_14_월별실적분석탭.md) — 지금까지는 Actual(A)
    # 계열만 채택했는데(.docs/03_데이터정제.md §2.3 "Standard(S) vs Actual(A) 이중 원가 체계"),
    # 사용자가 "표준매출원가는 실적 파일에 이미 있는 컬럼"이라고 확인해 Standard(S) 계열의
    # 매출원가(A)Tot과 정확히 대응하는 컬럼을 그대로 단순 복사해 추가한다.
    "매출원가(S)Tot",
    "매출액",
    "기타매출액",
    "제품매출조정",
    "매출액A(조정전)",
    "매출원가A(조정전)",
    "판관비A(조정전)",
    "재고실사차이",
    "매출수량",
    "원재료비_순연(A)",
    "원재료비_경연(A)",
    "원재료비_칼슘연(A",  # 실제 운영 파일 헤더에 닫는 괄호가 없다 — 사용자가 셀 내용을 직접 확인해줌
    "원재료비_니켈(A)",
    "원재료비_리튬(A)",
    "주재료비_전조(A)",
    "주재료비_카바(A)",
    "주재료비_격리판(A",  # 위와 동일한 이유로 닫는 괄호 없음
    "총매출액",
    "매출할인",
    "판관비(Total)",
    # 재료비 계 세부 (기타재료비 = 포장비+부대품재료비+부산물공제, 부재료비는 별도)
    "부재료비(A)",
    "포장비(A)",
    "부대품재료비(A)",
    "부산물공제(A)",
    # 노무비 계 세부
    "변동직접노무비(A)",
    "고정직접노무비(A)",
    "간접노무비(A)",
    # 경비 계 세부
    "변동경비(A)",
    "고정경비(A)",
    "외주가공비(A)",
    # 변동판관비 세부
    "차량유지비",
    "운반비",
    "수출비용(A)",
    "시험설치비(A)",
    "판매보증비",
    "불량제품손실",
    "수출비용_해상운임(",  # 실제 운영 파일 헤더에 닫는 괄호가 없다
    # 판관인건비 세부
    "임원급여",
    "직원급여",
    "임원상여",
    "직원상여",
    "임금",
    "제수당",
    "잡급",
    "퇴직급여",
    "대손상각비",
    # 고정판관비 세부 (판관인건비 제외)
    "복리후생비",
    "접대비(A)",
    "지급수수료",
    # 기타-판관비 세부 (18개 합산)
    "여비교통비",
    "통신비",
    "소모품비",
    "도서인쇄비",
    "세금과공과",
    "임차료",
    "수도광열비",
    "광고선전비",
    "교육훈련비",
    "감가상각비",
    "무형자산상각비",
    "수선유지비",
    "보험료",
    "회의비",
    "경상연구개발비",
    "연구개발비(국책과제",  # 실제 운영 파일 헤더에 닫는 괄호가 없다
    "대손충당금환입",
    "판관비_기타",
]


class RawColumnValidationError(ValueError):
    def __init__(self, missing_columns: list[str]):
        self.missing_columns = missing_columns
        super().__init__(f"실적 파일에 다음 컬럼이 없습니다: {missing_columns}")


def validate_raw_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_RAW_COLUMNS if c not in df.columns]
    if not any(c in df.columns for c in TEAM_SOURCE_COLUMNS):
        missing.append(" 또는 ".join(TEAM_SOURCE_COLUMNS))
    if missing:
        raise RawColumnValidationError(missing)


@dataclass
class RefinedRow:
    year: int
    month: int
    team: str
    customer_code: str
    customer_name: str
    product_code: str
    product_desc: str
    product_group: str | None  # 제품구분3(계획비교용)
    product_group_1: str | None  # 제품구분1(보고4용) — F4 드릴다운 필터용
    product_group_2: str | None  # 제품구분2(보고3용) — F4 드릴다운 필터용
    is_mapped: bool
    region: str | None  # 권역 (지점코드 매핑, .docs/03_데이터정제.md §3.5)
    office: str | None  # 사업소
    part: str | None  # 파트
    is_branch_mapped: bool
    # 매출
    sales_provisional: float  # 영업-가마감매출 (I)
    sales_discount: float  # 영업-매출할인 (J)
    sales_adjustment: float  # 영업-마감매출조정 (K = L-I-J)
    sales_final_ops: float  # 영업-정마감매출 (L)
    sales_other: float  # 영업-기타매출액 (M)
    sales_pre_adjust: float  # 영업-매출액(조정전) (N)
    plan_adjustment: float  # 기획-매출조정 (O)
    sales_final: float  # 기획-매출액(최종마감) (P)
    # 원재료비
    raw_material_sunyeon: float
    raw_material_gyeongyeon: float
    raw_material_calcium: float
    raw_material_nickel: float
    raw_material_lithium: float
    raw_material_total: float  # V
    # 주재료비
    main_material_jeonjo: float
    main_material_kaba: float
    main_material_gyeorimpan: float
    main_material_total: float  # Z
    # 기타재료비 (부재료비 + 포장비/부대품재료비/부산물공제)
    other_material_supplies: float  # 부재료비
    other_material_etc: float  # 포장비+부대품재료비+부산물공제
    material_total: float  # 재료비 계 = 원재료비 계 + 주재료비 계 + 부재료비 + 기타재료비
    # 노무비
    labor_variable_direct: float  # 변동직접노무비
    labor_fixed_direct: float  # 고정직접노무비
    labor_direct: float  # 직접노무비 계 = 변동직접+고정직접
    labor_indirect: float  # 간접노무비
    labor_total: float  # 노무비 계
    # 경비
    expense_variable: float
    expense_fixed: float
    expense_outsourcing: float
    expense_total: float  # 경비 계
    # 판관비 세부 (변동판관비 + 고정판관비 = sga_pre_adjust)
    sga_vehicle: float  # 차량유지비
    sga_delivery: float  # 운반비
    sga_export: float  # 수출비용(A)
    sga_installation: float  # 시험설치비(A)
    sga_warranty: float  # 판매보증비
    sga_defect_loss: float  # 불량제품손실
    sga_ocean_freight: float  # 수출비용_해상운임(
    sga_variable: float  # 변동판관비 계 = 위 7개 합
    sga_personnel: float  # 판관인건비
    sga_welfare: float  # 복리후생비
    sga_entertainment: float  # 접대비(A)
    sga_fees: float  # 지급수수료
    sga_other: float  # 기타-판관비 (18개 합)
    sga_fixed: float  # 고정판관비
    # 원가/판관비 (직접 복사, 최종 손익 계산용)
    cogs_pre_adjust: float  # AS = Raw!매출원가A(조정전)
    cogs_final: float  # AU = Raw!매출원가(A)Tot
    standard_cogs: float  # Phase 14 — Raw!매출원가(S)Tot 단순 복사(표준매출원가)
    sga_pre_adjust: float  # BJ = Raw!판관비A(조정전)
    sga_final: float  # BL = Raw!판관비(Total)
    # 최종 손익
    operating_profit_pre_adjust: float  # BM = N - AS - BJ
    operating_profit_final: float  # BN = P - AU - BL
    quantity_raw: float  # BO (R/QZZ 예외 규칙만 적용, 22.9cell 환산 전)
    quantity: float  # BZ 수량(22.9cell) — 수량/손익 분석의 기본 수량 (.docs/03_데이터정제.md §4.7)
    inventory_diff: float  # BP
    is_calc_error: bool = False
    calc_error_reason: str | None = None


# refined_sales_record 테이블 컬럼 목록(record_id/batch_id/file_id 제외) — RefinedRow의
# 필드 선언 순서를 그대로 따른다. app/routers/uploads.py(INSERT)와 app/services/export.py
# (F7 "실적 Re-arrange용 수식 시트 전체" 다운로드, Phase 15)가 함께 참조하므로 여기
# 한 곳에서만 유지한다 — 두 군데서 따로 손으로 나열하면 필드 추가 시 어긋나기 쉽다.
REFINED_ROW_COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(RefinedRow))


def _num(value) -> float:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return 0.0
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value in ("", "-"):
            return 0.0
    return float(value)


def refine_row(
    raw: pd.Series,
    mapping: ProductMappingTable,
    branch_mapping: BranchMappingTable | None = None,
) -> RefinedRow:
    is_calc_error = False
    calc_error_reason: str | None = None

    # "기간/연도" 값이 비어있거나(NaN) 형식이 깨진 행이 실제로 존재하는 것을 확인했다
    # (사용자 실사용 중 500 에러로 발견). 한 행 때문에 업로드 전체가 크래시하지 않도록,
    # 파싱 실패 시 이 행만 계산오류로 표시하고 년/월은 0(더미)으로 둔다 — 0은 실제
    # 연/월 값이 될 수 없어 배치 기간 판정(uploads.py)에서 자연히 제외된다.
    try:
        year, month = parse_period(str(raw["기간/연도"]))
    except PeriodParseError as exc:
        year, month = 0, 0
        is_calc_error = True
        calc_error_reason = str(exc)

    if "손익 센터" in raw.index:
        team = classify_team(parse_profit_center(raw["손익 센터"]))
    else:
        # "손익 센터" 컬럼이 없는 실적 파일은 "부문" 컬럼으로 팀을 구분한다
        # (.docs/03_데이터정제.md §4.1 확장, 사용자 확인: 두 컬럼 방식 모두 지원).
        try:
            team = classify_team_from_division(raw["부문"])
        except ValueError as exc:
            team = DEFAULT_TEAM
            is_calc_error = True
            calc_error_reason = str(exc)
    customer_code, customer_name = parse_customer(str(raw["고객"]))
    product_code, product_desc = parse_product(str(raw["상품"]))
    product_group, is_mapped = mapping.lookup(team, product_code)
    product_group_1 = mapping.lookup_product_group_1(team, product_code)
    product_group_2 = mapping.lookup_product_group_2(team, product_code)

    # 지점코드 매핑표는 아직 F1에서 별도로 업로드되지 않을 수 있다(.docs/03_데이터정제.md
    # §3.5 — 향후 매핑표 파일에 제품분류와 함께 포함될 예정). 없으면 미매핑으로 둔다.
    if branch_mapping is not None:
        region, office, part = branch_mapping.lookup(team, customer_code)
        is_branch_mapped = region is not None
    else:
        region, office, part = None, None, None
        is_branch_mapped = False

    sales_provisional = _num(raw["총매출액"])  # I = Raw!BN
    sales_discount = _num(raw["매출할인"])  # J = Raw!BO
    sales_final_ops = _num(raw["매출액"])  # L = Raw!H
    sales_other = _num(raw["기타매출액"])  # M = Raw!I
    sales_pre_adjust = _num(raw["매출액A(조정전)"])  # N = Raw!R
    plan_adjustment = _num(raw["제품매출조정"])  # O = Raw!J
    sales_final = _num(raw["매출액(Total)"])  # P = Raw!F
    sales_adjustment = sales_final_ops - sales_provisional - sales_discount  # K = L-I-J

    raw_material_sunyeon = _num(raw["원재료비_순연(A)"])
    raw_material_gyeongyeon = _num(raw["원재료비_경연(A)"])
    raw_material_calcium = _num(raw["원재료비_칼슘연(A"])
    raw_material_nickel = _num(raw["원재료비_니켈(A)"])
    raw_material_lithium = _num(raw["원재료비_리튬(A)"])
    raw_material_total = (
        raw_material_sunyeon + raw_material_gyeongyeon + raw_material_calcium
        + raw_material_nickel + raw_material_lithium
    )

    main_material_jeonjo = _num(raw["주재료비_전조(A)"])
    main_material_kaba = _num(raw["주재료비_카바(A)"])
    main_material_gyeorimpan = _num(raw["주재료비_격리판(A"])
    main_material_total = main_material_jeonjo + main_material_kaba + main_material_gyeorimpan

    other_material_supplies = _num(raw["부재료비(A)"])
    other_material_etc = _num(raw["포장비(A)"]) + _num(raw["부대품재료비(A)"]) + _num(raw["부산물공제(A)"])
    material_total = raw_material_total + main_material_total + other_material_supplies + other_material_etc

    labor_variable_direct = _num(raw["변동직접노무비(A)"])
    labor_fixed_direct = _num(raw["고정직접노무비(A)"])
    labor_direct = labor_variable_direct + labor_fixed_direct
    labor_indirect = _num(raw["간접노무비(A)"])
    labor_total = labor_direct + labor_indirect

    expense_variable = _num(raw["변동경비(A)"])
    expense_fixed = _num(raw["고정경비(A)"])
    expense_outsourcing = _num(raw["외주가공비(A)"])
    expense_total = expense_variable + expense_fixed + expense_outsourcing

    sga_vehicle = _num(raw["차량유지비"])
    sga_delivery = _num(raw["운반비"])
    sga_export = _num(raw["수출비용(A)"])
    sga_installation = _num(raw["시험설치비(A)"])
    sga_warranty = _num(raw["판매보증비"])
    sga_defect_loss = _num(raw["불량제품손실"])
    sga_ocean_freight = _num(raw["수출비용_해상운임("])
    sga_variable = (
        sga_vehicle + sga_delivery + sga_export + sga_installation + sga_warranty + sga_defect_loss + sga_ocean_freight
    )
    sga_personnel = (
        _num(raw["임원급여"]) + _num(raw["직원급여"]) + _num(raw["임원상여"]) + _num(raw["직원상여"])
        + _num(raw["임금"]) + _num(raw["제수당"]) + _num(raw["잡급"]) + _num(raw["퇴직급여"])
    )
    sga_welfare = _num(raw["복리후생비"])
    sga_entertainment = _num(raw["접대비(A)"])
    sga_fees = _num(raw["지급수수료"])
    # 대손상각비는 실제 수식(클로드 실적 데이터 분석용_2.xlsx로 확인)에서 판관인건비에
    # 포함되지 않는다 — "기타-판관비"가 "고정판관비 - (판관인건비+복리후생비+접대비+
    # 지급수수료)" 잔여값이라 대손상각비를 포함한 항목이 여기로 흡수된다. 정방향 합산도
    # 같은 결과가 되도록 여기에 함께 더한다.
    sga_other = (
        _num(raw["대손상각비"])
        + _num(raw["여비교통비"]) + _num(raw["통신비"]) + _num(raw["소모품비"]) + _num(raw["도서인쇄비"])
        + _num(raw["세금과공과"]) + _num(raw["임차료"]) + _num(raw["수도광열비"]) + _num(raw["광고선전비"])
        + _num(raw["교육훈련비"]) + _num(raw["감가상각비"]) + _num(raw["무형자산상각비"])
        + _num(raw["수선유지비"]) + _num(raw["보험료"]) + _num(raw["회의비"])
        + _num(raw["경상연구개발비"]) + _num(raw["연구개발비(국책과제"]) + _num(raw["대손충당금환입"])
        + _num(raw["판관비_기타"])
    )
    sga_fixed = sga_personnel + sga_welfare + sga_entertainment + sga_fees + sga_other

    cogs_pre_adjust = _num(raw["매출원가A(조정전)"])  # AS = Raw!S
    cogs_final = _num(raw["매출원가(A)Tot"])  # AU = Raw!G
    standard_cogs = _num(raw["매출원가(S)Tot"])  # Phase 14 — 단순 복사
    sga_pre_adjust = _num(raw["판관비A(조정전)"])  # BJ = Raw!T
    sga_final = _num(raw["판관비(Total)"])  # BL = Raw!BP

    operating_profit_pre_adjust = sales_pre_adjust - cogs_pre_adjust - sga_pre_adjust  # BM
    operating_profit_final = sales_final - cogs_final - sga_final  # BN

    raw_quantity = _num(raw["매출수량"])
    quantity_raw = apply_quantity_exception(product_code, raw_quantity)  # BO
    quantity = apply_cell_22_9_conversion(product_group_1, quantity_raw)  # BZ
    inventory_diff = _num(raw["재고실사차이"])  # BP

    if raw_material_total < 0 or main_material_total < 0:
        is_calc_error = True
        calc_error_reason = "원재료비/주재료비 합계가 음수입니다."
    if pd.isna(raw.get("매출원가A(조정전)")) or pd.isna(raw.get("판관비A(조정전)")):
        is_calc_error = True
        calc_error_reason = "매출원가 또는 판관비 원본 값이 비어 있습니다."

    return RefinedRow(
        year=year,
        month=month,
        team=team,
        customer_code=customer_code,
        customer_name=customer_name,
        product_code=product_code,
        product_desc=product_desc,
        product_group=product_group,
        product_group_1=product_group_1,
        product_group_2=product_group_2,
        is_mapped=is_mapped,
        region=region,
        office=office,
        part=part,
        is_branch_mapped=is_branch_mapped,
        sales_provisional=sales_provisional,
        sales_discount=sales_discount,
        sales_adjustment=sales_adjustment,
        sales_final_ops=sales_final_ops,
        sales_other=sales_other,
        sales_pre_adjust=sales_pre_adjust,
        plan_adjustment=plan_adjustment,
        sales_final=sales_final,
        raw_material_sunyeon=raw_material_sunyeon,
        raw_material_gyeongyeon=raw_material_gyeongyeon,
        raw_material_calcium=raw_material_calcium,
        raw_material_nickel=raw_material_nickel,
        raw_material_lithium=raw_material_lithium,
        raw_material_total=raw_material_total,
        main_material_jeonjo=main_material_jeonjo,
        main_material_kaba=main_material_kaba,
        main_material_gyeorimpan=main_material_gyeorimpan,
        main_material_total=main_material_total,
        other_material_supplies=other_material_supplies,
        other_material_etc=other_material_etc,
        material_total=material_total,
        labor_variable_direct=labor_variable_direct,
        labor_fixed_direct=labor_fixed_direct,
        labor_direct=labor_direct,
        labor_indirect=labor_indirect,
        labor_total=labor_total,
        expense_variable=expense_variable,
        expense_fixed=expense_fixed,
        expense_outsourcing=expense_outsourcing,
        expense_total=expense_total,
        sga_vehicle=sga_vehicle,
        sga_delivery=sga_delivery,
        sga_export=sga_export,
        sga_installation=sga_installation,
        sga_warranty=sga_warranty,
        sga_defect_loss=sga_defect_loss,
        sga_ocean_freight=sga_ocean_freight,
        sga_variable=sga_variable,
        sga_personnel=sga_personnel,
        sga_welfare=sga_welfare,
        sga_entertainment=sga_entertainment,
        sga_fees=sga_fees,
        sga_other=sga_other,
        sga_fixed=sga_fixed,
        cogs_pre_adjust=cogs_pre_adjust,
        cogs_final=cogs_final,
        standard_cogs=standard_cogs,
        sga_pre_adjust=sga_pre_adjust,
        sga_final=sga_final,
        operating_profit_pre_adjust=operating_profit_pre_adjust,
        operating_profit_final=operating_profit_final,
        quantity_raw=quantity_raw,
        quantity=quantity,
        inventory_diff=inventory_diff,
        is_calc_error=is_calc_error,
        calc_error_reason=calc_error_reason,
    )


@dataclass
class RefinementResult:
    rows: list[RefinedRow] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.rows)

    @property
    def unmapped_count(self) -> int:
        return sum(1 for r in self.rows if not r.is_mapped)

    @property
    def calc_error_count(self) -> int:
        return sum(1 for r in self.rows if r.is_calc_error)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([r.__dict__ for r in self.rows])


def refine_actual_records(
    df_raw: pd.DataFrame,
    mapping: ProductMappingTable,
    branch_mapping: BranchMappingTable | None = None,
) -> RefinementResult:
    """실적 Raw Data 전체를 정제한다. 미매핑/계산오류 행도 제외하지 않고 포함한다."""
    validate_raw_columns(df_raw)
    result = RefinementResult()
    for _, raw_row in df_raw.iterrows():
        result.rows.append(refine_row(raw_row, mapping, branch_mapping))
    return result
