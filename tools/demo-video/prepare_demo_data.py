"""발표 영상용 가상 데이터 준비 (Phase 27, .docs/phase/phase_27_발표영상제작.md).

실데이터는 전혀 쓰지 않는다. backend/scripts/seed_demo.py의 가상 실적(1~8월)을 쓰고,
1~7월은 데모 백엔드에 미리 넣고 8월 실적은 영상 안에서 직접 업로드하도록 파일로 분리한다.
팀별 손익계산서(계획)는 가상 판매계획·가상 실적 비율에서 만들어 목표가 서로 맞게 한다.

  python prepare_demo_data.py --out <폴더> --make
  python prepare_demo_data.py --out <폴더> --preload --api http://127.0.0.1:8001
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

import httpx
import openpyxl
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.services.plan import parse_plan_workbook  # noqa: E402
from scripts.seed_demo import PLAN_XLSX, TEAMS, build_demo_frames  # noqa: E402

LIVE_MONTH_PREFIX = "2026/008"  # 영상 안에서 직접 올릴 달(8월)
LIVE_FILE_NAME = "2026년08월_실적RawData_가상.csv"
PRELOAD_FILE_NAME = "preload_actual_1to7.csv"
MAPPING_FILE_NAME = "demo_mapping.csv"
PL_FILE_NAME = "demo_team_pl.xlsx"
HEADER_TEMPLATE = REPO / "손익계산서_더미용.xlsx"  # 계정과목 헤더(81열)만 가져온다

PROFIT_CENTER_TO_TEAM = {cfg[0]: team for team, cfg in TEAMS.items()}
TEAM_ORDER = ["모티브", "고정형", "차량대리점", "차량OE"]
SUBTOTAL_HEADERS = {"매출수량", "매출액(Total)", "매출원가(A)Tot", "매출총이익(A)", "판관비(Total)", "영업이익(A)",
                    "매출원가율", "판관비율", "이익률"}


def _raw_column_for(header: str, raw_columns: set[str]) -> str | None:
    s = header.strip()
    for cand in (s, s + "(A)", s + "(A", s.replace("(A)", "")):
        if cand in raw_columns:
            return cand
    return None


def build_team_pl(actual: pd.DataFrame, out_path: Path, seed: int = 7) -> None:
    rng = random.Random(seed)
    headers = [c.value for c in openpyxl.load_workbook(HEADER_TEMPLATE, data_only=True).worksheets[0][1]]

    plan = parse_plan_workbook(PLAN_XLSX.read_bytes())
    plan_amount: dict[tuple[str, int], float] = defaultdict(float)
    for e in plan:
        plan_amount[(e.team, e.month)] += e.planned_amount

    numeric = actual.drop(columns=[c for c in ("상품", "고객", "손익 센터", "기간/연도") if c in actual]).astype(float)
    team_of_row = actual["손익 센터"].astype(int).map(PROFIT_CENTER_TO_TEAM)
    raw_columns = set(numeric.columns)
    sums = {team: numeric[team_of_row == team].sum() for team in TEAM_ORDER}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "손익계산서 자료"
    ws.append(headers)
    for team in TEAM_ORDER:
        total = sums[team]
        sales_total = total["매출액(Total)"]
        unit_price = sales_total / total["매출수량"]
        for month in range(1, 13):
            amount = plan_amount.get((team, month)) or (sum(v for (t, _), v in plan_amount.items() if t == team) / 12)
            values: dict[str, float] = {"매출수량": round(amount / unit_price), "매출액(Total)": amount}
            for h in headers[2:]:
                key = h.strip()
                if key in SUBTOTAL_HEADERS:
                    continue
                raw = _raw_column_for(h, raw_columns)
                values[key] = amount * total[raw] / sales_total * rng.uniform(0.93, 1.07) if raw else 0.0
            values["매출원가(A)Tot"] = amount * total["매출원가(A)Tot"] / sales_total * rng.uniform(0.955, 0.985)
            values["판관비(Total)"] = amount * total["판관비(Total)"] / sales_total * rng.uniform(0.96, 0.99)
            values["매출총이익(A)"] = amount - values["매출원가(A)Tot"]
            values["영업이익(A)"] = values["매출총이익(A)"] - values["판관비(Total)"]
            values["매출원가율"] = values["매출원가(A)Tot"] / amount
            values["판관비율"] = values["판관비(Total)"] / amount
            values["이익률"] = values["영업이익(A)"] / amount
            ws.append([team, f"{month}월"] + [values.get(h.strip(), 0.0) for h in headers[2:]])
    wb.save(out_path)


def make(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    actual, mapping_df = build_demo_frames()
    live_mask = actual["기간/연도"].str.startswith(LIVE_MONTH_PREFIX)
    actual[~live_mask].to_csv(out / PRELOAD_FILE_NAME, index=False, encoding="utf-8-sig")
    actual[live_mask].to_csv(out / LIVE_FILE_NAME, index=False, encoding="utf-8-sig")
    mapping_df.to_csv(out / MAPPING_FILE_NAME, index=False, encoding="utf-8-sig")
    build_team_pl(actual, out / PL_FILE_NAME)
    print(f"생성: {PRELOAD_FILE_NAME}({int((~live_mask).sum())}행), {LIVE_FILE_NAME}({int(live_mask.sum())}행), "
          f"{MAPPING_FILE_NAME}, {PL_FILE_NAME}")


def preload(out: Path, api: str) -> None:
    mime = {".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    entries = [
        (out / PRELOAD_FILE_NAME, "실적"),
        (out / MAPPING_FILE_NAME, "매핑표"),
        (PLAN_XLSX, "계획"),
        (out / PL_FILE_NAME, "손익계산서"),
    ]
    files = [("files", (p.name, p.read_bytes(), mime[p.suffix])) for p, _ in entries]
    with httpx.Client(base_url=api, timeout=300) as client:
        res = client.post("/uploads", files=files,
                          data={"file_types": [t for _, t in entries], "confirm_overwrite": "true"})
        res.raise_for_status()
        batches = res.json()["batches"]
        # 여러 달을 한 번에 올리면 계획이 집계 뒤에 저장되는 알려진 문제가 있어 배치별로 다시 계산한다.
        for b in batches:
            client.post(f"/batches/{b['batch_id']}/recompute").raise_for_status()
    print("미리 넣은 배치:", ", ".join(b["target_period"] for b in batches))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--preload", action="store_true")
    ap.add_argument("--api", default="http://127.0.0.1:8001")
    args = ap.parse_args()
    if args.make:
        make(args.out)
    if args.preload:
        preload(args.out, args.api)
