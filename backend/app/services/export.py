"""F9. Overview·이상징후 리스트·보고서 초안을 엑셀(xlsx)로 내보낸다.

담당자가 다운로드한 파일을 기존 배포 경로(영업팀 공유/회의체/임원 메일)에
그대로 첨부할 수 있어야 하므로(PRD F9), 화면에 보이는 값 그대로 컬럼명을
한글로 두고 1개 시트에 표 형태로만 담는다 — 별도 서식·수식은 넣지 않는다.
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference

from app.services.analytics import get_anomalies, get_trend
from app.services.refinement import REFINED_ROW_COLUMNS
from app.services.reports import get_report_draft

# F7 "실적 Re-arrange용 수식 시트 전체" 다운로드(Phase 15, 사용자 요청: "raw와 맵핑을
# 거쳐 정제된 실적 Re-arrange용 수식 시트 전체, xlsx 양식") — refined_sales_record의
# 각 컬럼이 어떤 원본 Re-arrange 계정과목/식별자에 대응하는지는 app/services/refinement.py의
# RefinedRow 필드 주석과 .docs/03_데이터정제.md §4에서 실측 검증한 이름을 그대로 쓴다
# (추정으로 새 이름을 짓지 않는다).
REFINED_COLUMN_LABELS: dict[str, str] = {
    "year": "연도",
    "month": "월",
    "team": "팀",
    "customer_code": "고객코드",
    "customer_name": "고객명",
    "product_code": "상품코드",
    "product_desc": "상품명",
    "product_group": "제품구분3(계획비교용)",
    "product_group_1": "제품구분1(보고4용)",
    "product_group_2": "제품구분2(보고3용)",
    "is_mapped": "제품매핑여부",
    "region": "권역",
    "office": "사업소",
    "part": "파트",
    "is_branch_mapped": "지점매핑여부",
    "sales_provisional": "영업-가마감매출",
    "sales_discount": "영업-매출할인",
    "sales_adjustment": "영업-마감매출조정",
    "sales_final_ops": "영업-정마감매출",
    "sales_other": "영업-기타매출액",
    "sales_pre_adjust": "영업-매출액(조정전)",
    "plan_adjustment": "기획-매출조정",
    "sales_final": "기획-매출액(최종마감)",
    "raw_material_sunyeon": "원재료비_순연(A)",
    "raw_material_gyeongyeon": "원재료비_경연(A)",
    "raw_material_calcium": "원재료비_칼슘연(A)",
    "raw_material_nickel": "원재료비_니켈(A)",
    "raw_material_lithium": "원재료비_리튬(A)",
    "raw_material_total": "원재료비 계",
    "main_material_jeonjo": "주재료비_전조(A)",
    "main_material_kaba": "주재료비_카바(A)",
    "main_material_gyeorimpan": "주재료비_격리판(A)",
    "main_material_total": "주재료비 계",
    "other_material_supplies": "부재료비(A)",
    "other_material_etc": "기타재료비(포장비 등) 계",
    "material_total": "재료비 계",
    "labor_variable_direct": "변동직접노무비(A)",
    "labor_fixed_direct": "고정직접노무비(A)",
    "labor_direct": "직접노무비 계",
    "labor_indirect": "간접노무비(A)",
    "labor_total": "노무비 계",
    "expense_variable": "변동경비(A)",
    "expense_fixed": "고정경비(A)",
    "expense_outsourcing": "외주가공비(A)",
    "expense_total": "경비 계",
    "sga_vehicle": "차량유지비",
    "sga_delivery": "운반비",
    "sga_export": "수출비용(A)",
    "sga_installation": "시험설치비(A)",
    "sga_warranty": "판매보증비",
    "sga_defect_loss": "불량제품손실",
    "sga_ocean_freight": "수출비용_해상운임",
    "sga_variable": "변동판관비 계",
    "sga_personnel": "판관인건비",
    "sga_welfare": "복리후생비",
    "sga_entertainment": "접대비(A)",
    "sga_fees": "지급수수료",
    "sga_other": "기타-판관비",
    "sga_fixed": "고정판관비",
    "cogs_pre_adjust": "매출원가A(조정전)",
    "cogs_final": "매출원가(A)Tot",
    "standard_cogs": "매출원가(S)Tot",
    "sga_pre_adjust": "판관비A(조정전)",
    "sga_final": "판관비(Total)",
    "operating_profit_pre_adjust": "영업이익(조정전)",
    "operating_profit_final": "영업이익(최종마감)",
    "quantity_raw": "매출수량(예외규칙 적용)",
    "quantity": "수량(22.9cell)",
    "inventory_diff": "재고실사차이",
    "is_calc_error": "계산오류여부",
    "calc_error_reason": "계산오류사유",
}


def _to_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_anomalies_workbook(db, batch_id: str) -> bytes | None:
    if db.batch_period(batch_id) is None:
        return None
    anomalies = get_anomalies(db, batch_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "이상징후"
    ws.append(["팀", "제품군", "판정기준", "실제값", "임계값", "영향금액"])
    for a in anomalies:
        ws.append(
            [
                a["team"],
                a["product_group"] or "미매핑",
                a["metric_type"],
                a["actual_value"],
                a["threshold_value"],
                a["impact_amount"],
            ]
        )
    return _to_bytes(wb)


def _add_team_trend_chart(data_ws, chart_ws, team: str, months: list[dict], start_row: int) -> int:
    """`team`의 12개월 데이터(월/매출액/영업이익)를 data_ws에 표로 적고, chart_ws에
    F7 화면(app/reports/page.tsx)과 같은 매출액(막대)+영업이익(선, 보조축) 콤보
    차트를 하나 그려 넣는다. 데이터가 없는 달은 None으로 그대로 두어(화면과 동일하게
    "값 없음"으로 표시) 0으로 대체하지 않는다. 다음 팀이 이어 쓸 행 번호를 반환한다."""
    header_row = start_row
    data_ws.cell(row=header_row, column=1, value="월")
    data_ws.cell(row=header_row, column=2, value="매출액")
    data_ws.cell(row=header_row, column=3, value="영업이익")
    for i, m in enumerate(months):
        r = header_row + 1 + i
        data_ws.cell(row=r, column=1, value=m["month"])
        data_ws.cell(row=r, column=2, value=m["actual_amount"])
        data_ws.cell(row=r, column=3, value=m["profit"])
    last_row = header_row + len(months)

    bar = BarChart()
    bar.type = "col"
    bar.title = f"{team} 월별 추이(매출액·영업이익)"
    bar.y_axis.title = "매출액"
    bar.x_axis.title = "월"
    cats = Reference(data_ws, min_col=1, min_row=header_row + 1, max_row=last_row)
    sales_ref = Reference(data_ws, min_col=2, min_row=header_row, max_row=last_row)
    bar.add_data(sales_ref, titles_from_data=True)
    bar.set_categories(cats)

    line = LineChart()
    profit_ref = Reference(data_ws, min_col=3, min_row=header_row, max_row=last_row)
    line.add_data(profit_ref, titles_from_data=True)
    line.y_axis.axId = 200
    line.y_axis.title = "영업이익"
    line.y_axis.crosses = "max"  # 매출액과 규모 차이가 커서 화면처럼 축을 분리한다

    bar += line
    bar.width = 20
    bar.height = 10  # cm — 기본 행 높이 기준 대략 20행 분량의 시각적 높이
    chart_ws.add_chart(bar, f"A{header_row}")

    # 다음 팀의 차트가 이 차트와 겹치지 않도록, 데이터 블록 길이(13행)보다 차트의
    # 시각적 높이(약 20행)를 기준으로 다음 시작 행을 띄운다.
    return max(last_row + 2, header_row + 20)


def build_report_workbook(db, draft_id: str) -> bytes | None:
    draft = get_report_draft(db, draft_id)
    if draft is None:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = "보고서 초안"
    ws.append(["팀", "제품군", "판정기준", "코멘트", "배경 설명"])
    included_teams: list[str] = []
    for item in draft["items"]:
        if item["is_excluded"]:
            continue
        comment = item["user_comment"] or item["auto_comment"]
        ws.append(
            [
                item["team"],
                item["product_group"] or "미매핑",
                item["metric_type"],
                comment,
                item["background_note"] or "",
            ]
        )
        if item["team"] and item["team"] not in included_teams:
            included_teams.append(item["team"])

    # 사용자 요청: "엑셀 다운로드 시 내용에 그래프도 같이 들어가게" — F7 화면이 이미
    # 보여주는 팀별 추이(GET /batches/{id}/trend)를 그대로 재사용해 엑셀 네이티브
    # 차트로 옮긴다. 데이터는 "차트데이터" 숨김 시트에 두고 "추이 차트" 시트에는
    # 차트만 보이게 한다(표와 차트를 한 시트에 섞으면 서로 겹친다).
    period = db.batch_period(draft["batch_id"])
    if period and included_teams:
        year, month = period
        chart_ws = wb.create_sheet("추이 차트")
        data_ws = wb.create_sheet("차트데이터")
        data_ws.sheet_state = "hidden"
        row = 1
        for team in included_teams:
            trend = get_trend(db, team, year, month)
            row = _add_team_trend_chart(data_ws, chart_ws, team, trend["months"], row)

    return _to_bytes(wb)


def build_refined_export_workbook_for_batch(db, batch_id: str) -> bytes | None:
    """F7 "실적 Re-arrange용 수식 시트 전체" 다운로드 — 해당 배치의 refined_sales_record를
    raw+매핑을 거쳐 정제된 그대로, 컬럼 하나도 빠짐없이 xlsx 한 시트에 담는다."""
    if db.batch_period(batch_id) is None:
        return None

    columns = list(REFINED_ROW_COLUMNS)
    rows = db.connection.execute(
        f"SELECT {', '.join(columns)} FROM refined_sales_record WHERE batch_id = ?",
        [batch_id],
    ).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "실적 Re-arrange"
    ws.append([REFINED_COLUMN_LABELS[c] for c in columns])
    for row in rows:
        ws.append(list(row))
    return _to_bytes(wb)


def build_refined_export_workbook_for_draft(db, draft_id: str) -> bytes | None:
    """F7 보고서 화면에서 호출 — draft_id가 가리키는 배치의 정제 결과를 내려준다."""
    row = db.connection.execute(
        "SELECT batch_id FROM report_draft WHERE draft_id = ?", [draft_id]
    ).fetchone()
    if row is None:
        return None
    return build_refined_export_workbook_for_batch(db, row[0])
