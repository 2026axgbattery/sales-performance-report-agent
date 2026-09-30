import pandas as pd
import pytest

from app.services.branch import BranchMappingTable, BranchValidationError


@pytest.fixture()
def branch_df():
    return pd.DataFrame(
        [
            {
                "인자": "차량대리점2101226",
                "고객": "(주)예시글로벌",
                "거래처코드": "2101226",
                "권역": "중부권역",
                "사업소": "중부사업소",
                "파트": "대리점",
            },
            {
                "인자": "고정형2307151",
                "고객": "(유)검상전력",
                "거래처코드": "2307151",
                "권역": "중부권역",
                "사업소": "중부사업소",
                "파트": "직거래처",
            },
        ]
    )


def test_lookup_returns_region_office_part_for_known_key(branch_df):
    table = BranchMappingTable.from_dataframe(branch_df)
    region, office, part = table.lookup("차량대리점", "2101226")
    assert (region, office, part) == ("중부권역", "중부사업소", "대리점")


def test_lookup_does_not_apply_san_jeon_prefix_for_motive_or_fixed_team(branch_df):
    # 제품분류(mapping.py)와 달리 지점코드는 "산전" 접두사를 쓰지 않는다 — 실제
    # 시트 값이 "고정형2307151"이지 "산전2307151"이 아니다(.docs/03_데이터정제.md §3.5).
    table = BranchMappingTable.from_dataframe(branch_df)
    region, office, part = table.lookup("고정형", "2307151")
    assert (region, office, part) == ("중부권역", "중부사업소", "직거래처")


def test_lookup_returns_none_triple_for_unknown_key(branch_df):
    table = BranchMappingTable.from_dataframe(branch_df)
    assert table.lookup("차량OE", "9999999") == (None, None, None)


def test_from_dataframe_derives_team_by_stripping_customer_code_suffix(branch_df):
    table = BranchMappingTable.from_dataframe(branch_df)
    entry = table._entries["차량대리점2101226"]
    assert entry.team == "차량대리점"
    assert entry.customer_code == "2101226"


def test_from_dataframe_raises_on_missing_columns():
    df = pd.DataFrame([{"인자": "차량대리점2101226"}])
    with pytest.raises(BranchValidationError):
        BranchMappingTable.from_dataframe(df)
