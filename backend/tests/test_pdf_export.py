"""F9 Overview PDF export 회귀 테스트.

실제로 겪은 버그(사용자 확인: "PDF 다운하면 밑에 내용이 잘린다") — 팀별 목표 대비
실적 표(6개 팀 행 고정, app.services.analytics.TEAM_MATRIX_GROUPS 참고)의 마지막
행("합계")이 페이지 여백 계산에서 1pt 미만 차이로 다음 페이지로 밀려나, 표가
반복 헤더 3행 + 그 한 행만 남은 채 페이지 중간에서 잘린 것처럼 보였다
(app/services/pdf_export.py의 KeepTogether·여백 조정으로 수정, .docs/phase 참고 없이
바로 발견·수정한 실측 버그). 팀 수가 고정돼 있어(현재 6행) 항상 재현 가능하므로,
페이지 수와 "합계" 행이 실제로 포함돼 있는지를 고정 회귀 테스트로 검증한다.
"""
from io import BytesIO

import pdfplumber
from pypdf import PdfReader
from reportlab.platypus import Paragraph

from app.services.pdf_export import _wrapped_label
from tests.conftest import FIXTURES_DIR


def _upload(client, filenames_and_types, mime="text/csv"):
    files = [
        ("files", (name, open(FIXTURES_DIR / name, "rb"), mime))
        for name, _ in filenames_and_types
    ]
    data = {"file_types": [ftype for _, ftype in filenames_and_types]}
    return client.post("/uploads", files=files, data=data)


def test_overview_pdf_fits_team_matrix_on_a_single_page_without_truncation(client):
    upload = _upload(client, [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    assert upload.status_code == 200, upload.text
    batch_id = upload.json()["batch_id"]

    # team_matrix 섹션만 선택 — Phase 15부터 sections 생략 시 전체 섹션(월별 실적 분석 3종
    # + 손익 상세 분석까지)이 포함돼 여러 페이지가 되므로, 이 회귀 테스트의 원래 취지
    # (팀별 목표 대비 실적 표 자체가 페이지 여백 부족으로 잘리지 않는지)를 유지하려면
    # 섹션을 명시적으로 좁혀야 한다.
    response = client.get(f"/batches/{batch_id}/export/overview", params={"sections": "team_matrix"})
    assert response.status_code == 200, response.text

    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) == 1, "팀별 목표 대비 실적 표가 페이지 여백 부족으로 다음 페이지로 밀려났습니다."

    text = reader.pages[0].extract_text()
    # 두 매트릭스 표(수량·매출액 / 영업이익) 모두 "합계" 행이 페이지 안에 온전히 들어있어야 한다.
    assert text.count("합계") == 2


def test_overview_pdf_team_matrix_ytd_header_is_not_shifted(client):
    # 실제로 겪은 버그(사용자 확인: "PDF 다운받을때 원본 서식이 깨지지 않게") — 2단
    # 헤더를 만들 때 반복 블록마다 선행 빈 칸이 중복으로 들어가 "누계" 쪽 헤더가 14칸이
    # 되면서(13칸이어야 함) 데이터 컬럼과 한 칸씩 밀려 보였다. leaf 헤더 행이 정확히
    # 13칸이고, "누계" 그룹의 수량/매출액 라벨이 올바른 위치에 있는지 검증한다.
    upload = _upload(client, [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    batch_id = upload.json()["batch_id"]

    response = client.get(f"/batches/{batch_id}/export/overview", params={"sections": "team_matrix"})
    assert response.status_code == 200, response.text

    with pdfplumber.open(BytesIO(response.content)) as pdf:
        tables = pdf.pages[0].find_tables()
        # tables[0] = 상단 KPI 카드, tables[1] = 수량·매출액 표.
        rows = tables[1].extract()

    leaf_header = rows[2]
    assert len(leaf_header) == 13, f"leaf 헤더가 13칸이 아닙니다(중복된 빈 칸으로 밀림): {leaf_header}"
    assert leaf_header[7:13] == ["수량", "매출액", "수량", "매출액", "수량", "매출액"]

    first_data_row = rows[3]
    assert len(first_data_row) == 13
    # "누계" 그룹의 실적 수량(9번째 칸, 인덱스 9)은 계획 파일 유무와 무관하게 항상 숫자다
    # (목표 칸은 계획 파일이 없으면 "-"일 수 있어 검증에 쓰지 않는다). 밀렸다면 여기에
    # 억 단위 금액 문자열이나 빈 칸이 온다.
    assert first_data_row[9].replace(",", "").isdigit()
    # "누계" 실적 매출액(10번째 칸)은 항상 "억" 단위로 표시된다 — 밀렸다면 이 자리에
    # 수량(순수 숫자)이나 %가 온다.
    assert "억" in first_data_row[10]


def test_wrapped_label_wraps_long_text_instead_of_overflowing_the_cell():
    # 실제로 겪은 버그(사용자 확인: "칸에 안맞아서 구역을 침범하는거") — 긴 거래처명/
    # 계정과목명을 표 셀에 그냥 문자열로 넣으면 reportlab이 줄바꿈 없이 그대로 그려
    # 옆 칸 위로 겹쳐 보인다. 셀 라벨은 반드시 Paragraph로 감싸 셀 폭 안에서 자동
    # 줄바꿈되게 해야 한다.
    result = _wrapped_label("가나자동차 주식회사(GN Motors Corp)")
    assert isinstance(result, Paragraph)


def test_overview_pdf_defaults_to_all_sections(client):
    upload = _upload(client, [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    batch_id = upload.json()["batch_id"]

    response = client.get(f"/batches/{batch_id}/export/overview")
    assert response.status_code == 200, response.text

    reader = PdfReader(BytesIO(response.content))
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "팀별 목표 대비 실적" in full_text
    assert "월별 실적 분석(팀별)" in full_text
    assert "월별 실적 분석(제품군별)" in full_text
    assert "월별 실적 분석(거래처별)" in full_text
    assert "손익 상세 분석" in full_text
    assert len(reader.pages) > 1


def test_overview_pdf_only_includes_selected_sections(client):
    upload = _upload(client, [("actual_sample.csv", "실적"), ("mapping_sample.csv", "매핑표")])
    batch_id = upload.json()["batch_id"]

    response = client.get(
        f"/batches/{batch_id}/export/overview",
        params={"sections": ["monthly_customer"]},
    )
    assert response.status_code == 200, response.text

    reader = PdfReader(BytesIO(response.content))
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "월별 실적 분석(거래처별)" in full_text
    assert "팀별 목표 대비 실적" not in full_text
    assert "월별 실적 분석(팀별)" not in full_text
    assert "손익 상세 분석" not in full_text
