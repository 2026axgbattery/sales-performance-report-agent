"""제품분류 매핑표 파싱 (docs/03_데이터정제.md §3).

컬럼(10개): 인자, 구분(팀), 제품, 구분, 용도,
           제품구분1(보고4용), 제품구분2(보고3용), 제품구분3(계획비교용), 제품구분4, 자재내역(Desc)

조인 키: 구분(팀) + 제품 을 이어 붙인 "인자" 컬럼과 동일한 합성 키.
F2에서 실제로 조회하는 값은 제품구분3(계획비교용)이다.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd

from app.services.validation import validate_extension

PRODUCT_SHEET_NAME = "제품분류"
# 지점코드 매핑 시트는 파일마다 이름이 다르다 — "지점코드"(08월 실제 파일, .docs/03_
# 데이터정제.md §3.5)와 "업체코드"(`맵핑_분석용.xlsx`, 컬럼 구조는 동일하고 팀명 컬럼이
# 하나 더 있음)를 실측으로 확인했다. 추정으로 하나만 고정하지 않고 둘 다 허용한다.
BRANCH_SHEET_NAMES = ("지점코드", "업체코드")

REQUIRED_MAPPING_COLUMNS = [
    "인자",
    "구분(팀)",
    "제품",
    "구분",
    "용도",
    "제품구분1(보고4용)",
    "제품구분2(보고3용)",
    "제품구분3(계획비교용)",
    "제품구분4",
    "자재내역(Desc)",
]


class MappingValidationError(ValueError):
    def __init__(self, missing_columns: list[str] | None = None, message: str | None = None):
        self.missing_columns = missing_columns
        super().__init__(message or f"매핑표에 다음 컬럼이 없습니다: {missing_columns}")


@dataclass(frozen=True)
class MappingEntry:
    team: str
    product_code: str
    division: str
    usage: str
    product_group_1: str
    product_group_2: str
    product_group_3: str
    product_group_4: str
    material_desc: str


class ProductMappingTable:
    """mapping_key -> MappingEntry 조회 테이블."""

    def __init__(self, entries: dict[str, MappingEntry]):
        self._entries = entries

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "ProductMappingTable":
        missing = [c for c in REQUIRED_MAPPING_COLUMNS if c not in df.columns]
        if missing:
            raise MappingValidationError(missing)

        entries: dict[str, MappingEntry] = {}
        for _, row in df.iterrows():
            key = str(row["인자"]).strip()
            entries[key] = MappingEntry(
                team=str(row["구분(팀)"]).strip(),
                product_code=str(row["제품"]).strip(),
                division=str(row["구분"]).strip(),
                usage=str(row["용도"]).strip(),
                product_group_1=str(row["제품구분1(보고4용)"]).strip(),
                product_group_2=str(row["제품구분2(보고3용)"]).strip(),
                product_group_3=str(row["제품구분3(계획비교용)"]).strip(),
                product_group_4=str(row["제품구분4"]).strip(),
                material_desc=str(row["자재내역(Desc)"]).strip(),
            )
        return cls(entries)

    def lookup(self, team: str, product_code: str) -> tuple[str | None, bool]:
        """(제품구분3 값, 매핑 성공 여부)를 반환한다."""
        from app.services.team import mapping_prefix

        key = f"{mapping_prefix(team)}{product_code}"
        entry = self._entries.get(key)
        if entry is None:
            return None, False
        return entry.product_group_3, True

    def lookup_product_group_1(self, team: str, product_code: str) -> str | None:
        """제품구분1(보고4용) 값을 반환한다 (수량(22.9cell) 환산 대상 판정, F4 드릴다운 필터용)."""
        from app.services.team import mapping_prefix

        key = f"{mapping_prefix(team)}{product_code}"
        entry = self._entries.get(key)
        return entry.product_group_1 if entry else None

    def lookup_product_group_2(self, team: str, product_code: str) -> str | None:
        """제품구분2(보고3용) 값을 반환한다 (F4 드릴다운 필터용)."""
        from app.services.team import mapping_prefix

        key = f"{mapping_prefix(team)}{product_code}"
        entry = self._entries.get(key)
        return entry.product_group_2 if entry else None

    def __len__(self) -> int:
        return len(self._entries)


def parse_mapping_upload(filename: str, content: bytes) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """매핑표 파일에서 (제품분류 DataFrame, 지점코드 DataFrame|None)을 추출한다.

    F1의 매핑표는 향후 제품분류·지점코드 두 매핑을 한 파일로 함께 업로드할
    예정이다(.docs/03_데이터정제.md §3.5). CSV는 시트 개념이 없으므로 제품분류
    단일 표로만 취급한다(지점코드 없음 — 기존 CSV 기반 업로드와 호환).
    xlsx/xls/xlsb는 "제품분류"·(BRANCH_SHEET_NAMES 중 하나) 이름의 시트를 찾아 각각
    읽고, 이름이 일치하는 시트가 없으면(예: 시트명 없이 저장된 기존 방식 파일) 첫 번째
    시트를 제품분류로 취급한다.
    """
    ext = validate_extension(filename)
    try:
        if ext == ".csv":
            return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, na_values=[""]), None

        engine = "pyxlsb" if ext == ".xlsb" else None
        xl = pd.ExcelFile(io.BytesIO(content), engine=engine)

        product_sheet = PRODUCT_SHEET_NAME if PRODUCT_SHEET_NAME in xl.sheet_names else xl.sheet_names[0]
        product_df = xl.parse(product_sheet, dtype=str)

        branch_df = None
        branch_sheet = next((name for name in BRANCH_SHEET_NAMES if name in xl.sheet_names), None)
        if branch_sheet is not None:
            branch_df = xl.parse(branch_sheet, dtype=str)
    except MappingValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 — plan.py/team_pl.py와 동일한 패턴: 어떤 형식
        # 오류든(손상된 파일, 지원하지 않는 내부 구조 등) 사용자에게 원인과 함께 안내한다.
        raise MappingValidationError(message=f"매핑표 파일을 열 수 없습니다: {exc}") from exc

    return product_df, branch_df
