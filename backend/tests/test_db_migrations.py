"""report_item에 나중에 추가된 컬럼(is_excluded/background_note)이, 그 컬럼이
없던 시절에 만들어진 기존 로컬 DuckDB 파일을 다시 열었을 때도 정상적으로
추가되는지 검증한다 (CREATE TABLE IF NOT EXISTS는 기존 테이블을 바꾸지 않으므로
별도 컬럼 마이그레이션이 필요했다 — 실제로 로컬 데모 중 500 에러로 발견된 문제)."""
from app.db import Database


def test_reopening_db_with_pre_day5_schema_adds_missing_columns(tmp_path):
    db_path = tmp_path / "legacy.duckdb"

    # Day 5 이전 스키마(is_excluded/background_note 없음)로 파일을 먼저 만든다.
    legacy = Database(str(db_path))
    legacy.connection.execute(
        "CREATE TABLE report_item_legacy AS SELECT * FROM report_item"
    )
    legacy.connection.execute("DROP TABLE report_item")
    legacy.connection.execute(
        """
        CREATE TABLE report_item (
            item_id VARCHAR PRIMARY KEY,
            draft_id VARCHAR,
            flag_id VARCHAR,
            auto_comment VARCHAR,
            user_comment VARCHAR,
            chart_ref VARCHAR
        )
        """
    )
    legacy.close()

    # 새 코드로 같은 파일을 다시 열면(= 앱을 재시작하면) 마이그레이션이 적용되어야 한다.
    reopened = Database(str(db_path))
    columns = {row[1] for row in reopened.connection.execute("PRAGMA table_info('report_item')").fetchall()}
    assert "is_excluded" in columns
    assert "background_note" in columns

    # 새 컬럼을 실제로 쓸 수 있어야 한다 (create_report_draft가 의존하는 INSERT 형태).
    reopened.connection.execute(
        """
        INSERT INTO report_item (item_id, draft_id, flag_id, auto_comment, user_comment, chart_ref, is_excluded, background_note)
        VALUES ('i1', 'd1', NULL, 'auto', NULL, '팀', False, NULL)
        """
    )
    row = reopened.connection.execute(
        "SELECT is_excluded, background_note FROM report_item WHERE item_id = 'i1'"
    ).fetchone()
    assert row == (False, None)
    reopened.close()
