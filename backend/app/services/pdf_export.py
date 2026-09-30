"""F9. Overview 화면을 PDF로 내보낸다 (엑셀 대신 PDF 다운로드로 변경, 사용자 확인).

화면(app/overview/page.tsx)에 보이는 값과 동일한 내용을 담는다. Phase 15부터는
F4 화면 아래 탭 4개(월별 실적 분석 팀별/제품군별/거래처별, 손익 상세 분석)도
선택적으로 포함할 수 있다(사용자 요청: "아래의 각 탭의 것도 내용이 담겨서 출력이
될 수 있게... 다운로드하고 싶은 카테고리를 체크할 수 있게"). 한글 렌더링을 위해
Windows에 기본 내장된 맑은 고딕(Malgun Gothic) TTF를 등록해서 쓴다 — 이 프로젝트는
로컬(개인 Windows 환경) 데모가 완료 기준이라(PRD NG6) 별도 폰트 파일을 리포지토리에
포함하지 않고 OS 내장 폰트를 그대로 사용한다.
"""
from __future__ import annotations

from io import BytesIO
from typing import Callable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.analytics import get_overview
from app.services.monthly_analysis import (
    get_customer_monthly_analysis,
    get_product_group_monthly_analysis,
    get_team_monthly_analysis,
)
from app.services.pl_comparison import PLComparisonError, get_pl_comparison

# F4 화면의 "손익 상세 분석" 영역 탭(app/overview/page.tsx의 OverviewDetailTabs) 순서와
# 맞춘다. team_matrix는 항상 탭 UI보다 위에 있던 "팀별 목표 대비 실적" 영역이다.
SECTION_KEYS: list[str] = [
    "team_matrix",
    "monthly_team",
    "monthly_product_group",
    "monthly_customer",
    "pl_comparison",
]
SECTION_LABELS: dict[str, str] = {
    "team_matrix": "팀별 목표 대비 실적",
    "monthly_team": "월별 실적 분석(팀별)",
    "monthly_product_group": "월별 실적 분석(제품군별)",
    "monthly_customer": "월별 실적 분석(거래처별)",
    "pl_comparison": "손익 상세 분석",
}

# SEBANG CI 토큰(.docs/design.md)과 맞춘 색상.
SEBANG_DARK_GRAY = colors.HexColor("#333F48")
SEBANG_GREEN_700 = colors.HexColor("#006A76")
GREEN_50 = colors.HexColor("#EBF7F8")
LIGHT_GRAY_200 = colors.HexColor("#ECECEB")
# 밝은 노랑 — 월별 실적 분석 탭들의 "OO 요약" 소계 행과 같은 강조색(사용자 확인).
YELLOW_HIGHLIGHT = colors.HexColor("#FFF59D")

_FONT_REGISTERED = False
FONT_NAME = "Helvetica"
FONT_NAME_BOLD = "Helvetica-Bold"


def _ensure_korean_font() -> None:
    global _FONT_REGISTERED, FONT_NAME, FONT_NAME_BOLD
    if _FONT_REGISTERED:
        return
    _FONT_REGISTERED = True
    try:
        pdfmetrics.registerFont(TTFont("MalgunGothic", "C:/Windows/Fonts/malgun.ttf"))
        pdfmetrics.registerFont(TTFont("MalgunGothic-Bold", "C:/Windows/Fonts/malgunbd.ttf"))
        FONT_NAME = "MalgunGothic"
        FONT_NAME_BOLD = "MalgunGothic-Bold"
    except Exception:
        # 한글 폰트를 못 찾으면 Helvetica로 대체한다(한글은 깨지지만 다운로드 자체는 실패하지 않는다).
        pass


def _eok(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value / 100_000_000:,.1f}억"


def _num(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{round(value):,}"


def _num3(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"


def _pp(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%p"


def build_overview_pdf(db, batch_id: str, sections: list[str] | None = None) -> bytes | None:
    overview = get_overview(db, batch_id)
    if overview is None:
        return None
    _ensure_korean_font()

    selected = [s for s in SECTION_KEYS if sections is None or s in sections]
    if not selected:
        selected = list(SECTION_KEYS)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        title=f"전체 실적 Overview {overview['year']}년 {overview['month']}월",
    )

    title_style = ParagraphStyle("title", fontName=FONT_NAME_BOLD, fontSize=16, textColor=SEBANG_DARK_GRAY, spaceAfter=4)
    sub_style = ParagraphStyle("sub", fontName=FONT_NAME, fontSize=9, textColor=colors.HexColor("#717779"), spaceAfter=10)
    section_style = ParagraphStyle("section", fontName=FONT_NAME_BOLD, fontSize=13, textColor=SEBANG_DARK_GRAY, spaceAfter=8)
    subsection_style = ParagraphStyle("subsection", fontName=FONT_NAME_BOLD, fontSize=11, textColor=SEBANG_DARK_GRAY, spaceBefore=10, spaceAfter=6)
    caption_style = ParagraphStyle("caption", fontName=FONT_NAME, fontSize=9, textColor=SEBANG_DARK_GRAY, spaceAfter=2)

    elements: list = [
        Paragraph(f"전체 실적 Overview — {overview['year']}년 {overview['month']}월", title_style),
        Paragraph("팀별 순위, 목표 대비 실적, 전월·전년 동월 대비를 한눈에 확인합니다.", sub_style),
    ]

    style_ctx = _StyleContext(title_style, sub_style, section_style, subsection_style, caption_style)

    for i, key in enumerate(selected):
        if i > 0:
            elements.append(PageBreak())
        # team_matrix는 KPI 카드 + 표 자체의 소제목("팀별 목표 대비 실적 — ...")이 이미
        # 내용을 설명하므로 중복되는 섹션 제목을 또 넣지 않는다(넣으면 세로 여백이
        # 아주 조금 부족해져 표 마지막 행이 다음 페이지로 밀리는 걸 실제로 확인했다 —
        # 위쪽 KeepTogether/여백 수정과 같은 종류의 문제).
        if key != "team_matrix":
            elements.append(Paragraph(SECTION_LABELS[key], section_style))
        if key == "team_matrix":
            _add_team_matrix_section(elements, overview, style_ctx)
        elif key == "monthly_team":
            _add_monthly_team_section(elements, db, batch_id, style_ctx)
        elif key == "monthly_product_group":
            _add_monthly_grouped_section(
                elements,
                get_product_group_monthly_analysis(db, batch_id),
                "product_group_2",
                "미분류",
                ["수량", "매출액", "영업이익", "이익률", "판매가", "제조원가율", "판관비율"],
                lambda m: [_num(m["quantity"]), _num(m["actual_amount"]), _num(m["profit"]), _pct(m["profit_rate"]), _num3(m["avg_unit_price"]), _pct(m["mfg_cost_rate"]), _pct(m["sga_rate"])],
                style_ctx,
                label_width=42 * mm,
            )
        elif key == "monthly_customer":
            # 거래처명은 "가나자동차 주식회사(GN Motors Corp)"처럼 아주 길 수 있어(사용자
            # 확인: "칸에 안맞아서 구역을 침범하는거") 제품군 탭보다 라벨 칸을 더 넓게 준다.
            _add_monthly_grouped_section(
                elements,
                get_customer_monthly_analysis(db, batch_id),
                "customer",
                "미상",
                ["수량", "매출액", "영업이익", "영업이익%"],
                lambda m: [_num(m["quantity"]), _num(m["actual_amount"]), _num(m["profit"]), _pct(m["profit_rate"])],
                style_ctx,
                label_width=55 * mm,
            )
        elif key == "pl_comparison":
            _add_pl_comparison_section(elements, db, batch_id, style_ctx)

    doc.build(elements)
    return buf.getvalue()


class _StyleContext:
    def __init__(self, title, sub, section, subsection, caption):
        self.title = title
        self.sub = sub
        self.section = section
        self.subsection = subsection
        self.caption = caption


def _wrapped_label(text: str):
    """긴 거래처명·계정과목명이 셀 폭을 넘어 옆 칸을 침범하던 문제(사용자 확인:
    "칸에 안맞아서 구역을 침범하는거") — 고정 폭 셀에 그냥 문자열을 넣으면 reportlab이
    줄바꿈 없이 그대로 흘려보내 옆 칸 위로 겹쳐 그린다. Paragraph로 감싸면 셀 폭
    안에서 자동으로 줄바꿈되고 행 높이가 필요한 만큼 늘어난다. 스타일을 매번 새로
    만드는 이유 — FONT_NAME은 _ensure_korean_font()가 실행된 뒤에야 맑은 고딕으로
    바뀌는 모듈 전역값이라, 모듈 로드 시점에 스타일을 한 번만 만들어 두면 그 이전의
    Helvetica가 그대로 굳어버려 한글이 깨진다."""
    return Paragraph(text, ParagraphStyle("cell_label", fontName=FONT_NAME, fontSize=7.5, leading=9, alignment=0))


def _add_team_matrix_section(elements: list, overview: dict, styles: _StyleContext) -> None:
    summary = overview["summary"]
    matrix = overview["team_matrix"]
    total_row = next((r for r in matrix if r["team"] == "합계"), None)

    # ── 상단 KPI 요약 ──
    kpi_data = [
        ["수량", "매출", "영업이익", "이익률"],
        [
            _num(summary["total_quantity"]),
            _eok(summary["total_actual_amount"]),
            _eok(summary["total_profit"]),
            _pct(summary["total_profit_rate"]),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[60 * mm] * 4)
    kpi_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("FONTNAME", (0, 1), (-1, 1), FONT_NAME_BOLD),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, 1), 14),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#717779")),
                ("TEXTCOLOR", (0, 1), (-1, 1), SEBANG_DARK_GRAY),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.5, LIGHT_GRAY_200),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LIGHT_GRAY_200),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(kpi_table)
    elements.append(Spacer(1, 8))

    # ── 계획 대비 / 전월 대비 캡션 (사용자 확인 문구 형식) ──
    if total_row is not None:
        mtd = total_row["mtd"]
        amount_diff = summary["total_actual_amount"] - mtd["plan_amount"] if mtd["plan_amount"] is not None else None
        profit_diff = mtd["profit_diff"]
        rate_diff = (
            mtd["actual_profit_rate"] - mtd["plan_profit_rate"]
            if mtd["actual_profit_rate"] is not None and mtd["plan_profit_rate"] is not None
            else None
        )
        elements.append(
            Paragraph(
                f"<b>계획 대비</b>: 매출 {_eok(amount_diff)}"
                f"({_pct(mtd['amount_achievement_rate'])}) / 영업이익 {_eok(profit_diff)} / 영업이익률 {_pp(rate_diff)}",
                styles.caption,
            )
        )

    if summary["prev_month_available"]:
        prev_amount_diff = (
            summary["total_actual_amount"] - summary["prev_month_total_amount"]
            if summary["prev_month_total_amount"] is not None
            else None
        )
        prev_profit_diff = (
            summary["total_profit"] - summary["prev_month_total_profit"]
            if summary["prev_month_total_profit"] is not None
            else None
        )
        prev_rate_diff = (
            summary["total_profit_rate"] - summary["prev_month_total_profit_rate"]
            if summary["total_profit_rate"] is not None and summary["prev_month_total_profit_rate"] is not None
            else None
        )
        elements.append(
            Paragraph(
                f"<b>전월 대비</b>: 매출 {_eok(prev_amount_diff)}"
                f"({_pct(summary['prev_month_change_pct'])}) / 영업이익 {_eok(prev_profit_diff)} / 영업이익률 {_pp(prev_rate_diff)}",
                styles.caption,
            )
        )
    else:
        elements.append(Paragraph("<b>전월 대비</b>: 전월 배치가 없어 비교할 수 없습니다.", styles.caption))

    # ── 팀별 목표 대비 실적 표 (당월 + 누계, 그룹 헤더 2단) ──
    # 제목과 표를 KeepTogether로 묶는다 — 페이지 여백 계산이 아주 미세하게(1pt 미만) 부족해
    # 표의 마지막 행(합계)만 다음 페이지로 넘어가고 그 자리에 반복 헤더 3행 + 그 한 행만
    # 남는 문제를 실제로 겪었다(사용자 확인: "PDF 다운하면 밑에 내용이 잘린다"). KeepTogether로
    # 표 전체가 통째로 다음 페이지로 넘어가게 한다.
    def add_matrix_table(title: str, labels: tuple[str, str], compare_labels: tuple[str, str], row_values: Callable[[dict], list[str]]) -> None:
        block: list = [Spacer(1, 4), Paragraph(title, styles.subsection)]

        period_header = ["팀", f"{overview['year']}년 {overview['month']}월", "", "", "", "", "", f"{overview['year']}년 누계", "", "", "", "", ""]
        group_header = ["", "목표", "", "실적", "", "대비", "", "목표", "", "실적", "", "대비", ""]
        # 실제로 겪은 버그: 아래를 `["", ...6개] * 2` 뒤 앞의 ""를 "팀"으로 바꾸는 방식으로
        # 만들었더니, 반복되는 두 번째 블록에도 선행 ""가 그대로 남아 총 14칸(13칸이어야
        # 함)이 되어 "누계" 쪽 헤더가 데이터 컬럼과 한 칸씩 밀려 보였다(체크해보니 실제로
        # "수량"/"매출액" 칸이 밀리고 끝에 빈 칸이 하나 더 생겼다). "팀"은 한 번만 앞에 붙이고
        # 반복 블록에는 선행 빈 칸을 넣지 않아야 정확히 13칸이 된다.
        leaf_header = ["팀"] + [labels[0], labels[1], labels[0], labels[1], compare_labels[0], compare_labels[1]] * 2

        data = [period_header, group_header, leaf_header]
        for row in matrix:
            data.append([row["team"], *row_values(row["mtd"]), *row_values(row["ytd"])])

        col_widths = [24 * mm] + [19 * mm] * 12
        table = Table(data, colWidths=col_widths, repeatRows=3)
        style = [
            ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, 2), 8),
            ("FONTSIZE", (0, 3), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 2), SEBANG_GREEN_700),
            ("TEXTCOLOR", (0, 0), (-1, 2), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("SPAN", (1, 0), (6, 0)),
            ("SPAN", (7, 0), (12, 0)),
            ("SPAN", (1, 1), (2, 1)),
            ("SPAN", (3, 1), (4, 1)),
            ("SPAN", (5, 1), (6, 1)),
            ("SPAN", (7, 1), (8, 1)),
            ("SPAN", (9, 1), (10, 1)),
            ("SPAN", (11, 1), (12, 1)),
            ("SPAN", (0, 0), (0, 2)),
            ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GRAY_200),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for i, row in enumerate(matrix, start=3):
            if row["team"] == "합계":
                style.append(("BACKGROUND", (0, i), (-1, i), GREEN_50))
                style.append(("FONTNAME", (0, i), (-1, i), FONT_NAME_BOLD))
            elif row["is_synthetic"]:
                style.append(("TEXTCOLOR", (0, i), (-1, i), colors.HexColor("#717779")))
        table.setStyle(TableStyle(style))
        block.append(table)
        elements.append(KeepTogether(block))

    add_matrix_table(
        "팀별 목표 대비 실적 — 수량·매출액",
        ("수량", "매출액"),
        ("수량", "매출액"),
        lambda p: [
            _num(p["plan_quantity"]), _eok(p["plan_amount"]),
            _num(p["actual_quantity"]), _eok(p["actual_amount"]),
            _pct(p["quantity_achievement_rate"]), _pct(p["amount_achievement_rate"]),
        ],
    )

    add_matrix_table(
        "팀별 목표 대비 실적 — 영업이익",
        ("금액", "이익율"),
        ("금액", "금액(%)"),
        lambda p: [
            _eok(p["plan_profit"]), _pct(p["plan_profit_rate"]),
            _eok(p["actual_profit"]), _pct(p["actual_profit_rate"]),
            _eok(p["profit_diff"]), _pct(p["profit_achievement_rate"]),
        ],
    )


def _add_monthly_team_section(elements: list, db, batch_id: str, styles: _StyleContext) -> None:
    result = get_team_monthly_analysis(db, batch_id)
    header = ["팀", "월", "수량", "매출액", "영업이익", "이익률", "판관비", "판관비율", "제조원가", "제조원가율", "표준매출원가"]
    data = [header]
    style_cmds: list = [
        ("FONTNAME", (0, 0), (-1, 0), FONT_NAME_BOLD),
        ("BACKGROUND", (0, 0), (-1, 0), SEBANG_GREEN_700),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ]
    row_idx = 1
    for team in result["teams"]:
        start_row = row_idx
        for i, month_entry in enumerate(team["months"]):
            m = month_entry["metrics"]
            team_label = team["team"] if i == 0 else ""
            month_label = f"{month_entry['month']}월"
            if m is None:
                data.append([team_label, month_label] + ["-"] * 9)
            else:
                data.append([
                    team_label, month_label,
                    _num(m["quantity"]), _num(m["actual_amount"]), _num(m["profit"]), _pct(m["profit_rate"]),
                    _num(m["sga_amount"]), _pct(m["sga_rate"]), _num(m["mfg_cost"]), _pct(m["mfg_cost_rate"]), _num(m["standard_cogs"]),
                ])
            row_idx += 1
        s = team["summary"]
        # SPAN(0,1)의 표시 내용은 왼쪽 위 칸(0번)이 결정한다 — 라벨을 0번 칸에 넣는다.
        data.append([
            f"{team['team']} 요약", "",
            _num(s["quantity"]), _num(s["actual_amount"]), _num(s["profit"]), _pct(s["profit_rate"]),
            _num(s["sga_amount"]), _pct(s["sga_rate"]), _num(s["mfg_cost"]), _pct(s["mfg_cost_rate"]), _num(s["standard_cogs"]),
        ])
        # 팀 칸은 월별 행에만 SPAN한다(요약 행은 제외) — 요약 행까지 포함해서 SPAN하면
        # 요약 행 자체의 "{팀} 요약" 라벨이 좁은 월 칸(1칸)에만 갇혀 옆 칸으로 글자가
        # 넘치는 문제가 실제로 있었다(사용자 확인: "PDF 다운받을때 원본 서식이 깨진다").
        # 대신 요약 행은 합계 행과 똑같이 팀+월 두 칸을 SPAN해 라벨에 충분한 폭을 준다.
        style_cmds.append(("SPAN", (0, start_row), (0, row_idx - 1)))
        style_cmds.append(("SPAN", (0, row_idx), (1, row_idx)))
        style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), YELLOW_HIGHLIGHT))
        style_cmds.append(("FONTNAME", (0, row_idx), (-1, row_idx), FONT_NAME_BOLD))
        row_idx += 1

    t = result["total"]
    data.append([
        "합계", "",
        _num(t["quantity"]), _num(t["actual_amount"]), _num(t["profit"]), _pct(t["profit_rate"]),
        _num(t["sga_amount"]), _pct(t["sga_rate"]), _num(t["mfg_cost"]), _pct(t["mfg_cost_rate"]), _num(t["standard_cogs"]),
    ])
    style_cmds.append(("SPAN", (0, row_idx), (1, row_idx)))
    style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), GREEN_50))
    style_cmds.append(("FONTNAME", (0, row_idx), (-1, row_idx), FONT_NAME_BOLD))

    # 마지막 두 컬럼("제조원가율"/"표준매출원가")은 헤더 글자 수가 더 많아 16mm로는
    # 헤더 텍스트가 칸 밖으로 삐져나왔다(사용자 확인: "원본 서식이 깨진다") — 더 넓게 준다.
    col_widths = [22 * mm, 14 * mm] + [16 * mm] * 7 + [18 * mm, 20 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds += [
        ("FONTNAME", (0, 1), (-1, -2), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GRAY_200),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    table.setStyle(TableStyle(style_cmds))
    elements.append(table)


def _add_monthly_grouped_section(
    elements: list,
    result: dict | None,
    dimension_key: str,
    empty_label: str,
    leaf_labels: list[str],
    render_cells: Callable[[dict], list[str]],
    styles: _StyleContext,
    label_width: float = 30 * mm,
) -> None:
    if result is None:
        elements.append(Paragraph("데이터가 없습니다.", styles.caption))
        return

    n = len(leaf_labels)
    header1 = ["구분", f"{result['year']}년 {result['month']}월", *([""] * (n - 1)), f"{result['year']}년 누계", *([""] * (n - 1))]
    header2 = [""] + leaf_labels + leaf_labels
    data = [header1, header2]
    style_cmds: list = [
        ("SPAN", (1, 0), (n, 0)),
        ("SPAN", (n + 1, 0), (2 * n, 0)),
        ("SPAN", (0, 0), (0, 1)),
        ("BACKGROUND", (0, 0), (-1, 1), SEBANG_GREEN_700),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("FONTNAME", (0, 0), (-1, 1), FONT_NAME_BOLD),
    ]
    row_idx = 2
    for group in result["groups"]:
        data.append([group["team"]] + [""] * (2 * n))
        style_cmds.append(("SPAN", (0, row_idx), (2 * n, row_idx)))
        style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), LIGHT_GRAY_200))
        style_cmds.append(("FONTNAME", (0, row_idx), (-1, row_idx), FONT_NAME_BOLD))
        row_idx += 1
        for r in group["rows"]:
            label = r.get(dimension_key) or empty_label
            data.append([_wrapped_label(label), *render_cells(r["mtd"]), *render_cells(r["ytd"])])
            row_idx += 1
        data.append([f"{group['team']} 요약", *render_cells(group["subtotal"]["mtd"]), *render_cells(group["subtotal"]["ytd"])])
        style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), YELLOW_HIGHLIGHT))
        style_cmds.append(("FONTNAME", (0, row_idx), (-1, row_idx), FONT_NAME_BOLD))
        row_idx += 1

    data.append(["합계", *render_cells(result["total"]["mtd"]), *render_cells(result["total"]["ytd"])])
    style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), GREEN_50))
    style_cmds.append(("FONTNAME", (0, row_idx), (-1, row_idx), FONT_NAME_BOLD))

    col_widths = [label_width] + [16 * mm] * (2 * n)
    table = Table(data, colWidths=col_widths, repeatRows=2)
    style_cmds += [
        ("FONTNAME", (0, 2), (-1, -2), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GRAY_200),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    table.setStyle(TableStyle(style_cmds))
    elements.append(table)


def _add_pl_comparison_section(elements: list, db, batch_id: str, styles: _StyleContext) -> None:
    try:
        lines = get_pl_comparison(db, batch_id, team=None).lines
    except PLComparisonError:
        elements.append(Paragraph("데이터가 없습니다.", styles.caption))
        return

    elements.append(Paragraph("① 계획 대비 (국내 전체)", styles.subsection))
    header1 = ["구분", "계획", "", "", "실적", "", "", "계획대비", "", ""]
    header2 = ["", "단위당", "총액", "비중", "단위당", "총액", "비중", "단위당", "총액", "증감율"]
    data = [header1, header2]
    for line in lines:
        data.append([
            _wrapped_label(line.label), _num(line.plan_unit), _num(line.plan_total), _pct(line.plan_ratio),
            _num(line.actual_unit), _num(line.actual_total), _pct(line.actual_ratio),
            _num(line.diff_unit), _num(line.diff_total), _pct(line.change_rate),
        ])
    elements.append(_simple_grouped_table(data, [1, 4, 7], 38 * mm))

    elements.append(Spacer(1, 10))
    elements.append(Paragraph("② 전월 대비 (국내 전체)", styles.subsection))
    header1b = ["구분", "당월", "", "", "전월", "", "", "전월대비", "", ""]
    data2 = [header1b, header2]
    for line in lines:
        data2.append([
            _wrapped_label(line.label), _num(line.actual_unit), _num(line.actual_total), _pct(line.actual_ratio),
            _num(line.prev_month_unit), _num(line.prev_month_total), _pct(line.prev_month_ratio),
            _num(line.diff_prev_month_unit), _num(line.diff_prev_month_total), _pct(line.change_rate_prev_month),
        ])
    elements.append(_simple_grouped_table(data2, [1, 4, 7], 38 * mm))
    if not any(line.prev_month_available for line in lines):
        elements.append(Paragraph("전월 배치가 없어 전월 대비를 계산할 수 없습니다.", styles.caption))


def _simple_grouped_table(data: list[list[str]], group_start_cols: list[int], label_width) -> Table:
    """구분(1) + 3그룹×3칼럼 = 10칼럼, 2행 헤더(그룹명 병합 + 세부 라벨) 표 공통 스타일."""
    col_widths = [label_width] + [18 * mm] * 9
    table = Table(data, colWidths=col_widths, repeatRows=2)
    style_cmds = [
        ("SPAN", (0, 0), (0, 1)),
        ("BACKGROUND", (0, 0), (-1, 1), SEBANG_GREEN_700),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("FONTNAME", (0, 0), (-1, 1), FONT_NAME_BOLD),
        ("FONTNAME", (0, 2), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GRAY_200),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for start in group_start_cols:
        style_cmds.append(("SPAN", (start, 0), (start + 2, 0)))
    table.setStyle(TableStyle(style_cmds))
    return table
