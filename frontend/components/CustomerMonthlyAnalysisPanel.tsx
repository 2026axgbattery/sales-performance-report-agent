"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import {
  ApiError,
  type CustomerMonthlyAnalysisResponse,
  type MonthlyAnalysisFilterOptions,
  getCustomerMonthlyAnalysis,
  getMonthlyAnalysisFilterOptions,
} from "@/lib/api";
import { formatMillion, formatPlainPercent, formatQuantity } from "@/lib/format";

import { ErrorBox, MonthlyAnalysisTable, type MonthlyAnalysisDisplayRow } from "./MonthlyAnalysisTable";
import { MultiSelectDropdown } from "./MultiSelectDropdown";

const LEAF_LABELS = ["수량", "매출액", "영업이익", "영업이익%"];

// 손익 상세 분석(PLComparisonPanel)과 같은 방식 — 팀·파트 드릴다운 필터를 쿼리
// 파라미터로 서버에 보내 다시 조회한다(사용자 요청: "손익 상세분석에 적용한 것과 같이").
// "파트"는 실적 Re-arrange의 part 컬럼(지점코드 매핑 결과)이다.
export function CustomerMonthlyAnalysisPanel({ batchId }: { batchId: string }) {
  const [team, setTeam] = useState<string[]>([]);
  const [part, setPart] = useState<string[]>([]);
  const [filterOptions, setFilterOptions] = useState<MonthlyAnalysisFilterOptions | null>(null);
  const [data, setData] = useState<CustomerMonthlyAnalysisResponse | null>(null);
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
    getCustomerMonthlyAnalysis(batchId, { team, part })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "월별 실적 분석(거래처별)을 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [batchId, team, part]);

  let body: ReactNode = <p className="text-sm text-[var(--color-text-secondary)]">불러오는 중…</p>;
  if (data) {
    const rows: MonthlyAnalysisDisplayRow[] = [];
    for (const group of data.groups) {
      rows.push({ key: `${group.team}-header`, label: group.team, metrics: null });
      for (const r of group.rows) {
        rows.push({
          key: `${group.team}-${r.customer ?? "미상"}`,
          label: r.customer ?? "미상",
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
          formatMillion(m.actual_amount, 0),
          formatMillion(m.profit, 0),
          formatPlainPercent(m.profit_rate),
        ]}
      />
    );
  }

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-5">
      <h2 className="mb-1 text-base font-bold">월별 실적 분석 — 거래처별</h2>
      <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
        단위: 수량 EA, 금액 백만원. 팀·파트로 드릴다운해 거래처별 실적을 확인합니다.
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        <MultiSelectDropdown label="팀" options={filterOptions?.teams ?? []} selected={team} onChange={setTeam} />
        <MultiSelectDropdown label="파트" options={filterOptions?.parts ?? []} selected={part} onChange={setPart} />
      </div>
      {error ? <ErrorBox message={error} /> : body}
    </section>
  );
}
