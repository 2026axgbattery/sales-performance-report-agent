"""외부 데모 배포용 가상 데이터 시드 (Phase 26, .docs/phase/phase_26_백엔드외부배포.md).

실데이터는 전혀 쓰지 않는다. tests/fixtures/actual_sample.csv 한 행의 계정 비율만 빌려와
가공의 거래처·제품으로 2026년 1~8월 실적을 만들고, 더미 판매계획과 함께 앱의 POST /uploads로 넣는다.

실행: APP_DB_PATH=/tmp/demo.duckdb python -m scripts.seed_demo
"""
from __future__ import annotations

import io
import os
import random
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_CSV = BACKEND_DIR / "tests" / "fixtures" / "actual_sample.csv"
PLAN_XLSX = BACKEND_DIR / "demo_data" / "판매계획_더미데이터.xlsx"

SALES_COLS = {"매출액(Total)", "매출액", "기타매출액", "제품매출조정", "매출액A(조정전)", "총매출액", "매출할인"}
QTY_COL = "매출수량"
ID_COLS = {"상품", "고객", "손익 센터", "기간/연도"}

# (손익센터 코드, 매핑표 접두사, 월 목표 규모, 원가 배율, 제품 목록)
TEAMS = {
    "차량대리점": (20313, "차량대리점", 64e8, 1.00, [
        ("PCC90101", "GB 60L(샘플-대리점)", "GB", "GB 소형계열", "GB 소형", 62000),
        ("PCC90102", "GB 90L(샘플-대리점)", "GB", "GB 중형계열", "GB 중형", 98000),
        ("PCC90103", "GB 150L(샘플-대리점)", "GB", "GB 대형계열", "GB 대형", 141000),
    ]),
    "차량OE": (20399, "차량OE", 60e8, 1.42, [
        ("PCC90201", "AGM 70(샘플-OE)", "AGM", "AGM 중형계열", "AGM 중형", 118000),
        ("PCC90202", "GB 80(샘플-OE)", "GB", "GB 중형계열", "GB 중형", 86000),
    ]),
    "모티브": (20342, "산전", 110e8, 1.18, [
        ("PIJ90301", "Longest GC8(샘플)", "모티브", "모티브", "Longest (GC8)", 165000),
        ("PIJ90302", "MSB 중형(샘플)", "MSB", "MSB 중형계열", "MSB 중형", 270000),
    ]),
    "고정형": (20345, "산전", 90e8, 1.05, [
        ("PIJ90401", "ES 대형(샘플)", "ES", "ES 대형계열", "ES 대형", 245000),
        ("PIJ90402", "VGS 중형(샘플)", "VGS", "VGS 중형계열", "VGS 중형", 560000),
        ("PIJ90403", "CGS 소형(샘플)", "CGS", "CGS 소형계열", "CGS 소형", 280000),
    ]),
}
CUSTOMERS = [
    ("290001x", "샘플상사(대전)"), ("290002x", "가상모터스(부산)"), ("290003x", "예시정비공업사"),
    ("290004x", "데모에너지(주)"), ("290005x", "테스트산업(주)"), ("290006x", "모의유통(광주)"),
]


def build_demo_frames(seed: int = 2026) -> tuple[pd.DataFrame, pd.DataFrame]:
    """가상 실적(1~8월)과 그에 맞는 제품분류 매핑표를 만든다."""
    rng = random.Random(seed)
    tpl = pd.read_csv(TEMPLATE_CSV, dtype=str).iloc[1]
    columns = list(tpl.index)
    base_sales = float(tpl["매출액(Total)"])

    rows, mapping = [], {}
    for month in range(1, 9):
        seasonal = 1 + 0.18 * (month in (1, 2, 7)) - 0.12 * (month in (4, 5))
        for profit_center, prefix, plan, cost_ratio, products in TEAMS.values():
            team_target = plan * seasonal * rng.uniform(0.78, 1.18)
            weights = [rng.uniform(0.6, 1.4) for _ in products]
            for (code, desc, g1, g2, g3, price), w in zip(products, weights):
                mapping[prefix + code] = (prefix, code, g1, g2, g3, desc)
                product_target = team_target * w / sum(weights)
                customers = rng.sample(CUSTOMERS, 3)
                splits = [rng.uniform(0.5, 1.5) for _ in customers]
                unit_price = price * rng.uniform(0.9, 1.1)
                for (ccode, cname), s in zip(customers, splits):
                    amount = product_target * s / sum(splits)
                    f = amount / base_sales
                    cost_f = f * cost_ratio * rng.uniform(0.92, 1.08)
                    row = {}
                    for c in columns:
                        if c in ID_COLS:
                            continue
                        v = float(tpl[c] or 0)
                        if c == QTY_COL:
                            row[c] = round(amount / unit_price)
                        elif c in SALES_COLS:
                            row[c] = round(v * f)
                        else:
                            row[c] = round(v * cost_f)
                    row["상품"] = f"{code}           {desc}"
                    row["고객"] = f"{ccode}    {cname}"
                    row["손익 센터"] = str(profit_center)
                    row["기간/연도"] = f"2026/{month:03d} {month}월 2026"
                    rows.append(row)

    actual = pd.DataFrame(rows)[columns]
    mapping_df = pd.DataFrame(
        [
            {"인자": k, "구분(팀)": p, "제품": code, "구분": "완제품", "용도": "완제품",
             "제품구분1(보고4용)": g1, "제품구분2(보고3용)": g2, "제품구분3(계획비교용)": g3,
             "제품구분4": g1, "자재내역(Desc)": desc}
            for k, (p, code, g1, g2, g3, desc) in mapping.items()
        ]
    )
    return actual, mapping_df


def _csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")


def seed(client) -> int:
    """비어 있는 DB에만 데모 데이터를 넣고, 생성한 배치 수를 반환한다(이미 있으면 0)."""
    if client.get("/batches").json()["batches"]:
        return 0
    actual, mapping_df = build_demo_frames()
    files = [
        ("files", ("demo_actual.csv", _csv_bytes(actual), "text/csv")),
        ("files", ("demo_mapping.csv", _csv_bytes(mapping_df), "text/csv")),
        ("files", (PLAN_XLSX.name, PLAN_XLSX.read_bytes(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
    ]
    response = client.post(
        "/uploads",
        files=files,
        data={"file_types": ["실적", "매핑표", "계획"], "confirm_overwrite": "true"},
    )
    response.raise_for_status()
    batches = response.json()["batches"]
    # 다중 월 업로드는 계획 저장이 집계보다 늦게 실행되는 알려진 문제(Phase 23 기록)가 있어 배치별로 재계산한다.
    for batch in batches:
        client.post(f"/batches/{batch['batch_id']}/recompute").raise_for_status()
    return len(batches)


def main() -> int:
    if not os.environ.get("APP_DB_PATH"):
        print("APP_DB_PATH가 설정되지 않아 시드를 중단합니다 — 실데이터가 든 로컬 DB(backend/data/app.duckdb)를 보호하기 위함.",
              file=sys.stderr)
        return 1
    from fastapi.testclient import TestClient

    from app.main import app

    created = seed(TestClient(app))
    print(f"데모 시드 완료: 새 배치 {created}개" if created else "데모 시드 건너뜀: 이미 데이터가 있습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
