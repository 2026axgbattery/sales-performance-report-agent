"""F4 Overview / F5 이상징후 하이라이트 조회 API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import Database, get_db
from app.services.analytics import get_anomalies, get_overview, get_trend
from app.services.monthly_analysis import (
    get_customer_monthly_analysis,
    get_monthly_analysis_filter_options,
    get_product_group_monthly_analysis,
    get_team_monthly_analysis,
)
from app.services.pl_comparison import PLComparisonError, get_pl_comparison, get_pl_comparison_filter_options

router = APIRouter()


@router.get("/batches")
def list_batches(db: Database = Depends(get_db)):
    rows = db.connection.execute(
        "SELECT batch_id, target_year, target_month, upload_date FROM upload_batch ORDER BY target_year DESC, target_month DESC"
    ).fetchall()
    return {
        "batches": [
            {"batch_id": r[0], "year": r[1], "month": r[2], "upload_date": str(r[3])}
            for r in rows
        ]
    }


@router.get("/batches/{batch_id}/overview")
def read_overview(batch_id: str, db: Database = Depends(get_db)):
    overview = get_overview(db, batch_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    return overview


@router.get("/batches/{batch_id}/trend")
def read_trend(batch_id: str, team: str = Query(...), db: Database = Depends(get_db)):
    period = db.batch_period(batch_id)
    if period is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    year, month = period
    return get_trend(db, team, year, month)


@router.get("/batches/{batch_id}/anomalies")
def read_anomalies(batch_id: str, db: Database = Depends(get_db)):
    if db.batch_period(batch_id) is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    return {"anomalies": get_anomalies(db, batch_id)}


@router.get("/batches/{batch_id}/pl-comparison")
def read_pl_comparison(
    batch_id: str,
    team: Optional[list[str]] = Query(default=None, description="생략하면 국내(전체 팀 합계). 여러 개 선택 가능"),
    customer: Optional[list[str]] = Query(default=None),
    product_code: Optional[list[str]] = Query(default=None),
    desc: Optional[list[str]] = Query(default=None),
    product_group_1: Optional[list[str]] = Query(default=None),
    product_group_2: Optional[list[str]] = Query(default=None),
    product_group_3: Optional[list[str]] = Query(default=None),
    db: Database = Depends(get_db),
):
    """팀별 손익계산서 계획 대비/전월 대비 실적 (.docs/phase/phase_11_팀별손익계산서비교.md,
    .docs/phase/phase_12_전월대비및드릴다운.md). customer/product_code/desc/product_group_1~3은
    실적(당월·전월) 쪽에만 적용되는 드릴다운 필터다. 각 필터는 같은 쿼리 파라미터를 여러 번
    반복해(예: ?customer=A&customer=B) 다중 선택할 수 있다(사용자 확인)."""
    if db.batch_period(batch_id) is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    try:
        result = get_pl_comparison(
            db,
            batch_id,
            team=team,
            customer=customer,
            product_code=product_code,
            desc=desc,
            product_group_1=product_group_1,
            product_group_2=product_group_2,
            product_group_3=product_group_3,
        )
    except PLComparisonError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "batch_id": batch_id,
        "team": ", ".join(team) if team else "국내",
        "plan_comparison_available": result.plan_comparison_available,
        "lines": [
            {
                "key": line.key,
                "label": line.label,
                "plan_unit": line.plan_unit,
                "plan_total": line.plan_total,
                "plan_ratio": line.plan_ratio,
                "actual_unit": line.actual_unit,
                "actual_total": line.actual_total,
                "actual_ratio": line.actual_ratio,
                "diff_unit": line.diff_unit,
                "diff_total": line.diff_total,
                "change_rate": line.change_rate,
                "prev_month_available": line.prev_month_available,
                "prev_month_unit": line.prev_month_unit,
                "prev_month_total": line.prev_month_total,
                "prev_month_ratio": line.prev_month_ratio,
                "diff_prev_month_unit": line.diff_prev_month_unit,
                "diff_prev_month_total": line.diff_prev_month_total,
                "change_rate_prev_month": line.change_rate_prev_month,
            }
            for line in result.lines
        ],
    }


@router.get("/batches/{batch_id}/pl-comparison/filters")
def read_pl_comparison_filter_options(batch_id: str, db: Database = Depends(get_db)):
    """F4 드릴다운 화면의 필터 드롭다운을 채우기 위한 이 배치의 실제 값 목록."""
    try:
        return get_pl_comparison_filter_options(db, batch_id)
    except PLComparisonError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# Phase 14 — F4 손익 상세 분석 영역의 "월별 실적 분석" 탭 3종(팀별/제품군별/거래처별).
# pl-comparison(계획 대비)과 달리 계획 데이터를 조회하지 않는 순수 실적 집계다.
@router.get("/batches/{batch_id}/monthly-analysis/team")
def read_monthly_analysis_team(batch_id: str, db: Database = Depends(get_db)):
    result = get_team_monthly_analysis(db, batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    return result


@router.get("/batches/{batch_id}/monthly-analysis/product-group")
def read_monthly_analysis_product_group(
    batch_id: str,
    team: Optional[list[str]] = Query(default=None, description="드릴다운 필터 — 여러 개 선택 가능"),
    db: Database = Depends(get_db),
):
    result = get_product_group_monthly_analysis(db, batch_id, team=team)
    if result is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    return result


@router.get("/batches/{batch_id}/monthly-analysis/customer")
def read_monthly_analysis_customer(
    batch_id: str,
    team: Optional[list[str]] = Query(default=None, description="드릴다운 필터 — 여러 개 선택 가능"),
    part: Optional[list[str]] = Query(default=None, description="드릴다운 필터(실적 Re-arrange의 '파트' 컬럼) — 여러 개 선택 가능"),
    db: Database = Depends(get_db),
):
    result = get_customer_monthly_analysis(db, batch_id, team=team, part=part)
    if result is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    return result


@router.get("/batches/{batch_id}/monthly-analysis/filters")
def read_monthly_analysis_filter_options(batch_id: str, db: Database = Depends(get_db)):
    result = get_monthly_analysis_filter_options(db, batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    return result
