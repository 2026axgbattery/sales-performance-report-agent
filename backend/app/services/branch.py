"""지점코드 매핑표 파싱 (docs/03_데이터정제.md §3.5).

컬럼(6개): 인자, 고객, 거래처코드, 권역, 사업소, 파트

조인 키: "팀" + "거래처코드"를 이어 붙인 "인자" 컬럼과 동일한 합성 키
(제품분류의 "팀+제품코드" 패턴과 동일). F2에서는 team+customer_code로
조회해 권역/사업소/파트를 얻는다.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

REQUIRED_BRANCH_COLUMNS = [
    "인자",
    "고객",
    "거래처코드",
    "권역",
    "사업소",
    "파트",
]


class BranchValidationError(ValueError):
    def __init__(self, missing_columns: list[str]):
        self.missing_columns = missing_columns
        super().__init__(f"지점코드 매핑표에 다음 컬럼이 없습니다: {missing_columns}")


@dataclass(frozen=True)
class BranchEntry:
    team: str
    customer_code: str
    customer_name: str
    region: str
    office: str
    part: str


class BranchMappingTable:
    """mapping_key -> BranchEntry 조회 테이블. 제품분류(ProductMappingTable)와 동일한 패턴이다."""

    def __init__(self, entries: dict[str, BranchEntry]):
        self._entries = entries

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "BranchMappingTable":
        missing = [c for c in REQUIRED_BRANCH_COLUMNS if c not in df.columns]
        if missing:
            raise BranchValidationError(missing)

        entries: dict[str, BranchEntry] = {}
        for _, row in df.iterrows():
            key = str(row["인자"]).strip()
            customer_code = str(row["거래처코드"]).strip()
            # 지점코드 시트에는 팀 컬럼이 따로 없다 — 인자(팀+거래처코드)에서 거래처코드
            # 접미사를 떼어내야 팀을 알 수 있다.
            team = key[: -len(customer_code)] if customer_code and key.endswith(customer_code) else key
            entries[key] = BranchEntry(
                team=team,
                customer_code=customer_code,
                customer_name=str(row["고객"]).strip(),
                region=str(row["권역"]).strip(),
                office=str(row["사업소"]).strip(),
                part=str(row["파트"]).strip(),
            )
        return cls(entries)

    def lookup(self, team: str, customer_code: str) -> tuple[str | None, str | None, str | None]:
        """(권역, 사업소, 파트)를 반환한다. 매핑에 없으면 전부 None.

        제품분류(mapping.py)와 달리 모티브·고정형 팀에 "산전" 접두사를 쓰지 않는다 —
        실제 지점코드 시트의 인자 값이 "고정형2307151"처럼 팀명을 그대로 쓰는 것을
        확인했다(.docs/03_데이터정제.md §3.5). team_prefix 치환을 적용하면 안 된다.
        """
        key = f"{team}{customer_code}"
        entry = self._entries.get(key)
        if entry is None:
            return None, None, None
        return entry.region, entry.office, entry.part

    def __len__(self) -> int:
        return len(self._entries)
