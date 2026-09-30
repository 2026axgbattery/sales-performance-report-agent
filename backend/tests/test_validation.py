from tests.conftest import FIXTURES_DIR

from app.services.validation import read_dataframe


def test_read_dataframe_normal_header_row1():
    content = (FIXTURES_DIR / "actual_sample.csv").read_bytes()
    df = read_dataframe("actual_sample.csv", content)
    assert "상품" in df.columns
    assert "고객" in df.columns
    assert len(df) == 5


def test_read_dataframe_detects_header_on_row2():
    # 실사용 중 실제로 겪은 파일 구조 — 1행은 일부 계정과목에만 붙는 그룹/단위 라벨이고
    # 실제 컬럼명("상품"/"고객"/"손익 센터" 등)은 2행에 있다(.docs/03_데이터정제.md §2).
    content = (FIXTURES_DIR / "actual_sample_header_row2.xlsx").read_bytes()
    df = read_dataframe("actual_sample_header_row2.xlsx", content)
    assert "상품" in df.columns
    assert "고객" in df.columns
    assert "손익 센터" in df.columns
    assert len(df) == 5
    assert df.iloc[0]["상품"].strip().startswith("PCC01179")
