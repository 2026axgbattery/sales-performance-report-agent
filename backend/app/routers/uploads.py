"""F1 파일 업로드 + F2 데이터 정제·매핑 API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.db import Database, get_db
from app.services.aggregation import compute_aggregates_for_batch
from app.services.anomaly import evaluate_anomalies
from app.services.branch import BranchMappingTable, BranchValidationError
from app.services.mapping import MappingValidationError, ProductMappingTable, parse_mapping_upload
from app.services.plan import PlanValidationError, parse_plan_workbook
from app.services.refinement import REFINED_ROW_COLUMNS, RawColumnValidationError, refine_actual_records
from app.services.team_pl import TeamPLValidationError, parse_team_pl_workbook
from app.services.validation import (
    REQUIRED_FILE_TYPE,
    FileParseError,
    UnknownFileCategoryError,
    UnsupportedFileTypeError,
    read_dataframe,
    validate_file_category,
)

router = APIRouter()


@router.post("/uploads")
async def create_upload(
    files: List[UploadFile] = File(...),
    file_types: List[str] = Form(...),
    # Phase 19(.docs/phase/phase_19_실적파일다중월분할업로드.md) — 실적 파일 하나에
    # 여러 달치 데이터가 섞여 있고 그중 일부가 이미 배치가 있는 달과 겹칠 때만 쓰는
    # 확인 플래그다. 파일이 단일 기간만 담고 있으면(기존 실사용 방식) 이 값과 무관하게
    # 항상 자동으로 덮어쓴다(하위 호환 — 기존 F6 재계산/순차 월별 업로드 워크플로우가
    # 확인 없이 동작해야 하므로).
    confirm_overwrite: Optional[bool] = Form(default=None),
    db: Database = Depends(get_db),
):
    if len(files) != len(file_types):
        raise HTTPException(
            status_code=400,
            detail="files와 file_types의 개수가 일치해야 합니다.",
        )

    if REQUIRED_FILE_TYPE not in file_types:
        raise HTTPException(
            status_code=400,
            detail=f"필수 파일이 없습니다: '{REQUIRED_FILE_TYPE}' 파일을 1건 이상 업로드해야 합니다.",
        )

    # 판매계획·손익계산서·매핑표 파일은 시트가 여러 개인 실제 구조(.docs/03_데이터정제.md
    # §3.5·§6.1·§6.2)라 단일 시트를 가정하는 read_dataframe으로는 읽을 수 없다 — content(원본
    # 바이트)를 그대로 보관해 각각의 전용 파서에 넘긴다.
    MULTI_SHEET_TYPES = {"계획", "손익계산서", "매핑표"}
    loaded: list[tuple[UploadFile, str, "pd.DataFrame | None", bytes]] = []  # noqa: F821
    for f, ftype in zip(files, file_types):
        try:
            validate_file_category(ftype)
            content = await f.read()
            df = None if ftype in MULTI_SHEET_TYPES else read_dataframe(f.filename, content)
        except (UnsupportedFileTypeError, UnknownFileCategoryError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileParseError as exc:
            raise HTTPException(status_code=400, detail=f"'{f.filename}' — {exc}") from exc
        loaded.append((f, ftype, df, content))

    # ── 매핑표 처리 (없으면 기존 저장분 재사용) ─────────────────────────
    # 매핑표는 제품분류(필수)와 지점코드(있으면 함께, .docs/03_데이터정제.md §3.5)를
    # 한 파일에 담아 올릴 수 있다 — CSV는 제품분류만, xlsx/xlsb는 시트명으로 둘 다 찾는다.
    mapping_uploaded = False
    branch_mapping: BranchMappingTable | None = None
    for f, ftype, _df, content in loaded:
        if ftype != "매핑표":
            continue
        try:
            product_df, branch_df = parse_mapping_upload(f.filename, content)
            mapping_table = ProductMappingTable.from_dataframe(product_df)
        except MappingValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"'{f.filename}' — {exc}",
            ) from exc
        _store_product_mapping(db, product_df)
        mapping_uploaded = True

        if branch_df is not None:
            try:
                branch_mapping = BranchMappingTable.from_dataframe(branch_df)
            except BranchValidationError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{f.filename}' — {exc}",
                ) from exc
            _store_branch_mapping(db, branch_df)

    if not mapping_uploaded:
        if not db.has_product_mapping():
            raise HTTPException(
                status_code=400,
                detail="제품분류 매핑표가 없습니다. 최초 업로드 시에는 매핑표를 함께 업로드해야 합니다.",
            )
        mapping_table = _load_product_mapping(db)
        branch_mapping = _load_branch_mapping(db)

    # ── 판매계획 파일 검증·파싱 ─────────────────────────────────────────
    plan_entries_by_file: dict[int, list] = {}
    for f, ftype, _df, content in loaded:
        if ftype != "계획":
            continue
        try:
            plan_entries_by_file[id(f)] = parse_plan_workbook(content)
        except PlanValidationError as exc:
            raise HTTPException(status_code=400, detail=f"'{f.filename}' — {exc}") from exc

    # ── 실적 파일 검증·정제 ────────────────────────────────────────────
    actual_files = [(f, df) for f, ftype, df, _content in loaded if ftype == REQUIRED_FILE_TYPE]
    refinement_results = []
    batch_periods: set[tuple[int, int]] = set()
    for f, df in actual_files:
        try:
            result = refine_actual_records(df, mapping_table, branch_mapping)
        except RawColumnValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"'{f.filename}' — {exc}",
            ) from exc
        if not result.rows:
            raise HTTPException(status_code=400, detail=f"'{f.filename}' — 실적 데이터가 비어 있습니다.")
        # year=0/month=0은 "기간/연도" 값을 해석할 수 없었던 행의 더미값이다(refinement.py
        # 참고) — 실제 기간이 아니므로 배치 기간 판정에서 제외한다(그 행 자체는 계산오류로
        # 표시된 채 그대로 저장된다, 업로드 전체를 크래시시키지 않는다).
        periods = {(r.year, r.month) for r in result.rows if r.year and r.month}
        batch_periods |= periods
        refinement_results.append((f, result))

    if not batch_periods:
        raise HTTPException(
            status_code=400,
            detail="실적 파일에서 유효한 '기간/연도' 값을 찾을 수 없습니다.",
        )

    period_warning = None
    if len(batch_periods) > 1:
        period_warning = (
            f"업로드된 실적 파일들의 대상 기간이 서로 다릅니다: {sorted(batch_periods)}"
        )

    target_year, target_month = sorted(batch_periods)[0]

    # ── 팀별 손익계산서 파일 검증·파싱 ───────────────────────────────────
    # 세로형(팀×월 행) 파일은 연도 정보가 없어 실적 파일의 target_year가 확정된
    # 뒤에야 파싱할 수 있다(app/services/team_pl.py 모듈 docstring 참고).
    team_pl_entries_by_file: dict[int, list] = {}
    for f, ftype, _df, content in loaded:
        if ftype != "손익계산서":
            continue
        try:
            team_pl_entries_by_file[id(f)] = parse_team_pl_workbook(content, year=target_year)
        except TeamPLValidationError as exc:
            raise HTTPException(status_code=400, detail=f"'{f.filename}' — {exc}") from exc

    file_summaries = [{"file_name": f.filename, "file_type": ftype} for f, ftype, _, _ in loaded]

    # ── 실적 파일이 단일 기간만 담고 있는 경우: 기존 동작 그대로(하위 호환) ──
    # 확인 없이 항상 자동으로 덮어쓴다 — F6 재계산, 순차 월별 업로드 등 기존
    # 워크플로우 전체가 이 즉시-커밋 동작에 의존하고 있어 그대로 유지한다.
    if len(batch_periods) <= 1:
        existing_batch_id = db.find_batch_id_by_period(target_year, target_month)
        if existing_batch_id:
            db.delete_batch(existing_batch_id)

        batch_id = str(uuid.uuid4())
        db.connection.execute(
            "INSERT INTO upload_batch (batch_id, upload_date, target_year, target_month) VALUES (?, ?, ?, ?)",
            [batch_id, datetime.now(), target_year, target_month],
        )

        total_rows = 0
        unmapped_rows = 0
        calc_error_rows = 0

        for f, ftype, _df, _content in loaded:
            file_id = str(uuid.uuid4())
            db.connection.execute(
                "INSERT INTO uploaded_file (file_id, batch_id, file_name, file_type, recognition_method) "
                "VALUES (?, ?, ?, ?, ?)",
                [file_id, batch_id, f.filename, ftype, "사용자 지정"],
            )
            for actual_f, result in refinement_results:
                if actual_f is f:
                    _store_refined_rows(db, batch_id, file_id, result.rows)
                    total_rows += result.total_count
                    unmapped_rows += result.unmapped_count
                    calc_error_rows += result.calc_error_count

            if id(f) in plan_entries_by_file:
                _store_plan_records(db, batch_id, file_id, plan_entries_by_file[id(f)])

            if id(f) in team_pl_entries_by_file:
                _store_team_pl_records(db, batch_id, file_id, team_pl_entries_by_file[id(f)])

        aggregated_count = compute_aggregates_for_batch(db, batch_id)
        anomaly_count = evaluate_anomalies(db, batch_id)

        batch_summary = {
            "batch_id": batch_id,
            "target_period": f"{target_year:04d}-{target_month:02d}",
            "overwrote_existing_batch": existing_batch_id is not None,
            "total_rows": total_rows,
            "unmapped_rows": unmapped_rows,
            "calc_error_rows": calc_error_rows,
            "aggregated_groups": aggregated_count,
            "anomaly_count": anomaly_count,
        }
        return {
            **batch_summary,
            "files": file_summaries,
            "warning": period_warning,
            "requires_confirmation": False,
            "batches": [batch_summary],
            "skipped_periods": [],
        }

    # ── Phase 19: 실적 파일 하나에 여러 기간이 섞여 있는 경우 ───────────────
    # (.docs/phase/phase_19_실적파일다중월분할업로드.md, 사용자 확인) — 각 행의
    # 실제 (연,월)로 나눠 기간마다 별도 배치를 만든다. 이미 배치가 있는 기간과
    # 겹치면 사용자 확인(confirm_overwrite) 없이는 아무것도 저장하지 않는다.
    rows_by_period: dict[tuple[int, int], list[tuple]] = {}
    for f, result in refinement_results:
        by_period: dict[tuple[int, int], list] = {}
        for row in result.rows:
            if not (row.year and row.month):
                continue
            by_period.setdefault((row.year, row.month), []).append(row)
        for period, rows in by_period.items():
            rows_by_period.setdefault(period, []).append((f, rows))

    existing_map = {p: db.find_batch_id_by_period(*p) for p in batch_periods}
    conflicting_periods = sorted(p for p, bid in existing_map.items() if bid)
    new_periods = sorted(p for p, bid in existing_map.items() if not bid)

    if conflicting_periods and confirm_overwrite is None:
        return {
            "requires_confirmation": True,
            "conflicting_periods": [f"{y:04d}-{m:02d}" for y, m in conflicting_periods],
            "new_periods": [f"{y:04d}-{m:02d}" for y, m in new_periods],
            "files": file_summaries,
            "warning": period_warning,
        }

    committed_periods = sorted(
        new_periods + (conflicting_periods if confirm_overwrite else [])
    )
    skipped_periods = conflicting_periods if not confirm_overwrite else []

    batch_id_by_period: dict[tuple[int, int], str] = {}
    batches_summary: list[dict] = []
    for year, month in committed_periods:
        existing_batch_id = existing_map[(year, month)]
        if existing_batch_id:
            db.delete_batch(existing_batch_id)

        period_batch_id = str(uuid.uuid4())
        batch_id_by_period[(year, month)] = period_batch_id
        db.connection.execute(
            "INSERT INTO upload_batch (batch_id, upload_date, target_year, target_month) VALUES (?, ?, ?, ?)",
            [period_batch_id, datetime.now(), year, month],
        )

        total_rows = 0
        unmapped_rows = 0
        calc_error_rows = 0
        for actual_f, rows in rows_by_period.get((year, month), []):
            file_id = str(uuid.uuid4())
            db.connection.execute(
                "INSERT INTO uploaded_file (file_id, batch_id, file_name, file_type, recognition_method) "
                "VALUES (?, ?, ?, ?, ?)",
                [file_id, period_batch_id, actual_f.filename, REQUIRED_FILE_TYPE, "사용자 지정"],
            )
            _store_refined_rows(db, period_batch_id, file_id, rows)
            total_rows += len(rows)
            unmapped_rows += sum(1 for r in rows if not r.is_mapped)
            calc_error_rows += sum(1 for r in rows if r.is_calc_error)

        aggregated_count = compute_aggregates_for_batch(db, period_batch_id)
        anomaly_count = evaluate_anomalies(db, period_batch_id)
        batches_summary.append(
            {
                "batch_id": period_batch_id,
                "target_period": f"{year:04d}-{month:02d}",
                "overwrote_existing_batch": existing_batch_id is not None,
                "total_rows": total_rows,
                "unmapped_rows": unmapped_rows,
                "calc_error_rows": calc_error_rows,
                "aggregated_groups": aggregated_count,
                "anomaly_count": anomaly_count,
            }
        )

    # 실적 외 파일(계획/손익계산서/매핑표)은 기간별로 나뉘지 않으므로, 커밋된 기간 중
    # 가장 이른 기간의 배치("대표 배치")에 그대로 연결한다 — sales_plan_record/
    # team_pl_record는 team+year+month로 조회되고 재업로드 시 연도 단위로 지우고
    # 다시 채우므로 어느 batch_id에 달려 있든 계산 결과에는 영향이 없다(계보 추적용).
    primary_batch_id = batch_id_by_period.get(committed_periods[0]) if committed_periods else None
    if primary_batch_id is not None:
        for f, ftype, _df, _content in loaded:
            if ftype == REQUIRED_FILE_TYPE:
                continue
            file_id = str(uuid.uuid4())
            db.connection.execute(
                "INSERT INTO uploaded_file (file_id, batch_id, file_name, file_type, recognition_method) "
                "VALUES (?, ?, ?, ?, ?)",
                [file_id, primary_batch_id, f.filename, ftype, "사용자 지정"],
            )
            if id(f) in plan_entries_by_file:
                _store_plan_records(db, primary_batch_id, file_id, plan_entries_by_file[id(f)])
            if id(f) in team_pl_entries_by_file:
                _store_team_pl_records(db, primary_batch_id, file_id, team_pl_entries_by_file[id(f)])

    representative = batches_summary[0] if batches_summary else {
        "batch_id": None,
        "target_period": None,
        "overwrote_existing_batch": False,
        "total_rows": 0,
        "unmapped_rows": 0,
        "calc_error_rows": 0,
        "aggregated_groups": 0,
        "anomaly_count": 0,
    }
    return {
        **representative,
        "files": file_summaries,
        "warning": period_warning,
        "requires_confirmation": False,
        "batches": batches_summary,
        "skipped_periods": [f"{y:04d}-{m:02d}" for y, m in skipped_periods],
    }


def _store_product_mapping(db: Database, df) -> None:
    # 실제 매핑표 파일에는 동일한 "인자"(팀+제품코드 합성 키) 값이 중복된 행이 존재할 수
    # 있음을 실제로 확인했다(원인 미상 — 데이터 정정을 위해 뒤에 다시 기재된 것일 수도,
    # 원본 자체의 중복일 수도 있음). mapping_key가 PRIMARY KEY라 평범한 INSERT는 두 번째
    # 중복 행에서 그대로 크래시한다 — INSERT OR REPLACE로 뒤에 나온 행이 앞의 값을
    # 덮어쓰게 해 업로드가 중단되지 않게 한다(엑셀에서 아래로 갈수록 최신/수정 값이라는
    # 일반적인 관례를 따름).
    db.connection.execute("DELETE FROM product_mapping")
    for _, row in df.iterrows():
        db.connection.execute(
            """
            INSERT OR REPLACE INTO product_mapping
                (mapping_key, team, product_code, division, usage,
                 product_group_1, product_group_2, product_group_3, product_group_4, material_desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(row["인자"]).strip(),
                str(row["구분(팀)"]).strip(),
                str(row["제품"]).strip(),
                str(row["구분"]).strip(),
                str(row["용도"]).strip(),
                str(row["제품구분1(보고4용)"]).strip(),
                str(row["제품구분2(보고3용)"]).strip(),
                str(row["제품구분3(계획비교용)"]).strip(),
                str(row["제품구분4"]).strip(),
                str(row["자재내역(Desc)"]).strip(),
            ],
        )


def _load_product_mapping(db: Database) -> ProductMappingTable:
    import pandas as pd

    rows = db.connection.execute(
        "SELECT mapping_key AS \"인자\", team AS \"구분(팀)\", product_code AS \"제품\", "
        "division AS \"구분\", usage AS \"용도\", "
        "product_group_1 AS \"제품구분1(보고4용)\", product_group_2 AS \"제품구분2(보고3용)\", "
        "product_group_3 AS \"제품구분3(계획비교용)\", product_group_4 AS \"제품구분4\", "
        "material_desc AS \"자재내역(Desc)\" "
        "FROM product_mapping"
    ).fetchdf()
    return ProductMappingTable.from_dataframe(rows)


def _store_branch_mapping(db: Database, df) -> None:
    # product_mapping과 동일한 이유(중복 키 존재 가능)로 INSERT OR REPLACE를 쓴다.
    db.connection.execute("DELETE FROM branch_mapping")
    for _, row in df.iterrows():
        key = str(row["인자"]).strip()
        customer_code = str(row["거래처코드"]).strip()
        # 인자(팀+거래처코드)에서 거래처코드 접미사를 떼어내 팀을 구한다(branch.py와 동일 로직).
        team = key[: -len(customer_code)] if customer_code and key.endswith(customer_code) else key
        db.connection.execute(
            """
            INSERT OR REPLACE INTO branch_mapping
                (mapping_key, team, customer_code, customer_name, region, office, part)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                key,
                team,
                customer_code,
                str(row["고객"]).strip(),
                str(row["권역"]).strip(),
                str(row["사업소"]).strip(),
                str(row["파트"]).strip(),
            ],
        )


def _load_branch_mapping(db: Database) -> BranchMappingTable | None:
    import pandas as pd

    rows = db.connection.execute(
        "SELECT mapping_key AS \"인자\", customer_name AS \"고객\", customer_code AS \"거래처코드\", "
        "region AS \"권역\", office AS \"사업소\", part AS \"파트\" "
        "FROM branch_mapping"
    ).fetchdf()
    if rows.empty:
        return None
    return BranchMappingTable.from_dataframe(rows)


def _store_plan_records(db: Database, batch_id: str, file_id: str, entries: list) -> None:
    # 판매계획은 연간 전체를 한 번에 담은 파일이므로, 같은 연도를 재업로드하면 기존
    # 행을 지우고 다시 채운다 — 지우지 않으면 재계산 시 계획금액이 중복 합산된다.
    years = {entry.year for entry in entries}
    for year in years:
        db.connection.execute("DELETE FROM sales_plan_record WHERE year = ?", [year])

    for entry in entries:
        db.connection.execute(
            """
            INSERT INTO sales_plan_record (
                record_id, file_id, batch_id, team,
                customer_code, customer_name, delivery_code, delivery_name, sales_rep,
                category, product_type, hq_report_group,
                year, month, unit_price, quantity, planned_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                file_id,
                batch_id,
                entry.team,
                entry.customer_code,
                entry.customer_name,
                entry.delivery_code,
                entry.delivery_name,
                entry.sales_rep,
                entry.category,
                entry.product_type,
                entry.hq_report_group,
                entry.year,
                entry.month,
                entry.unit_price,
                entry.quantity,
                entry.planned_amount,
            ],
        )


def _store_team_pl_records(db: Database, batch_id: str, file_id: str, entries: list) -> None:
    # 손익계산서(계획)도 판매계획과 마찬가지로 연간 전체(팀×12개월)를 한 번에 담은
    # 파일이다 — 실사용 중 실제로 겪은 버그: 같은 연도를 재업로드해도 기존 행을 지우지
    # 않아서, pl_comparison.py가 (year, month)로만 조회할 때 여러 번 업로드분이 전부
    # 더해져 계획 수치가 몇 배로 부풀려졌다. sales_plan_record와 동일하게 재업로드 시
    # 같은 연도의 기존 행을 지우고 다시 채운다.
    years = {entry.year for entry in entries}
    for year in years:
        db.connection.execute("DELETE FROM team_pl_record WHERE year = ?", [year])

    for entry in entries:
        db.connection.execute(
            """
            INSERT INTO team_pl_record (record_id, file_id, batch_id, team, account_item, year, month, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                file_id,
                batch_id,
                entry.team,
                entry.account_item,
                entry.year,
                entry.month,
                entry.amount,
            ],
        )


def _store_refined_rows(db: Database, batch_id: str, file_id: str, rows: list) -> None:
    columns = ["record_id", "batch_id", "file_id", *REFINED_ROW_COLUMNS]
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO refined_sales_record ({', '.join(columns)}) VALUES ({placeholders})"
    for row in rows:
        values = [str(uuid.uuid4()), batch_id, file_id, *(getattr(row, col) for col in REFINED_ROW_COLUMNS)]
        db.connection.execute(sql, values)
