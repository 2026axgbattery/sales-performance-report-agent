"""F9. 결과 다운로드(엑셀) API."""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.db import Database, get_db
from app.services.export import (
    build_anomalies_workbook,
    build_refined_export_workbook_for_draft,
    build_report_workbook,
)
from app.services.pdf_export import build_overview_pdf

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA_TYPE = "application/pdf"


def _xlsx_response(content: bytes, filename: str) -> Response:
    # HTTP 헤더는 latin-1만 허용하므로, 한글 파일명은 RFC 5987 filename*(UTF-8 percent-encoding)로
    # 전달하고 filename=에는 ASCII로만 된 대체 이름을 둔다.
    encoded = quote(filename)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename=\"export.xlsx\"; filename*=UTF-8''{encoded}",
        },
    )


def _pdf_response(content: bytes, filename: str) -> Response:
    encoded = quote(filename)
    return Response(
        content=content,
        media_type=PDF_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename=\"export.pdf\"; filename*=UTF-8''{encoded}",
        },
    )


@router.get("/batches/{batch_id}/export/overview")
def export_overview(
    batch_id: str,
    sections: Optional[list[str]] = Query(
        default=None,
        description="포함할 카테고리(팀별 목표 대비 실적/월별 실적 분석 팀별·제품군별·거래처별/손익 상세 분석). 생략하면 전체 포함.",
    ),
    db: Database = Depends(get_db),
):
    # 사용자 확인: Overview 다운로드는 엑셀이 아니라 PDF로 받는다(F9). Phase 15부터
    # F4 아래 탭 내용도 카테고리 체크박스로 선택해서 포함할 수 있다(사용자 요청).
    content = build_overview_pdf(db, batch_id, sections=sections)
    if content is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    return _pdf_response(content, f"Overview_{batch_id}.pdf")


@router.get("/batches/{batch_id}/export/anomalies")
def export_anomalies(batch_id: str, db: Database = Depends(get_db)):
    content = build_anomalies_workbook(db, batch_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    return _xlsx_response(content, f"이상징후_{batch_id}.xlsx")


@router.get("/reports/{draft_id}/export")
def export_report(draft_id: str, db: Database = Depends(get_db)):
    content = build_report_workbook(db, draft_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 draft_id 입니다: {draft_id}")
    return _xlsx_response(content, f"보고서초안_{draft_id}.xlsx")


@router.get("/reports/{draft_id}/export/refined")
def export_refined(draft_id: str, db: Database = Depends(get_db)):
    # F7 신규 다운로드 버튼(Phase 15, 사용자 요청) — raw+매핑을 거쳐 정제된 실적
    # Re-arrange용 수식 시트 전체를 xlsx로 내려준다(draft_id가 가리키는 배치 기준).
    content = build_refined_export_workbook_for_draft(db, draft_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 draft_id 입니다: {draft_id}")
    return _xlsx_response(content, f"실적_Re-arrange_{draft_id}.xlsx")
