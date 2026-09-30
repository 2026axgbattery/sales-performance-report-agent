"""F7. 보고서 초안(ReportDraft/ReportItem) 생성·조회.

F5에서 이미 계산된 anomaly_flag 전체를 근거로 ReportItem을 1건씩 만든다 —
여기서 새로 이상징후를 판정하지 않는다(app.services.anomaly가 이미 수행).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.services.comment_generator import generate_comment
from app.services.pl_item_analysis import find_team_item_deviation, format_pl_item_comment
from app.services.report_analysis_mapper import build_analysis_records
from app.services.thresholds import METRIC_PL_ITEM_PLAN

STATUS_DRAFT = "초안"


def create_report_draft(db, batch_id: str) -> str:
    if db.batch_period(batch_id) is None:
        raise ValueError(f"존재하지 않는 batch_id 입니다: {batch_id}")

    draft_id = str(uuid.uuid4())
    db.connection.execute(
        "INSERT INTO report_draft (draft_id, batch_id, created_at, status) VALUES (?, ?, ?, ?)",
        [draft_id, batch_id, datetime.now(timezone.utc), STATUS_DRAFT],
    )

    # F3(app.services.anomaly)가 계산한 이상징후 결과를 comment_generator.AnalysisRecord로
    # 매핑해(app.services.report_analysis_mapper, Phase 16) 서사형 코멘트를 만든다 —
    # 이전에 쓰던 app.services.comments(단문 사실 서술)는 그대로 남겨두되(다른 곳에서
    # 쓸 수 있어 삭제하지 않음) 여기서는 더 이상 참조하지 않는다.
    flags_meta = db.connection.execute(
        "SELECT flag_id, team FROM anomaly_flag WHERE batch_id = ?",
        [batch_id],
    ).fetchall()
    team_by_flag = {flag_id: team for flag_id, team in flags_meta}

    for flag_id, record in build_analysis_records(db, batch_id):
        try:
            comment = generate_comment(record)
        except Exception as exc:  # noqa: BLE001 - 이 항목만 건너뛰고 나머지는 계속 처리
            # Phase 21(.docs/phase/phase_21_코멘트조사자동화및방어처리.md) — 항목 1건에서
            # 예기치 못한 예외가 나도(예: 향후 필드 타입이 바뀌는 등) F7 초안 생성
            # 전체가 죽지 않도록 한다. uploads.py/refinement.py가 이미 쓰는 "행 1개
            # 실패가 전체를 안 죽인다" 원칙과 동일하다 — 플레이스홀더로 대체하고 계속.
            comment = (
                f"[코멘트 생성 실패] {team_by_flag.get(flag_id, '')} 항목은 자동 서술을 "
                f"만들지 못했습니다({type(exc).__name__}). 원본 수치를 직접 확인해 주세요."
            )
        db.connection.execute(
            """
            INSERT INTO report_item (item_id, draft_id, flag_id, auto_comment, user_comment, chart_ref, is_excluded, background_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                draft_id,
                flag_id,
                comment,
                None,
                team_by_flag.get(flag_id),
                False,
                None,
            ],
        )

    # 손익항목계획대비(Phase 18, .docs/phase/phase_18_손익항목계획대비판정.md) 플래그는
    # report_analysis_mapper의 _METRIC_NAME_AND_CATEGORY에 없어 build_analysis_records가
    # 건너뛴다 — comment_generator의 "전월 대비" 서사 틀과 맞지 않는, "단위당/총액 계획
    # 대비" 전용 문장이 필요하기 때문이다. 여기서 anomaly_flag가 남긴 (팀, 항목 라벨)로
    # pl_item_analysis를 다시 조회해(다른 F7 코멘트가 aggregated_result를 재조회하는
    # 것과 같은 패턴) 문장을 직접 조립한다.
    pl_item_flags = db.connection.execute(
        "SELECT flag_id, team, product_group FROM anomaly_flag WHERE batch_id = ? AND metric_type = ?",
        [batch_id, METRIC_PL_ITEM_PLAN],
    ).fetchall()
    for flag_id, team, item_label in pl_item_flags:
        dev = find_team_item_deviation(db, batch_id, team, item_label)
        if dev is None:
            continue
        try:
            comment = format_pl_item_comment(dev)
        except Exception as exc:  # noqa: BLE001 - 이 항목만 건너뛰고 나머지는 계속 처리
            comment = (
                f"[코멘트 생성 실패] {team} {item_label} 항목은 자동 서술을 만들지 "
                f"못했습니다({type(exc).__name__}). 원본 수치를 직접 확인해 주세요."
            )
        db.connection.execute(
            """
            INSERT INTO report_item (item_id, draft_id, flag_id, auto_comment, user_comment, chart_ref, is_excluded, background_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                draft_id,
                flag_id,
                comment,
                None,
                team,
                False,
                None,
            ],
        )

    return draft_id


def get_report_draft(db, draft_id: str) -> dict | None:
    draft_row = db.connection.execute(
        "SELECT draft_id, batch_id, created_at, status FROM report_draft WHERE draft_id = ?",
        [draft_id],
    ).fetchone()
    if draft_row is None:
        return None
    draft_id_, batch_id, created_at, status = draft_row

    item_rows = db.connection.execute(
        """
        SELECT ri.item_id, ri.flag_id, ri.auto_comment, ri.user_comment, ri.chart_ref,
               ri.is_excluded, ri.background_note,
               af.team, af.product_group, af.metric_type, af.actual_value, af.impact_amount
        FROM report_item ri
        LEFT JOIN anomaly_flag af ON af.flag_id = ri.flag_id
        WHERE ri.draft_id = ?
        """,
        [draft_id],
    ).fetchall()

    items = [
        {
            "item_id": r[0],
            "flag_id": r[1],
            "auto_comment": r[2],
            "user_comment": r[3],
            "chart_ref": r[4],
            "is_excluded": bool(r[5]),
            "background_note": r[6],
            "team": r[7],
            "product_group": r[8],
            "metric_type": r[9],
            "actual_value": r[10],
            "impact_amount": r[11],
        }
        for r in item_rows
    ]
    items.sort(key=lambda i: abs(i["impact_amount"] or 0), reverse=True)

    return {
        "draft_id": draft_id_,
        "batch_id": batch_id,
        "created_at": created_at.isoformat() if created_at else None,
        "status": status,
        "items": items,
    }


UPDATABLE_ITEM_FIELDS = ("user_comment", "background_note", "is_excluded")


def update_report_item(db, draft_id: str, item_id: str, updates: dict) -> bool:
    """F8. user_comment(코멘트 수정)/background_note(배경 설명)/is_excluded(제외 토글)
    중 전달된 필드만 갱신한다. 대상 item이 없으면 False를 반환한다."""
    fields = [f for f in UPDATABLE_ITEM_FIELDS if f in updates]
    if not fields:
        return True

    existing = db.connection.execute(
        "SELECT item_id FROM report_item WHERE item_id = ? AND draft_id = ?",
        [item_id, draft_id],
    ).fetchone()
    if existing is None:
        return False

    set_clause = ", ".join(f"{f} = ?" for f in fields)
    values = [updates[f] for f in fields]
    db.connection.execute(
        f"UPDATE report_item SET {set_clause} WHERE item_id = ? AND draft_id = ?",
        [*values, item_id, draft_id],
    )
    return True
