from tests.conftest import FIXTURES_DIR


def _upload(client, filenames_and_types, mime="text/csv"):
    files = [
        ("files", (name, open(FIXTURES_DIR / name, "rb"), mime))
        for name, _ in filenames_and_types
    ]
    data = {"file_types": [ftype for _, ftype in filenames_and_types]}
    return client.post("/uploads", files=files, data=data)


def test_upload_mapping_with_duplicate_key_does_not_crash_and_last_row_wins(client, test_db):
    # 실제 매핑표 파일에서 동일한 "인자"(팀+제품코드) 값이 중복된 행을 실제로 겪었다 —
    # mapping_key가 PRIMARY KEY라 평범한 INSERT는 두 번째 행에서 크래시했다.
    response = _upload(
        client,
        [("actual_sample.csv", "실적"), ("mapping_duplicate_key.csv", "매핑표")],
    )
    assert response.status_code == 200, response.text

    row = test_db.connection.execute(
        "SELECT product_group_3 FROM product_mapping WHERE mapping_key = '차량대리점PCC01179'"
    ).fetchone()
    assert row[0] == "GB 소형(수정)"  # 뒤에 나온 행이 앞의 값을 덮어씀


def test_upload_mapping_with_branch_sheet_populates_region_office_part(client, test_db):
    # 매핑표 파일에 "제품분류"·"지점코드" 두 시트가 함께 있으면(.docs/03_데이터정제.md
    # §3.5) 둘 다 파싱해서 실적 정제 결과에 권역/사업소/파트까지 채워야 한다.
    response = _upload(
        client,
        [("actual_sample.csv", "실적"), ("mapping_with_branch.xlsx", "매핑표")],
    )
    assert response.status_code == 200, response.text

    row = test_db.connection.execute(
        "SELECT region, office, part, is_branch_mapped FROM refined_sales_record "
        "WHERE product_code = 'PCC01179'"
    ).fetchone()
    assert row == ("남부권역", "남부사업소", "대리점", True)

    # 지점코드에 없는 거래처는 미매핑으로 표시되고 나머지 처리는 막히지 않는다.
    unmapped_row = test_db.connection.execute(
        "SELECT is_branch_mapped FROM refined_sales_record WHERE product_code = 'PCC04736'"
    ).fetchone()
    assert unmapped_row == (False,)


def test_upload_mapping_with_upche_code_sheet_name_also_populates_branch(client, test_db):
    # 실제 파일(`맵핑_분석용.xlsx`)은 같은 컬럼 구조를 "지점코드"가 아니라 "업체코드"라는
    # 시트명으로 담고 있다 — 시트명이 다르면 조용히 미매핑으로 빠지지 않고 이 이름도
    # 인식해야 한다(app/services/mapping.py의 BRANCH_SHEET_NAMES).
    response = _upload(
        client,
        [("actual_sample.csv", "실적"), ("mapping_with_upche_code.xlsx", "매핑표")],
    )
    assert response.status_code == 200, response.text

    row = test_db.connection.execute(
        "SELECT region, office, part, is_branch_mapped FROM refined_sales_record "
        "WHERE product_code = 'PCC01179'"
    ).fetchone()
    assert row == ("남부권역", "남부사업소", "대리점", True)


def test_upload_mapping_csv_only_leaves_branch_fields_unmapped(client, test_db):
    # 기존처럼 매핑표가 제품분류만 있는 CSV여도(지점코드 없음) 그대로 동작해야 한다
    # (하위 호환 — 지점코드는 아직 F1에서 항상 오는 게 아니다).
    response = _upload(
        client,
        [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")],
    )
    assert response.status_code == 200, response.text

    row = test_db.connection.execute(
        "SELECT is_branch_mapped, region FROM refined_sales_record WHERE product_code = 'PCC01179'"
    ).fetchone()
    assert row == (False, None)


def test_upload_actual_with_header_on_row2_succeeds(client):
    # 실사용 중 실제로 겪은 파일 구조 — 헤더가 1행이 아니라 2행에 있다(1행은 일부
    # 계정과목에만 붙는 그룹/단위 라벨). 이걸 인식 못 하면 "다음 컬럼이 없습니다:
    # ['상품','고객','기간/연도','손익 센터 또는 부문']"처럼 전부 못 찾는 오류가 난다.
    response = _upload(
        client,
        [("actual_sample_header_row2.xlsx", "실적"), ("mapping_sample.csv", "매핑표")],
    )
    assert response.status_code == 200, response.text
    assert response.json()["total_rows"] == 5


def test_upload_actual_with_mapping_succeeds(client):
    response = _upload(
        client,
        [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")],
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["target_period"] == "2026-07"
    assert body["total_rows"] == 5
    assert body["unmapped_rows"] == 2
    assert body["calc_error_rows"] == 0
    assert body["overwrote_existing_batch"] is False


def test_upload_with_blank_period_row_does_not_crash_and_flags_calc_error(client, test_db):
    # 실사용 중 실제로 겪은 크래시 — "기간/연도"가 비어있는 행이 있으면 500 에러로
    # 업로드 전체가 죽었다. 나머지 정상 행은 그대로 처리되고, 문제 행만 계산오류로
    # 표시되며 target_period는 정상 행들의 기간으로 결정되어야 한다.
    import pandas as pd

    mixed_path = FIXTURES_DIR / "actual_sample_with_blank_period_row.csv"
    good = pd.read_csv(FIXTURES_DIR / "actual_sample.csv", dtype=str, keep_default_na=False)
    bad = pd.read_csv(FIXTURES_DIR / "actual_all_blank_period.csv", dtype=str, keep_default_na=False)
    pd.concat([good, bad], ignore_index=True).to_csv(mixed_path, index=False, encoding="utf-8-sig")
    try:
        response = _upload(
            client,
            [("actual_sample_with_blank_period_row.csv", "실적"), ("mapping_sample.csv", "매핑표")],
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["target_period"] == "2026-07"
        assert body["calc_error_rows"] >= 1
    finally:
        mixed_path.unlink(missing_ok=True)


def test_upload_with_only_blank_period_rows_returns_400(client):
    response = _upload(
        client,
        [("actual_all_blank_period.csv", "실적"), ("mapping_sample.csv", "매핑표")],
    )
    assert response.status_code == 400
    assert "기간" in response.json()["detail"]


def test_upload_persists_refined_rows_in_duckdb(client, test_db):
    response = _upload(
        client,
        [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")],
    )
    assert response.status_code == 200, response.text

    count = test_db.connection.execute("SELECT COUNT(*) FROM refined_sales_record").fetchone()[0]
    assert count == 5

    row = test_db.connection.execute(
        "SELECT team, product_group, operating_profit_final, quantity "
        "FROM refined_sales_record WHERE product_code = 'PCC01179'"
    ).fetchone()
    assert row == ("차량대리점", "GB 소형", 10227.0, 5.0)


def test_upload_without_actual_file_type_is_rejected(client):
    response = _upload(client, [("mapping_sample.csv", "매핑표")])
    assert response.status_code == 400
    assert "실적" in response.json()["detail"]


def test_upload_without_mapping_on_first_run_is_rejected(client):
    response = _upload(client, [("actual_sample.csv", "실적")])
    assert response.status_code == 400
    assert "매핑표" in response.json()["detail"]


def test_upload_reuses_previous_mapping_when_not_reuploaded(client):
    first = _upload(client, [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    assert first.status_code == 200, first.text

    second = _upload(client, [("actual_sample.csv", "실적")])
    assert second.status_code == 200, second.text
    assert second.json()["unmapped_rows"] == 2


def test_upload_missing_required_columns_reports_which_file_and_columns(client):
    response = _upload(
        client,
        [("actual_missing_column.csv", "실적"), ("mapping_sample.csv", "매핑표")],
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "actual_missing_column.csv" in detail
    assert "매출원가A(조정전)" in detail


def test_reuploading_plan_file_same_year_does_not_double_count(client, test_db):
    r1 = _upload(
        client,
        [
            ("actual_sample.csv", "실적"),
            ("mapping_sample.csv", "매핑표"),
            ("plan_sample.xlsx", "계획"),
        ],
    )
    assert r1.status_code == 200, r1.text

    r2 = _upload(client, [("actual_sample.csv", "실적"), ("plan_sample.xlsx", "계획")])
    assert r2.status_code == 200, r2.text

    total = test_db.connection.execute(
        "SELECT SUM(planned_amount) FROM sales_plan_record WHERE team = '차량대리점' AND year = 2026 AND month = 7"
    ).fetchone()[0]
    assert total == 900000  # 재업로드해도 중복 합산되지 않아야 한다


def test_upload_parses_team_pl_file_and_stores_computed_subtotals(client, test_db):
    response = _upload(
        client,
        [
            ("actual_sample.csv", "실적"),
            ("mapping_sample.csv", "매핑표"),
            ("team_pl_sample.xlsx", "손익계산서"),
        ],
    )
    assert response.status_code == 200, response.text

    row = test_db.connection.execute(
        "SELECT amount FROM team_pl_record "
        "WHERE team = '모티브' AND account_item = '영업이익(A)' AND year = 2026 AND month = 1"
    ).fetchone()
    assert row is not None
    assert row[0] == 750  # 매출총이익(800) - 판관비(50), 원본 수식을 직접 계산한 값


def test_upload_parses_long_format_team_pl_file_using_batch_year(client, test_db):
    # 실제 업로드 형식(손익계산서_더미용.xlsx) — 시트 1개, 팀×월 행, 파일 자체엔
    # 연도가 없어 실적 파일(actual_sample.csv, 2026년 7월)의 target_year를 그대로 쓴다.
    response = _upload(
        client,
        [
            ("actual_sample.csv", "실적"),
            ("mapping_sample.csv", "매핑표"),
            ("team_pl_long_format_sample.xlsx", "손익계산서"),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json()["target_period"] == "2026-07"

    row = test_db.connection.execute(
        "SELECT amount FROM team_pl_record "
        "WHERE team = '모티브' AND account_item = '매출액(Total)' AND year = 2026 AND month = 1"
    ).fetchone()
    assert row == (1000,)


def test_upload_team_pl_twice_does_not_duplicate_same_year(client, test_db):
    # 실사용 중 실제로 겪은 버그 — 손익계산서(계획)는 연간 전체(팀×12개월)를 한 번에
    # 담은 파일인데, 재업로드해도 기존 행을 지우지 않아서 같은 연도를 두 번 올리면
    # pl_comparison의 계획 합계가 두 배로 부풀려졌다(sales_plan_record는 이미 이 문제를
    # 해결해뒀었는데 team_pl_record에는 같은 수정이 빠져 있었다).
    for _ in range(2):
        response = _upload(
            client,
            [
                ("actual_sample.csv", "실적"),
                ("mapping_sample.csv", "매핑표"),
                ("team_pl_long_format_sample.xlsx", "손익계산서"),
            ],
        )
        assert response.status_code == 200, response.text

    count = test_db.connection.execute(
        "SELECT COUNT(*) FROM team_pl_record "
        "WHERE team = '모티브' AND account_item = '매출액(Total)' AND year = 2026 AND month = 1"
    ).fetchone()[0]
    assert count == 1

    amount = test_db.connection.execute(
        "SELECT amount FROM team_pl_record "
        "WHERE team = '모티브' AND account_item = '매출액(Total)' AND year = 2026 AND month = 1"
    ).fetchone()[0]
    assert amount == 1000


def test_upload_accepts_xlsb_actual_file(client):
    # SAP에서 실제로 내려받는 원본 파일 형식(.docs/03_데이터정제.md 근거).
    # actual_sample.xlsb는 actual_sample.csv와 동일한 5행을 담고 있다(Excel로 변환해 생성).
    mime = "application/vnd.ms-excel.sheet.binary.macroEnabled.12"
    files = [
        ("files", ("actual_sample.xlsb", open(FIXTURES_DIR / "actual_sample.xlsb", "rb"), mime)),
        ("files", ("mapping_sample.csv", open(FIXTURES_DIR / "mapping_sample.csv", "rb"), "text/csv")),
    ]
    data = {"file_types": ["실적", "매핑표"]}
    response = client.post("/uploads", files=files, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_rows"] == 5
    assert body["unmapped_rows"] == 2


def test_upload_unsupported_extension_is_rejected(client, tmp_path):
    bad_file = tmp_path / "note.txt"
    bad_file.write_text("hello")
    files = [
        ("files", ("note.txt", open(bad_file, "rb"), "text/plain")),
        ("files", ("mapping_sample.csv", open(FIXTURES_DIR / "mapping_sample.csv", "rb"), "text/csv")),
    ]
    data = {"file_types": ["실적", "매핑표"]}
    response = client.post("/uploads", files=files, data=data)
    assert response.status_code == 400
    assert "지원하지 않는 파일 형식" in response.json()["detail"]


def test_upload_corrupted_actual_file_reports_clear_reason_instead_of_crashing(client, tmp_path):
    # 확장자는 맞지만(.xlsx) 내용이 실제 엑셀 파일이 아닌 경우(.docs/phase/phase_13_
    # 업로드오류처리.md) — read_dataframe이 pandas 예외를 사용자 메시지로 변환해야 한다.
    corrupted = tmp_path / "broken.xlsx"
    corrupted.write_bytes(b"this is not a real xlsx file")
    files = [
        ("files", ("broken.xlsx", open(corrupted, "rb"), "application/octet-stream")),
        ("files", ("mapping_sample.csv", open(FIXTURES_DIR / "mapping_sample.csv", "rb"), "text/csv")),
    ]
    data = {"file_types": ["실적", "매핑표"]}
    response = client.post("/uploads", files=files, data=data)
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "broken.xlsx" in detail
    assert "읽을 수 없습니다" in detail


def test_upload_corrupted_mapping_file_reports_clear_reason_instead_of_crashing(client, tmp_path):
    corrupted = tmp_path / "broken_mapping.xlsx"
    corrupted.write_bytes(b"not a real workbook either")
    files = [
        ("files", ("actual_sample.csv", open(FIXTURES_DIR / "actual_sample.csv", "rb"), "text/csv")),
        ("files", ("broken_mapping.xlsx", open(corrupted, "rb"), "application/octet-stream")),
    ]
    data = {"file_types": ["실적", "매핑표"]}
    response = client.post("/uploads", files=files, data=data)
    assert response.status_code == 400, response.text
    assert "열 수 없습니다" in response.json()["detail"]


def test_reuploading_same_period_overwrites_previous_batch(client, test_db):
    first = _upload(client, [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    assert first.status_code == 200, first.text

    second = _upload(client, [("actual_sample.csv", "실적")])
    assert second.status_code == 200, second.text
    assert second.json()["overwrote_existing_batch"] is True

    batch_count = test_db.connection.execute("SELECT COUNT(*) FROM upload_batch").fetchone()[0]
    record_count = test_db.connection.execute("SELECT COUNT(*) FROM refined_sales_record").fetchone()[0]
    assert batch_count == 1
    assert record_count == 5


# ── Phase 19: 실적 파일 하나에 여러 기간이 섞인 경우 자동 분할 + 겹치는 달 확인 ──
# (.docs/phase/phase_19_실적파일다중월분할업로드.md, 사용자 확인)


def _make_multi_period_fixture(tmp_path, *, extra_period_raw: str) -> str:
    import pandas as pd

    good = pd.read_csv(FIXTURES_DIR / "actual_sample.csv", dtype=str, keep_default_na=False)  # 2026-07
    shifted = good.copy()
    shifted["기간/연도"] = shifted["기간/연도"].str.replace(
        "2026/007 7월 2026", extra_period_raw, regex=False
    )
    combined = pd.concat([good, shifted], ignore_index=True)
    path = tmp_path / "actual_multi_period.csv"
    combined.to_csv(path, index=False, encoding="utf-8-sig")
    return str(path)


def test_multi_period_upload_with_only_new_periods_commits_without_confirmation(client, tmp_path):
    # 2026-07(신규)과 2026-02(신규)만 섞여 있으면 겹치는 달이 없으므로 확인 없이 바로 커밋된다.
    path = _make_multi_period_fixture(tmp_path, extra_period_raw="2026/002 2월 2026")
    files = [
        ("files", ("actual_multi_period.csv", open(path, "rb"), "text/csv")),
        ("files", ("mapping_sample.csv", open(FIXTURES_DIR / "mapping_sample.csv", "rb"), "text/csv")),
    ]
    data = {"file_types": ["실적", "매핑표"]}
    response = client.post("/uploads", files=files, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requires_confirmation"] is False
    periods = {b["target_period"] for b in body["batches"]}
    assert periods == {"2026-02", "2026-07"}
    assert body["skipped_periods"] == []
    for b in body["batches"]:
        assert b["total_rows"] == 5  # 각 기간 배치가 자기 기간의 행만 갖는다(합산 버그 회귀 검증)


def test_multi_period_upload_conflicting_period_requires_confirmation_first(client, tmp_path):
    first = _upload(client, [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    assert first.status_code == 200, first.text  # 2026-07 배치 존재

    path = _make_multi_period_fixture(tmp_path, extra_period_raw="2026/003 3월 2026")
    files = [("files", ("actual_multi_period.csv", open(path, "rb"), "text/csv"))]
    data = {"file_types": ["실적"]}
    response = client.post("/uploads", files=files, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requires_confirmation"] is True
    assert body["conflicting_periods"] == ["2026-07"]
    assert body["new_periods"] == ["2026-03"]


def test_multi_period_upload_confirm_true_overwrites_conflict_and_adds_new(client, test_db, tmp_path):
    first = _upload(client, [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    assert first.status_code == 200, first.text
    old_july_batch_id = first.json()["batch_id"]

    path = _make_multi_period_fixture(tmp_path, extra_period_raw="2026/003 3월 2026")
    files = [("files", ("actual_multi_period.csv", open(path, "rb"), "text/csv"))]
    data = {"file_types": ["실적"], "confirm_overwrite": "true"}
    response = client.post("/uploads", files=files, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requires_confirmation"] is False
    periods = {b["target_period"] for b in body["batches"]}
    assert periods == {"2026-03", "2026-07"}

    # 옛 7월 배치는 지워지고 새 배치로 교체됐어야 한다.
    remaining_old = test_db.connection.execute(
        "SELECT COUNT(*) FROM upload_batch WHERE batch_id = ?", [old_july_batch_id]
    ).fetchone()[0]
    assert remaining_old == 0


def test_multi_period_upload_confirm_false_skips_conflict_but_adds_new(client, test_db, tmp_path):
    first = _upload(client, [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    assert first.status_code == 200, first.text
    old_july_batch_id = first.json()["batch_id"]

    path = _make_multi_period_fixture(tmp_path, extra_period_raw="2026/004 4월 2026")
    files = [("files", ("actual_multi_period.csv", open(path, "rb"), "text/csv"))]
    data = {"file_types": ["실적"], "confirm_overwrite": "false"}
    response = client.post("/uploads", files=files, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skipped_periods"] == ["2026-07"]
    periods = {b["target_period"] for b in body["batches"]}
    assert periods == {"2026-04"}

    # 기존 7월 배치는 그대로 살아있어야 한다.
    remaining_old = test_db.connection.execute(
        "SELECT COUNT(*) FROM upload_batch WHERE batch_id = ?", [old_july_batch_id]
    ).fetchone()[0]
    assert remaining_old == 1
