"""DuckDB 연결 및 스키마 관리 (PRD 7장 데이터 모델의 F1·F2 부분집합)."""
from __future__ import annotations

from pathlib import Path

import duckdb

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.duckdb"

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS upload_batch (
        batch_id VARCHAR PRIMARY KEY,
        upload_date TIMESTAMP,
        target_year INTEGER,
        target_month INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS uploaded_file (
        file_id VARCHAR PRIMARY KEY,
        batch_id VARCHAR,
        file_name VARCHAR,
        file_type VARCHAR,
        recognition_method VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_mapping (
        mapping_key VARCHAR PRIMARY KEY,
        team VARCHAR,
        product_code VARCHAR,
        division VARCHAR,
        usage VARCHAR,
        product_group_1 VARCHAR,
        product_group_2 VARCHAR,
        product_group_3 VARCHAR,
        product_group_4 VARCHAR,
        material_desc VARCHAR
    )
    """,
    """
    -- 지점코드 매핑표(.docs/03_데이터정제.md §3.5) — 08월 실제 파일로 신규 확인됨.
    -- "팀+거래처코드" 합성 키(mapping_key)로 권역/사업소/파트를 조회한다.
    -- product_mapping과 달리 모티브·고정형도 "산전" 접두사 없이 팀명을 그대로 쓴다.
    CREATE TABLE IF NOT EXISTS branch_mapping (
        mapping_key VARCHAR PRIMARY KEY,
        team VARCHAR,
        customer_code VARCHAR,
        customer_name VARCHAR,
        region VARCHAR,
        office VARCHAR,
        part VARCHAR
    )
    """,
    """
    -- 판매계획 파일의 실제 구조를 더미 샘플로 확인했다(.docs/03_데이터정제.md §6.1).
    -- 팀·년·월 단위가 아니라 거래처×제품군×월 단위이며, planned_amount(금액)는 원본
    -- 셀 수식(판가×수량)이 계산 캐시되어 있지 않을 수 있어 파서가 직접 계산해 채운다.
    -- hq_report_group("본부보고용")은 product_group/product_type과는 다른 제3의 분류
    -- 축으로 확인되어(PRD 미해결 질문 17번), 지금은 통합하지 않고 원본 그대로 보존만 한다.
    CREATE TABLE IF NOT EXISTS sales_plan_record (
        record_id VARCHAR PRIMARY KEY,
        file_id VARCHAR,
        batch_id VARCHAR,
        team VARCHAR,
        customer_code VARCHAR,
        customer_name VARCHAR,
        delivery_code VARCHAR,
        delivery_name VARCHAR,
        sales_rep VARCHAR,
        category VARCHAR,
        product_type VARCHAR,
        hq_report_group VARCHAR,
        year INTEGER,
        month INTEGER,
        unit_price DOUBLE,
        quantity DOUBLE,
        planned_amount DOUBLE
    )
    """,
    """
    -- 팀별 손익계산서 파일의 실제 구조를 더미 샘플로 확인했다(.docs/03_데이터정제.md §6.2).
    -- 팀×계정과목×월 단위이며, 매출원가(A)Tot/매출총이익(A)/판관비(Total)/영업이익(A)
    -- 4개 소계 행은 원본 수식(SUM 범위·뺄셈)이 계산 캐시되어 있지 않아 파서가 직접
    -- 계산해 채운다 (판매계획의 금액=판가×수량과 동일한 문제).
    CREATE TABLE IF NOT EXISTS team_pl_record (
        record_id VARCHAR PRIMARY KEY,
        file_id VARCHAR,
        batch_id VARCHAR,
        team VARCHAR,
        account_item VARCHAR,
        year INTEGER,
        month INTEGER,
        amount DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS refined_sales_record (
        record_id VARCHAR PRIMARY KEY,
        batch_id VARCHAR,
        file_id VARCHAR,
        year INTEGER,
        month INTEGER,
        team VARCHAR,
        customer_code VARCHAR,
        customer_name VARCHAR,
        product_code VARCHAR,
        product_desc VARCHAR,
        product_group VARCHAR,
        product_group_1 VARCHAR,
        product_group_2 VARCHAR,
        is_mapped BOOLEAN,
        region VARCHAR,
        office VARCHAR,
        part VARCHAR,
        is_branch_mapped BOOLEAN,
        sales_provisional DOUBLE,
        sales_discount DOUBLE,
        sales_adjustment DOUBLE,
        sales_final_ops DOUBLE,
        sales_other DOUBLE,
        sales_pre_adjust DOUBLE,
        plan_adjustment DOUBLE,
        sales_final DOUBLE,
        raw_material_sunyeon DOUBLE,
        raw_material_gyeongyeon DOUBLE,
        raw_material_calcium DOUBLE,
        raw_material_nickel DOUBLE,
        raw_material_lithium DOUBLE,
        raw_material_total DOUBLE,
        main_material_jeonjo DOUBLE,
        main_material_kaba DOUBLE,
        main_material_gyeorimpan DOUBLE,
        main_material_total DOUBLE,
        other_material_supplies DOUBLE,
        other_material_etc DOUBLE,
        material_total DOUBLE,
        labor_variable_direct DOUBLE,
        labor_fixed_direct DOUBLE,
        labor_direct DOUBLE,
        labor_indirect DOUBLE,
        labor_total DOUBLE,
        expense_variable DOUBLE,
        expense_fixed DOUBLE,
        expense_outsourcing DOUBLE,
        expense_total DOUBLE,
        sga_vehicle DOUBLE,
        sga_delivery DOUBLE,
        sga_export DOUBLE,
        sga_installation DOUBLE,
        sga_warranty DOUBLE,
        sga_defect_loss DOUBLE,
        sga_ocean_freight DOUBLE,
        sga_variable DOUBLE,
        sga_personnel DOUBLE,
        sga_welfare DOUBLE,
        sga_entertainment DOUBLE,
        sga_fees DOUBLE,
        sga_other DOUBLE,
        sga_fixed DOUBLE,
        cogs_pre_adjust DOUBLE,
        cogs_final DOUBLE,
        standard_cogs DOUBLE,
        sga_pre_adjust DOUBLE,
        sga_final DOUBLE,
        operating_profit_pre_adjust DOUBLE,
        operating_profit_final DOUBLE,
        quantity_raw DOUBLE,
        quantity DOUBLE,
        inventory_diff DOUBLE,
        is_calc_error BOOLEAN,
        calc_error_reason VARCHAR
    )
    """,
    """
    -- F3/F4가 사용하는 팀×제품군 단위 집계 (당월 기준, MTD). YTD는 Day 3에서
    -- 여러 배치를 조회해 계산하며 이 테이블에 별도 저장하지 않는다.
    CREATE TABLE IF NOT EXISTS aggregated_result (
        result_id VARCHAR PRIMARY KEY,
        batch_id VARCHAR,
        year INTEGER,
        month INTEGER,
        team VARCHAR,
        product_group VARCHAR,
        quantity DOUBLE,
        actual_amount DOUBLE,
        profit DOUBLE,
        profit_rate DOUBLE,
        sga_amount DOUBLE,
        avg_unit_price DOUBLE,
        plan_amount DOUBLE,
        achievement_rate DOUBLE,
        prev_month_available BOOLEAN,
        prev_month_amount DOUBLE,
        prev_month_profit DOUBLE,
        prev_month_sga_amount DOUBLE,
        prev_month_avg_unit_price DOUBLE,
        prev_year_month_available BOOLEAN,
        prev_year_month_amount DOUBLE,
        prev_year_month_profit DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS threshold_config (
        config_id VARCHAR PRIMARY KEY,
        metric_type VARCHAR UNIQUE,
        threshold_value DOUBLE,
        threshold_low DOUBLE,
        threshold_high DOUBLE,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS anomaly_flag (
        flag_id VARCHAR PRIMARY KEY,
        batch_id VARCHAR,
        result_id VARCHAR,
        team VARCHAR,
        product_group VARCHAR,
        metric_type VARCHAR,
        actual_value DOUBLE,
        threshold_value DOUBLE,
        impact_amount DOUBLE,
        is_confirmed_by_user BOOLEAN
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS report_draft (
        draft_id VARCHAR PRIMARY KEY,
        batch_id VARCHAR,
        created_at TIMESTAMP,
        status VARCHAR
    )
    """,
    """
    -- chart_ref는 F7 화면이 기존 GET /batches/{id}/trend?team=...을 그대로 재사용해
    -- 추이 차트를 그릴 수 있도록 "team" 값만 담는다 (별도 차트 이미지를 생성하지 않는다).
    -- is_excluded: F8 "이상징후 항목 삭제/제외 토글" — 실제로 행을 지우지 않고 보고서
    -- export(F9)에서만 제외한다. background_note: F8 담당자 배경 설명(자유 텍스트),
    -- user_comment(자동 코멘트 수정)와는 별개로 추가되는 설명이다.
    CREATE TABLE IF NOT EXISTS report_item (
        item_id VARCHAR PRIMARY KEY,
        draft_id VARCHAR,
        flag_id VARCHAR,
        auto_comment VARCHAR,
        user_comment VARCHAR,
        chart_ref VARCHAR,
        is_excluded BOOLEAN DEFAULT FALSE,
        background_note VARCHAR
    )
    """,
]

# CREATE TABLE IF NOT EXISTS는 이미 존재하는 로컬 DuckDB 파일(backend/data/app.duckdb)의
# 테이블에는 새 컬럼을 추가하지 않는다 — Day 5에서 report_item에 is_excluded/
# background_note를 추가했을 때 기존 파일에 반영되지 않아 500 에러가 발생한 것으로 확인됨.
# 정식 마이그레이션 도구 없이도 스키마가 늘어날 때마다 기존 로컬 DB가 깨지지 않도록,
# 테이블 생성 직후 누락된 컬럼을 추가한다(이미 있으면 아무 일도 하지 않는다).
COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("report_item", "is_excluded", "BOOLEAN DEFAULT FALSE"),
    ("report_item", "background_note", "VARCHAR"),
    ("sales_plan_record", "customer_code", "VARCHAR"),
    ("sales_plan_record", "customer_name", "VARCHAR"),
    ("sales_plan_record", "delivery_code", "VARCHAR"),
    ("sales_plan_record", "delivery_name", "VARCHAR"),
    ("sales_plan_record", "sales_rep", "VARCHAR"),
    ("sales_plan_record", "category", "VARCHAR"),
    ("sales_plan_record", "product_type", "VARCHAR"),
    ("sales_plan_record", "hq_report_group", "VARCHAR"),
    ("sales_plan_record", "unit_price", "DOUBLE"),
    ("sales_plan_record", "quantity", "DOUBLE"),
    ("team_pl_record", "team", "VARCHAR"),
    ("team_pl_record", "account_item", "VARCHAR"),
    ("team_pl_record", "year", "INTEGER"),
    ("team_pl_record", "month", "INTEGER"),
    ("team_pl_record", "amount", "DOUBLE"),
    ("refined_sales_record", "region", "VARCHAR"),
    ("refined_sales_record", "office", "VARCHAR"),
    ("refined_sales_record", "part", "VARCHAR"),
    ("refined_sales_record", "is_branch_mapped", "BOOLEAN"),
    ("refined_sales_record", "quantity_raw", "DOUBLE"),
    ("refined_sales_record", "other_material_supplies", "DOUBLE"),
    ("refined_sales_record", "other_material_etc", "DOUBLE"),
    ("refined_sales_record", "material_total", "DOUBLE"),
    ("refined_sales_record", "labor_direct", "DOUBLE"),
    ("refined_sales_record", "labor_indirect", "DOUBLE"),
    ("refined_sales_record", "labor_total", "DOUBLE"),
    ("refined_sales_record", "expense_variable", "DOUBLE"),
    ("refined_sales_record", "expense_fixed", "DOUBLE"),
    ("refined_sales_record", "expense_outsourcing", "DOUBLE"),
    ("refined_sales_record", "expense_total", "DOUBLE"),
    ("refined_sales_record", "sga_variable", "DOUBLE"),
    ("refined_sales_record", "sga_personnel", "DOUBLE"),
    ("refined_sales_record", "sga_welfare", "DOUBLE"),
    ("refined_sales_record", "sga_entertainment", "DOUBLE"),
    ("refined_sales_record", "sga_fees", "DOUBLE"),
    ("refined_sales_record", "sga_other", "DOUBLE"),
    ("refined_sales_record", "sga_fixed", "DOUBLE"),
    ("refined_sales_record", "product_group_1", "VARCHAR"),
    ("refined_sales_record", "product_group_2", "VARCHAR"),
    ("refined_sales_record", "labor_variable_direct", "DOUBLE"),
    ("refined_sales_record", "labor_fixed_direct", "DOUBLE"),
    ("refined_sales_record", "sga_vehicle", "DOUBLE"),
    ("refined_sales_record", "sga_delivery", "DOUBLE"),
    ("refined_sales_record", "sga_export", "DOUBLE"),
    ("refined_sales_record", "sga_installation", "DOUBLE"),
    ("refined_sales_record", "sga_warranty", "DOUBLE"),
    ("refined_sales_record", "sga_defect_loss", "DOUBLE"),
    ("refined_sales_record", "sga_ocean_freight", "DOUBLE"),
    ("refined_sales_record", "standard_cogs", "DOUBLE"),
]


class Database:
    """duckdb 연결 하나를 감싸는 얇은 래퍼. 테스트에서는 in-memory로 사용한다."""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(self.path)
        self.init_schema()

    def init_schema(self) -> None:
        for stmt in SCHEMA_STATEMENTS:
            self.connection.execute(stmt)
        for table, column, ddl_type in COLUMN_MIGRATIONS:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl_type}")

    def delete_batch(self, batch_id: str) -> None:
        # sales_plan_record는 제외한다: 연간 판매계획은 특정 월 배치에 종속된 데이터가
        # 아니라 여러 배치에 걸쳐 조회되는 참조 데이터이므로, 특정 월을 재업로드해도
        # 유지되어야 한다 (제품분류 매핑표와 동일한 취급).
        self.connection.execute(
            "DELETE FROM report_item WHERE draft_id IN (SELECT draft_id FROM report_draft WHERE batch_id = ?)",
            [batch_id],
        )
        for table in (
            "report_draft",
            "anomaly_flag",
            "aggregated_result",
            "refined_sales_record",
            "team_pl_record",
            "uploaded_file",
            "upload_batch",
        ):
            self.connection.execute(f"DELETE FROM {table} WHERE batch_id = ?", [batch_id])

    def find_batch_id_by_period(self, year: int, month: int) -> str | None:
        row = self.connection.execute(
            "SELECT batch_id FROM upload_batch WHERE target_year = ? AND target_month = ?",
            [year, month],
        ).fetchone()
        return row[0] if row else None

    def has_product_mapping(self) -> bool:
        row = self.connection.execute("SELECT COUNT(*) FROM product_mapping").fetchone()
        return bool(row and row[0] > 0)

    def batch_period(self, batch_id: str) -> tuple[int, int] | None:
        row = self.connection.execute(
            "SELECT target_year, target_month FROM upload_batch WHERE batch_id = ?", [batch_id]
        ).fetchone()
        return (row[0], row[1]) if row else None

    def close(self) -> None:
        self.connection.close()


_default_db: Database | None = None


def get_db() -> Database:
    """FastAPI Depends()에서 사용하는 기본 DB 인스턴스 (프로세스당 1개)."""
    global _default_db
    if _default_db is None:
        _default_db = Database()
    return _default_db
