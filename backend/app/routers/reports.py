"""F7 보고서 초안 생성·조회 + F8 검토·수정 API."""
from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException

from app.db import Database, get_db
from app.services.reports import create_report_draft, get_report_draft, update_report_item

router = APIRouter()


class CreateReportRequest(BaseModel):
    batch_id: str


class UpdateReportItemRequest(BaseModel):
    user_comment: str | None = None
    background_note: str | None = None
    is_excluded: bool | None = None


@router.post("/reports")
def create_report(body: CreateReportRequest, db: Database = Depends(get_db)):
    try:
        draft_id = create_report_draft(db, body.batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_report_draft(db, draft_id)


@router.get("/reports/{draft_id}")
def read_report(draft_id: str, db: Database = Depends(get_db)):
    draft = get_report_draft(db, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 draft_id 입니다: {draft_id}")
    return draft


@router.patch("/reports/{draft_id}/items/{item_id}")
def patch_report_item(
    draft_id: str,
    item_id: str,
    body: UpdateReportItemRequest,
    db: Database = Depends(get_db),
):
    updates = body.model_dump(exclude_unset=True)
    ok = update_report_item(db, draft_id, item_id, updates)
    if not ok:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 item_id 입니다: {item_id}")
    return get_report_draft(db, draft_id)
