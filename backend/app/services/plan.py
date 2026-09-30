"""연간 판매계획 파일 파싱.

.docs/03_데이터정제.md §6.1에서 확인된 실제 구조를 반영한다 — 팀·년·월 단위가
아니라 거래처×제품군×월 단위이며, 팀별 시트(고정형/모티브/차량대리점/차량OE)와
제품군 매핑 시트(인자)로 구성된다. "금액" 셀은 원본에서 판가×수량 수식으로
계산되는데 캐시값이 비어 있을 수 있으므로, 이 파서는 셀 값을 신뢰하지 않고
판가×수량을 직접 계산한다.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

from openpyxl import load_workbook

FACTOR_SHEET = "인자"

# 시트명(=앱 전체에서 쓰는 표준 team 값) -> 그 시트 안의 "본부보고용" VLOOKUP 수식이
# 실제로 사용하는 리터럴 키. 두 값이 시트마다 다르다는 것을 실제로 확인했다
# (예: "차량대리점" 시트인데 VLOOKUP은 "대리점"&제품군을 키로 쓴다) — 시트명·"팀"
# 컬럼 값·VLOOKUP 리터럴 셋 다 서로 다르므로 하나로 추정하지 않고 실측한 값을 그대로 쓴다.
TEAM_SHEET_TO_FACTOR_KEY = {
    "고정형": "고정형",
    "모티브": "모티브",
    "차량대리점": "대리점",
    "차량OE": "차량OE",
}

# 담당,팀,유통채널,고객,고객명,납품처,납품처명,영업담당,구분,제품군,제품코드,판가,수량,금액,
# (1~12월: 판가,수량,금액) 순서로 고정되어 있다 (§6.1 근거).
FIRST_MONTH_COLUMN_OFFSET = 14  # "담당"=0 기준, 1월 판가가 시작되는 0-based 컬럼 오프셋


class PlanValidationError(ValueError):
    def __init__(self, message: str):
        super().__init__(message)


@dataclass
class PlanEntry:
    team: str
    customer_code: str | None
    customer_name: str | None
    delivery_code: str | None
    delivery_name: str | None
    sales_rep: str | None
    category: str | None
    product_type: str | None
    hq_report_group: str | None
    year: int
    month: int
    unit_price: float | None
    quantity: float | None
    planned_amount: float | None


def _cell(row, idx):
    return row[idx] if idx < len(row) else None


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_factor_sheet(ws) -> dict[tuple[str, str], str]:
    """인자 시트를 (팀, 제품군) -> 본부보고용 딕셔너리로 변환한다."""
    mapping: dict[tuple[str, str], str] = {}
    for row in ws.iter_rows(min_row=3, values_only=True):
        team, product_type, hq_group = _cell(row, 1), _cell(row, 2), _cell(row, 3)
        if team and product_type:
            mapping[(str(team).strip(), str(product_type).strip())] = (
                str(hq_group).strip() if hq_group else None
            )
    return mapping


def _find_year(ws) -> int:
    for row in ws.iter_rows(max_row=5, values_only=True):
        for value in row:
            if isinstance(value, str):
                m = re.search(r"(\d{4})년", value)
                if m:
                    return int(m.group(1))
    raise PlanValidationError(f"'{ws.title}' 시트 제목에서 연도를 찾을 수 없습니다 (예: '2026년...').")


def _find_header_row(ws) -> int:
    for row_idx in range(1, ws.max_row + 1):
        first_cell = ws.cell(row=row_idx, column=1).value
        if first_cell == "담당":
            return row_idx
    raise PlanValidationError(f"'{ws.title}' 시트에서 헤더 행('담당' 컬럼)을 찾을 수 없습니다.")


def _parse_team_sheet(ws, team: str, factor_key: str, factor_map: dict[tuple[str, str], str]) -> list[PlanEntry]:
    year = _find_year(ws)
    header_row = _find_header_row(ws)

    entries: list[PlanEntry] = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if not _cell(row, 0):  # "담당"이 비어 있으면 데이터 행이 끝난 것으로 본다
            continue
        customer_code = _cell(row, 3)
        customer_name = _cell(row, 4)
        delivery_code = _cell(row, 5)
        delivery_name = _cell(row, 6)
        sales_rep = _cell(row, 7)
        category = _cell(row, 8)
        product_type = _cell(row, 9)
        product_type = str(product_type).strip() if product_type else None
        hq_report_group = factor_map.get((factor_key, product_type)) if product_type else None

        for month in range(1, 13):
            base = FIRST_MONTH_COLUMN_OFFSET + (month - 1) * 3
            unit_price = _to_float(_cell(row, base))
            quantity = _to_float(_cell(row, base + 1))
            if unit_price is None and quantity is None:
                continue
            planned_amount = (unit_price or 0.0) * (quantity or 0.0)
            entries.append(
                PlanEntry(
                    team=team,
                    customer_code=str(customer_code) if customer_code is not None else None,
                    customer_name=str(customer_name) if customer_name is not None else None,
                    delivery_code=str(delivery_code) if delivery_code is not None else None,
                    delivery_name=str(delivery_name) if delivery_name is not None else None,
                    sales_rep=str(sales_rep) if sales_rep is not None else None,
                    category=str(category) if category is not None else None,
                    product_type=product_type,
                    hq_report_group=hq_report_group,
                    year=year,
                    month=month,
                    unit_price=unit_price,
                    quantity=quantity,
                    planned_amount=planned_amount,
                )
            )
    return entries


def parse_plan_workbook(content: bytes) -> list[PlanEntry]:
    """판매계획 xlsx 파일(팀별 시트 + 인자 매핑 시트)을 파싱한다."""
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:  # noqa: BLE001 — 어떤 형식 오류든 사용자에게 동일하게 안내
        raise PlanValidationError(f"판매계획 파일을 열 수 없습니다: {exc}") from exc

    factor_map = _parse_factor_sheet(wb[FACTOR_SHEET]) if FACTOR_SHEET in wb.sheetnames else {}

    present_team_sheets = [name for name in TEAM_SHEET_TO_FACTOR_KEY if name in wb.sheetnames]
    if not present_team_sheets:
        raise PlanValidationError(
            f"판매계획 파일에 팀별 시트가 없습니다 (필요: {list(TEAM_SHEET_TO_FACTOR_KEY)} 중 최소 1개)."
        )

    entries: list[PlanEntry] = []
    for sheet_name in present_team_sheets:
        factor_key = TEAM_SHEET_TO_FACTOR_KEY[sheet_name]
        entries.extend(_parse_team_sheet(wb[sheet_name], sheet_name, factor_key, factor_map))
    return entries
