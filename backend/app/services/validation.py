"""F1. 파일 업로드 — 형식/파일종류 검증 유틸리티."""
from __future__ import annotations

import io

import pandas as pd

ALLOWED_EXTENSIONS = (".xlsx", ".xls", ".xlsb", ".csv")
FILE_TYPES = ("실적", "계획", "손익계산서", "매핑표")
REQUIRED_FILE_TYPE = "실적"


class UnsupportedFileTypeError(ValueError):
    pass


class UnknownFileCategoryError(ValueError):
    pass


class FileParseError(ValueError):
    """확장자는 맞지만 내용을 읽을 수 없는 경우(손상된 파일, 지원하지 않는 내부 구조 등).

    .docs/phase/phase_13_업로드오류처리.md 참고 — plan.py/team_pl.py의 "workbook 열기를
    try/except로 감싸 사용자 메시지로 변환" 패턴을 실적 파일에도 동일하게 적용한다.
    """


def validate_extension(filename: str) -> str:
    lower = filename.lower()
    for ext in ALLOWED_EXTENSIONS:
        if lower.endswith(ext):
            return ext
    raise UnsupportedFileTypeError(
        f"'{filename}' — 지원하지 않는 파일 형식입니다. 허용 형식: {ALLOWED_EXTENSIONS}"
    )


def validate_file_category(file_type: str) -> None:
    if file_type not in FILE_TYPES:
        raise UnknownFileCategoryError(
            f"'{file_type}' — 알 수 없는 파일 종류입니다. 허용 값: {FILE_TYPES}"
        )


# 실적 Raw Data 파일 중 일부는 헤더가 한 행이 아니라 "엇갈린 2행"에 걸쳐 있다 —
# 실사용 파일로 확인(.docs/03_데이터정제.md §2): 1행에는 계정과목명(예: "매출액(Total)")이
# 식별자 컬럼(상품/고객/손익 센터 등) 자리만 비운 채 들어있고, 2행에는 그 식별자명이
# 채워져 있는 대신 계정과목 컬럼 자리엔 "1 KRW"/"1 AH" 같은 단위 라벨이 들어있다.
# 즉 어느 한 행만 헤더로 쓰면 절반은 무조건 못 찾는다 — 컬럼별로 1행 값이 있으면
# 그걸, 없으면(빈 칸) 2행 값을 쓰는 방식으로 두 행을 합쳐야 한다.
_HEADER_PROBE_COLUMNS = ("상품", "고객")


def _looks_like_header(columns) -> bool:
    return any(col in _HEADER_PROBE_COLUMNS for col in columns)


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    # dtype=str로 읽어도 빈 셀은 문자열 "nan"이 아니라 float NaN으로 온다
    # (keep_default_na=False를 안 줬을 때) — pd.isna로 같이 걸러야 한다.
    return bool(pd.isna(value))


def read_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    ext = validate_extension(filename)
    try:
        if ext == ".csv":
            return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, na_values=[""])

        engine = "pyxlsb" if ext == ".xlsb" else None
        # SAP에서 내려받는 실제 원본 파일(.docs/03_데이터정제.md 근거)은 .xlsb 형식이다.
        # openpyxl/xlrd는 xlsb를 읽지 못하므로 pyxlsb 엔진을 명시해야 한다.
        df = pd.read_excel(io.BytesIO(content), dtype=str, engine=engine, header=0)
        if _looks_like_header(df.columns):
            return df

        # 1행 헤더로는 식별자 컬럼을 못 찾았다 — 1행+2행을 컬럼별로 합쳐서 다시 시도한다.
        raw_rows = pd.read_excel(io.BytesIO(content), dtype=str, engine=engine, header=None, nrows=2)
        if len(raw_rows) < 2:
            return df
        row1, row2 = list(raw_rows.iloc[0]), list(raw_rows.iloc[1])
        merged_header = [r1 if not _is_blank(r1) else r2 for r1, r2 in zip(row1, row2)]
        if not _looks_like_header(merged_header):
            return df

        df_merged = pd.read_excel(io.BytesIO(content), dtype=str, engine=engine, header=None, skiprows=2)
        df_merged.columns = merged_header[: len(df_merged.columns)]
        return df_merged
    except UnsupportedFileTypeError:
        raise
    except Exception as exc:  # noqa: BLE001 — 확장자는 맞지만(손상된 파일, 지원하지 않는
        # 내부 구조 등) 내용을 읽지 못하는 모든 경우를 사용자에게 원인과 함께 안내한다.
        raise FileParseError(f"파일을 읽을 수 없습니다 (형식이 손상되었거나 지원하지 않는 구조입니다): {exc}") from exc
