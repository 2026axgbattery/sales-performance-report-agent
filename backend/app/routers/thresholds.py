"""F6. 임계치 설정 API."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import Database, get_db
from app.services.aggregation import compute_aggregates_for_batch
from app.services.anomaly import evaluate_anomalies
from app.services.thresholds import UnknownMetricError, get_thresholds, update_thresholds

router = APIRouter()


class ThresholdUpdate(BaseModel):
    metric_type: str
    threshold_value: Optional[float] = None
    threshold_low: Optional[float] = None
    threshold_high: Optional[float] = None


class ThresholdUpdateRequest(BaseModel):
    updates: List[ThresholdUpdate]


def _serialize(thresholds: dict) -> list[dict]:
    return [
        {
            "metric_type": t.metric_type,
            "threshold_value": t.threshold_value,
            "threshold_low": t.threshold_low,
            "threshold_high": t.threshold_high,
        }
        for t in thresholds.values()
    ]


@router.get("/thresholds")
def read_thresholds(db: Database = Depends(get_db)):
    return {"thresholds": _serialize(get_thresholds(db))}


@router.put("/thresholds")
def write_thresholds(payload: ThresholdUpdateRequest, db: Database = Depends(get_db)):
    try:
        thresholds = update_thresholds(db, [u.model_dump() for u in payload.updates])
    except UnknownMetricError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"thresholds": _serialize(thresholds)}


@router.post("/batches/{batch_id}/recompute")
def recompute_batch(batch_id: str, db: Database = Depends(get_db)):
    """F6에서 임계치를 바꾼 뒤, 재업로드 없이 이상징후만 다시 계산할 때 사용한다."""
    if db.batch_period(batch_id) is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 batch_id 입니다: {batch_id}")
    aggregated_count = compute_aggregates_for_batch(db, batch_id)
    anomaly_count = evaluate_anomalies(db, batch_id)
    return {"batch_id": batch_id, "aggregated_groups": aggregated_count, "anomaly_count": anomaly_count}
