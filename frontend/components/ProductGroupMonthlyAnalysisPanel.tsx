"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import {
  ApiError,
  type MonthlyAnalysisFilterOptions,
  type ProductGroupMonthlyAnalysisResponse,
  getMonthlyAnalysisFilterOptions,
  getProductGroupMonthlyAnalysis,
} from "@/lib/api";
import { formatMillion, formatPlainPercent, formatQuantity } from "@/lib/format";

import { ErrorBox, MonthlyAnalysisTable, type MonthlyAnalysisDisplayRow } from "./MonthlyAnalysisTable";
import { MultiSelectDropdown } from "./MultiSelectDropdown";

const LEAF_LABELS = ["수량", "매출액", "영업이익", "이익률", "판매가", "제조원가율", "판관비율"];

// 팀 드릴다운 필터는 거래처별 탭(CustomerMonthlyAnalysisPanel)과 동일한 구성이다
// (사용자 요청) — 서버에 team 쿼리 파라미터로 보내 다시 조회한다.
export function ProductGroupMonthlyAnalysisPanel({ batchId }: { batchId: string }) {
  const [team, setTeam] = useState<string[]>([]);
  const [filterOptions, setFilterOptions] = useState<MonthlyAnalysisFilterOptions | null>(null);
  const [data, setData] = useState<ProductGroupMonthlyAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMonthlyAnalysisFilterOptions(batchId)
      .then((res) => {
        if (!cancelled) setFilterOptions(res);
      })
      .catch(() => {
        if (!cancelled) setFilterOptions(null);
      });
    return () => {
      cancelled = true;
    };
  }, [batchId]);

  useEffect(() => {
    let cancelled = false;
    getProductGroupMonthlyAnalysis(batchId, { team })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "월별 실적 분석(제품군별)을 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [batchId, team]);

  let body: ReactNode = <p className="text-sm text-[var(--color-text-secondary)]">불러오는 중…</p>;
  if (data) {
    const rows: MonthlyAnalysisDisplayRow[] = [];
    for (const group of data.groups) {
      rows.push({ key: `${group.team}-header`, label: group.team, metrics: null });
      for (const r of group.rows) {
        rows.push({
          key: `${group.team}-${r.product_group_2 ?? "미분류"}`,
          label: r.product_group_2 ?? "미분류",
          metrics: { mtd: r.mtd, ytd: r.ytd },
          indent: true,
        });
      }
      rows.push({
        key: `${group.team}-요약`,
        label: `${group.team} 요약`,
        metrics: group.subtotal,
        variant: "subtotal",
      });
    }
    rows.push({ key: "합계", label: "합계", metrics: data.total, variant: "total" });

    body = (
      <MonthlyAnalysisTable
        year={data.year}
        month={data.month}
        leafLabels={LEAF_LABELS}
        rows={rows}
        renderCells={(m) => [
          formatQuantity(m.quantity),
          formatMillion(m.actual_amount),
          formatMillion(m.profit),
          formatPlainPercent(m.profit_rate),
          formatMillion(m.avg_unit_price, 3),
          formatPlainPercent(m.mfg_cost_rate),
          formatPlainPercent(m.sga_rate),
        ]}
      />
    );
  }

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-5">
      <h2 className="mb-1 text-base font-bold">월별 실적 분석 — 제품군별</h2>
      <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
        단위: 수량 EA, 금액 백만원. 팀 드릴다운으로 좁혀 제품군(제품구분2)별 실적과 팀 소계를 표시합니다.
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        <MultiSelectDropdown label="팀" options={filterOptions?.teams ?? []} selected={team} onChange={setTeam} />
      </div>
      {error ? <ErrorBox message={error} /> : body}
    </section>
  );
}
