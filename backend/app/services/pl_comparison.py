"""F4 확장 — 팀별 손익계산서 계획 대비/전월 대비 실적 비교 (드릴다운 필터 지원).

.docs/phase/phase_11_팀별손익계산서비교.md, .docs/phase/phase_12_전월대비및드릴다운.md 근거:
사용자가 제공한 실제 참고 파일의 "검색용" 시트(피벗테이블 3개 — 당월실적/전월실적은
실적 Re-arrange 기준, 손익계산서는 계획 시트 기준)를 분석해 아래 구조를 그대로 반영했다.
  - 단위당 = 총액 ÷ 매출수량
  - 비중 = 항목 총액 ÷ 매출액 총액 (계획·실적·전월 각각 자기 매출액 기준)
  - 계획대비/전월대비: 단위당·총액은 (비교대상 − 기준), 증감율은 (비교대상 − 기준) / 기준

실적 값은 refined_sales_record를 팀(또는 전체 "국내")×배치 단위로 SUM한다 — 모든
소계(재료비 계/노무비 계/경비 계/판관비 세부 등)는 app.services.refinement에서
이미 실측 검증한 공식으로 계산되어 저장된 컬럼이므로 그대로 합산하면 된다.
계획 값은 team_pl_record(계정과목×월, "손익계산서" 파일 업로드 결과)에서 조회한다 —
이 데이터에는 "재료비 계" 같은 중간 소계 행이 없어(§6.2), PLAN_ITEM_GROUPS로 leaf
계정과목을 합산해 실적과 동일한 소계를 만든다. team_pl_record는 팀×월 단위로만
존재하므로(고객·상품 등 세부 차원이 없다), 계획 쪽은 팀 필터만 적용한다 — 나머지
드릴다운 필터(고객/상품/DESC/제품구분1~3)는 실적(전월 포함) 쪽에만 적용된다.
"""
from __future__ import annotations

from dataclasses import dataclass

TEAMS = ["모티브", "고정형", "차량대리점", "차량OE"]
ALL_TEAMS_LABEL = "국내"

# 드릴다운 필터로 지원하는 refined_sales_record 컬럼 (F4 화면의 필터 항목과 1:1 대응)
FILTER_COLUMNS: dict[str, str] = {
    "customer": "customer_name",
    "product_code": "product_code",
    "desc": "product_desc",
    "product_group_1": "product_group_1",
    "product_group_2": "product_group_2",
    "product_group_3": "product_group",
}

# report_key(=refined_sales_record 컬럼명) -> 표시 라벨
LINE_ITEMS: list[tuple[str, str]] = [
    ("quantity", "매출수량"),
    ("sales_final", "매출액"),
    ("raw_material_sunyeon", "원재료비_순연"),
    ("raw_material_gyeongyeon", "원재료비_경연"),
    ("raw_material_calcium", "원재료비_칼슘연"),
    # 원재료비_니켈·원재료비_리튬은 항상 0이라(§4의 원본 수식 자체는 존재) 목록에서
    # 숨긴다(사용자 확인) — raw_material_total 계산에는 여전히 포함된다.
    ("raw_material_total", "원재료비 계"),
    ("main_material_jeonjo", "주재료비_전조"),
    ("main_material_kaba", "주재료비_카바"),
    ("main_material_gyeorimpan", "주재료비_격리판"),
    ("main_material_total", "주재료비 계"),
    ("other_material_supplies", "부재료비"),
    ("other_material_etc", "기타재료비(포장비 등) 계"),
    ("material_total", "재료비 계"),
    ("labor_variable_direct", "변동직접노무비"),
    ("labor_fixed_direct", "고정직접노무비"),
    ("labor_direct", "직접노무비 계"),
    ("labor_indirect", "간접노무비"),
    ("labor_total", "노무비 계"),
    ("expense_variable", "변동경비"),
    ("expense_fixed", "고정경비"),
    ("expense_outsourcing", "외주가공비"),
    ("expense_total", "경비 계"),
    ("cogs_final", "매출원가"),
    ("sga_vehicle", "차량유지비"),
    ("sga_delivery", "운반비"),
    ("sga_export", "수출비용"),
    ("sga_installation", "시험설치비"),
    ("sga_warranty", "판매보증비"),
    ("sga_defect_loss", "불량제품손실"),
    ("sga_ocean_freight", "해상운임"),
    ("sga_variable", "변동판관비 계"),
    ("sga_personnel", "판관인건비"),
    ("sga_welfare", "복리후생비"),
    ("sga_entertainment", "접대비"),
    ("sga_fees", "지급수수료"),
    ("sga_other", "기타-판관비"),
    ("sga_fixed", "고정판관비 계"),
    ("sga_final", "판관비 계"),
    ("operating_profit_final", "영업이익"),
]

# 계획(team_pl_record.account_item) 쪽은 leaf 계정과목만 있어 소계를 여기서 합산한다.
# 실적(refined_sales_record) 쪽 REQUIRED_RAW_COLUMNS 명칭과 동일한 원본 계정과목명을 쓴다
# (.docs/03_데이터정제.md §6.2 — 손익계산서 파일의 행 라벨은 Raw Data 헤더와 대체로 일치).
PLAN_ITEM_GROUPS: dict[str, list[str]] = {
    "quantity": ["매출수량"],
    "sales_final": ["매출액(Total)"],
    "raw_material_sunyeon": ["원재료비_순연"],
    "raw_material_gyeongyeon": ["원재료비_경연"],
    "raw_material_calcium": ["원재료비_칼슘연"],
    "raw_material_total": ["원재료비_순연", "원재료비_경연", "원재료비_칼슘연", "원재료비_니켈(A)", "원재료비_리튬(A)"],
    "main_material_jeonjo": ["주재료비_전조(A)"],
    "main_material_kaba": ["주재료비_카바(A)"],
    "main_material_gyeorimpan": ["주재료비_격리판(A"],
    "main_material_total": ["주재료비_전조(A)", "주재료비_카바(A)", "주재료비_격리판(A"],
    "other_material_supplies": ["부재료비(A)"],
    "other_material_etc": ["포장비(A)", "부대품재료비(A)", "부산물공제(A)"],
    "material_total": [
        "원재료비_순연", "원재료비_경연", "원재료비_칼슘연", "원재료비_니켈(A)", "원재료비_리튬(A)",
        "주재료비_전조(A)", "주재료비_카바(A)", "주재료비_격리판(A",
        "부재료비(A)", "포장비(A)", "부대품재료비(A)", "부산물공제(A)",
    ],
    "labor_variable_direct": ["변동직접노무비(A)"],
    "labor_fixed_direct": ["고정직접노무비(A)"],
    "labor_direct": ["변동직접노무비(A)", "고정직접노무비(A)"],
    "labor_indirect": ["간접노무비(A)"],
    "labor_total": ["변동직접노무비(A)", "고정직접노무비(A)", "간접노무비(A)"],
    "expense_variable": ["변동경비(A)"],
    "expense_fixed": ["고정경비(A)"],
    "expense_outsourcing": ["외주가공비(A)"],
    "expense_total": ["변동경비(A)", "고정경비(A)", "외주가공비(A)"],
    "cogs_final": ["매출원가(A)Tot"],
    "sga_vehicle": ["차량유지비"],
    "sga_delivery": ["운반비"],
    "sga_export": ["수출비용(A)"],
    "sga_installation": ["시험설치비(A)"],
    "sga_warranty": ["판매보증비"],
    "sga_defect_loss": ["불량제품손실"],
    "sga_ocean_freight": ["수출비용_해상운임("],
    "sga_variable": [
        "차량유지비", "운반비", "수출비용(A)", "시험설치비(A)", "판매보증비", "불량제품손실", "수출비용_해상운임(",
    ],
    "sga_personnel": [
        "임원급여", "직원급여", "임원상여", "직원상여", "임금", "제수당", "잡급", "퇴직급여",
    ],
    "sga_welfare": ["복리후생비"],
    "sga_entertainment": ["접대비(A)"],
    "sga_fees": ["지급수수료"],
    # 대손상각비는 판관인건비가 아니라 여기 포함된다(실제 수식 확인, refinement.py 참고).
    "sga_other": [
        "대손상각비",
        "여비교통비", "통신비", "소모품비", "도서인쇄비", "세금과공과", "임차료", "수도광열비", "광고선전비",
        "교육훈련비", "감가상각비", "무형자산상각비", "수선유지비", "보험료", "회의비",
        "경상연구개발비", "연구개발비(국책과제", "대손충당금환입", "판관비_기타",
    ],
    "sga_fixed": [
        "임원급여", "직원급여", "임원상여", "직원상여", "임금", "제수당", "잡급", "퇴직급여",
        "복리후생비", "접대비(A)", "지급수수료",
        "대손상각비",
        "여비교통비", "통신비", "소모품비", "도서인쇄비", "세금과공과", "임차료", "수도광열비", "광고선전비",
        "교육훈련비", "감가상각비", "무형자산상각비", "수선유지비", "보험료", "회의비",
        "경상연구개발비", "연구개발비(국책과제", "대손충당금환입", "판관비_기타",
    ],
    "sga_final": ["판관비(Total)"],
    "operating_profit_final": ["영업이익(A)"],
}


@dataclass
class PLComparisonResult:
    """Phase 18(.docs/phase/phase_18_손익항목계획대비판정.md) — 드릴다운 필터(고객/
    상품/DESC/제품구분1~3)가 걸려 있으면 plan_comparison_available=False다. 계획
    (team_pl_record)은 팀×월 단위로만 존재해 이 필터들을 적용할 수 없는데, 실적만
    필터링된 값을 팀 전체 계획과 비교하면 왜곡된 계획대비 수치가 나오기 때문에(제품군
    하나의 실적을 팀 전체 계획과 비교하던 F3 계획대비의 기존 버그, Phase 17과 같은
    종류) 그 경우 각 라인의 diff_unit/diff_total/change_rate를 None으로 비운다."""
    plan_comparison_available: bool
    lines: list["PLLineComparison"]


@dataclass
class PLLineComparison:
    key: str
    label: str
    plan_unit: float | None
    plan_total: float
    plan_ratio: float | None  # 매출액 대비 비중(%)
    actual_unit: float | None
    actual_total: float
    actual_ratio: float | None
    diff_unit: float | None
    diff_total: float
    change_rate: float | None  # (실적-계획)/계획, 계획이 0이면 None
    prev_month_available: bool
    prev_month_unit: float | None
    prev_month_total: float | None
    prev_month_ratio: float | None
    diff_prev_month_unit: float | None
    diff_prev_month_total: float | None
    change_rate_prev_month: float | None  # (당월실적-전월실적)/전월실적


class PLComparisonError(ValueError):
    pass


def _prev_period(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _build_refined_filter(teams: list[str] | None, filters: dict[str, list[str]]) -> tuple[str, list]:
    clauses = []
    params: list = []
    if teams:
        placeholders = ", ".join(["?"] * len(teams))
        clauses.append(f"team IN ({placeholders})")
        params.extend(teams)
    for filter_key, values in filters.items():
        if not values:
            continue
        column = FILTER_COLUMNS[filter_key]
        placeholders = ", ".join(["?"] * len(values))
        clauses.append(f"{column} IN ({placeholders})")
        params.extend(values)
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _sum_refined(db, batch_id: str, teams: list[str] | None, column: str, filters: dict[str, list[str]]) -> float:
    where, params = _build_refined_filter(teams, filters)
    sql = f"SELECT SUM({column}) FROM refined_sales_record WHERE batch_id = ?{where}"
    row = db.connection.execute(sql, [batch_id, *params]).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _sum_plan(db, year: int, month: int, teams: list[str] | None, account_items: list[str]) -> float:
    # team_pl_record는 팀×월 단위뿐이라 고객/상품 등 드릴다운 필터는 적용할 수 없다.
    placeholders = ", ".join(["?"] * len(account_items))
    if not teams:
        sql = f"""
            SELECT SUM(amount) FROM team_pl_record
            WHERE year = ? AND month = ? AND account_item IN ({placeholders})
        """
        params = [year, month, *account_items]
    else:
        team_placeholders = ", ".join(["?"] * len(teams))
        sql = f"""
            SELECT SUM(amount) FROM team_pl_record
            WHERE year = ? AND month = ? AND team IN ({team_placeholders}) AND account_item IN ({placeholders})
        """
        params = [year, month, *teams, *account_items]
    row = db.connection.execute(sql, params).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _build_line(
    key: str,
    label: str,
    plan_total: float,
    actual_total: float,
    prev_total: float | None,
    *,
    plan_quantity: float,
    actual_quantity: float,
    plan_sales: float,
    actual_sales: float,
    prev_quantity: float | None,
    prev_sales: float | None,
    prev_available: bool,
) -> PLLineComparison:
    plan_unit = (plan_total / plan_quantity) if plan_quantity else None
    actual_unit = (actual_total / actual_quantity) if actual_quantity else None
    plan_ratio = (plan_total / plan_sales * 100) if plan_sales else None
    actual_ratio = (actual_total / actual_sales * 100) if actual_sales else None

    diff_total = actual_total - plan_total
    diff_unit = (actual_unit - plan_unit) if plan_unit is not None and actual_unit is not None else None
    change_rate = (diff_total / plan_total) if plan_total else None

    prev_month_unit = (prev_total / prev_quantity) if prev_available and prev_quantity else None
    prev_month_ratio = (prev_total / prev_sales * 100) if prev_available and prev_sales else None
    diff_prev_month_total = (actual_total - prev_total) if prev_available else None
    diff_prev_month_unit = (
        (actual_unit - prev_month_unit) if actual_unit is not None and prev_month_unit is not None else None
    )
    change_rate_prev_month = (diff_prev_month_total / prev_total) if prev_available and prev_total else None

    return PLLineComparison(
        key=key,
        label=label,
        plan_unit=plan_unit,
        plan_total=plan_total,
        plan_ratio=plan_ratio,
        actual_unit=actual_unit,
        actual_total=actual_total,
        actual_ratio=actual_ratio,
        diff_unit=diff_unit,
        diff_total=diff_total,
        change_rate=change_rate,
        prev_month_available=prev_available,
        prev_month_unit=prev_month_unit,
        prev_month_total=(prev_total if prev_available else None),
        prev_month_ratio=prev_month_ratio,
        diff_prev_month_unit=diff_prev_month_unit,
        diff_prev_month_total=diff_prev_month_total,
        change_rate_prev_month=change_rate_prev_month,
    )


def get_pl_comparison(
    db,
    batch_id: str,
    team: list[str] | None = None,
    *,
    customer: list[str] | None = None,
    product_code: list[str] | None = None,
    desc: list[str] | None = None,
    product_group_1: list[str] | None = None,
    product_group_2: list[str] | None = None,
    product_group_3: list[str] | None = None,
) -> PLComparisonResult:
    """배치(=연/월)에 대해 팀별(또는 team=None -> 국내 전체) 계획 대비/전월 대비 실적
    손익계산서를 반환한다. customer/product_code/desc/product_group_1~3은 실적(당월·전월)
    쪽에만 적용되는 드릴다운 필터다(계획은 팀×월 단위라 이 필터들을 적용할 수 없다).
    각 필터는 여러 값을 동시에 선택할 수 있다(사용자 확인 — 드릴다운 다중 선택), 값들은
    OR(=IN절)로 묶이고 필터 종류 사이는 AND로 묶인다.
    """
    for t in team or []:
        if t not in TEAMS:
            raise PLComparisonError(f"알 수 없는 팀입니다: {t!r} (허용: {TEAMS})")

    period = db.batch_period(batch_id)
    if period is None:
        raise PLComparisonError(f"존재하지 않는 batch_id 입니다: {batch_id}")
    year, month = period

    filters = {
        "customer": customer,
        "product_code": product_code,
        "desc": desc,
        "product_group_1": product_group_1,
        "product_group_2": product_group_2,
        "product_group_3": product_group_3,
    }

    prev_year, prev_month = _prev_period(year, month)
    prev_batch_id = db.find_batch_id_by_period(prev_year, prev_month)

    actual_values: dict[str, float] = {
        key: _sum_refined(db, batch_id, team, key, filters) for key, _ in LINE_ITEMS
    }
    plan_values: dict[str, float] = {
        key: _sum_plan(db, year, month, team, PLAN_ITEM_GROUPS[key]) for key, _ in LINE_ITEMS
    }
    prev_values: dict[str, float] | None = None
    if prev_batch_id is not None:
        prev_values = {
            key: _sum_refined(db, prev_batch_id, team, key, filters) for key, _ in LINE_ITEMS
        }

    plan_quantity = plan_values["quantity"]
    actual_quantity = actual_values["quantity"]
    plan_sales = plan_values["sales_final"]
    actual_sales = actual_values["sales_final"]
    prev_quantity = prev_values["quantity"] if prev_values else None
    prev_sales = prev_values["sales_final"] if prev_values else None

    prev_month_available = prev_values is not None

    def _line(key: str, label: str, plan_total: float, actual_total: float, prev_total: float | None) -> PLLineComparison:
        return _build_line(
            key,
            label,
            plan_total,
            actual_total,
            prev_total,
            plan_quantity=plan_quantity,
            actual_quantity=actual_quantity,
            plan_sales=plan_sales,
            actual_sales=actual_sales,
            prev_quantity=prev_quantity,
            prev_sales=prev_sales,
            prev_available=prev_month_available,
        )

    results: list[PLLineComparison] = [
        _line(key, label, plan_values[key], actual_values[key], prev_values[key] if prev_values else None)
        for key, label in LINE_ITEMS
    ]

    # "기타(상품구매,재고실사차이 등)"과 "총원가"는 team_pl_record에 대응하는 leaf
    # 계정과목이 없어(참고 파일 "검색용" 시트 "1) 계획 대비" 표에서 확인된 잔여/합산
    # 행) PLAN_ITEM_GROUPS로 조회하지 않고, 이미 계산된 다른 항목들로부터 순수
    # 산술로 도출한다 — 매출원가(cogs_final)는 refinement.py가 원본 "매출원가
    # (A)Tot"를 그대로 채택하므로(재료비+노무비+경비의 합과 정확히 일치하지 않음),
    # 그 차액이 곧 원본 수식의 "기타매출원가+실제매출원가조정" 잔여값이다.
    other_cogs_plan = plan_values["cogs_final"] - plan_values["material_total"] - plan_values["labor_total"] - plan_values["expense_total"]
    other_cogs_actual = (
        actual_values["cogs_final"] - actual_values["material_total"] - actual_values["labor_total"] - actual_values["expense_total"]
    )
    other_cogs_prev = (
        prev_values["cogs_final"] - prev_values["material_total"] - prev_values["labor_total"] - prev_values["expense_total"]
        if prev_values is not None
        else None
    )
    other_cogs_line = _line("other_cogs", "기타(상품구매,재고실사차이 등)", other_cogs_plan, other_cogs_actual, other_cogs_prev)
    cogs_idx = next(i for i, r in enumerate(results) if r.key == "cogs_final")
    results.insert(cogs_idx, other_cogs_line)

    total_cost_plan = plan_values["cogs_final"] + plan_values["sga_final"]
    total_cost_actual = actual_values["cogs_final"] + actual_values["sga_final"]
    total_cost_prev = (prev_values["cogs_final"] + prev_values["sga_final"]) if prev_values is not None else None
    total_cost_line = _line("total_cost", "총원가", total_cost_plan, total_cost_actual, total_cost_prev)
    profit_idx = next(i for i, r in enumerate(results) if r.key == "operating_profit_final")
    results.insert(profit_idx, total_cost_line)

    plan_comparison_available = not any(filters.values())
    if not plan_comparison_available:
        for line in results:
            line.diff_unit = None
            line.diff_total = None
            line.change_rate = None

    return PLComparisonResult(plan_comparison_available=plan_comparison_available, lines=results)


def get_pl_comparison_filter_options(db, batch_id: str) -> dict[str, list[str]]:
    """F4 드릴다운 화면의 필터 드롭다운을 채우기 위해, 이 배치에 실제로 존재하는
    고객/상품/DESC/제품구분1~3 값 목록을 반환한다(팀은 TEAMS 상수로 고정)."""
    if db.batch_period(batch_id) is None:
        raise PLComparisonError(f"존재하지 않는 batch_id 입니다: {batch_id}")

    options: dict[str, list[str]] = {"teams": TEAMS}
    for filter_key, column in FILTER_COLUMNS.items():
        rows = db.connection.execute(
            f"SELECT DISTINCT {column} FROM refined_sales_record "
            f"WHERE batch_id = ? AND {column} IS NOT NULL ORDER BY {column}",
            [batch_id],
        ).fetchall()
        options[filter_key] = [r[0] for r in rows]
    return options
