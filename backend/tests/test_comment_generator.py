"""comment_generator.py의 은/는 조사 자동 선택 회귀 테스트.

Phase 21(.docs/phase/phase_21_코멘트조사자동화및방어처리.md) — 이 프로젝트가 실제로
쓰지 않는 별도 초안(comment_generator.py, 루트)을 검토해 _eun_neun/_has_batchim만
부분 이식했다. 그 전까지는 문장마다 "은(는)"을 그대로 노출해 문법적으로 어색했다.
"""
from app.services.comment_generator import (
    AccountCategory,
    AnalysisRecord,
    _eun_neun,
    _has_batchim,
    generate_comment,
)


def test_has_batchim_detects_final_consonant():
    assert _has_batchim("차량대리점") is True  # "점" 받침 ㅁ
    assert _has_batchim("고정형") is True  # "형" 받침 ㅇ
    assert _has_batchim("모티브") is False  # "브" 받침 없음
    assert _has_batchim("차량OE") is False  # 한글이 아닌 마지막 글자


def test_eun_neun_picks_particle_by_batchim():
    assert _eun_neun("차량대리점") == "은"
    assert _eun_neun("모티브") == "는"


def test_generate_comment_uses_correct_particle_for_team_name(seed=1):
    record_with_batchim = AnalysisRecord(
        team_name="차량대리점",
        metric_name="매출액",
        period_label="2026년 8월",
        value=100_000.0,
        mom_change_pct=12.0,
        account_category=AccountCategory.REVENUE,
    )
    comment = generate_comment(record_with_batchim, seed=seed)
    assert "차량대리점은" in comment
    assert "차량대리점은(는)" not in comment

    record_without_batchim = AnalysisRecord(
        team_name="모티브",
        metric_name="매출액",
        period_label="2026년 8월",
        value=100_000.0,
        mom_change_pct=12.0,
        account_category=AccountCategory.REVENUE,
    )
    comment2 = generate_comment(record_without_batchim, seed=seed)
    assert "모티브는" in comment2
    assert "모티브은(는)" not in comment2


def test_generate_comment_uses_correct_particle_when_mom_unavailable():
    record = AnalysisRecord(
        team_name="차량대리점",
        metric_name="매출액(계획대비)",
        period_label="2026년 8월",
        value=100_000.0,
        mom_change_pct=None,
        account_category=AccountCategory.REVENUE,
    )
    comment = generate_comment(record)
    assert "차량대리점은" in comment
    assert "은(는)" not in comment
