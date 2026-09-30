"use client";

import type { ReactNode } from "react";

import type { MonthlyMetrics, MonthlyMetricsPeriod } from "@/lib/api";

// F4 "월별 실적 분석" 탭 3종(팀별/제품군별/거래처별)이 공유하는 당월|금년누계 2단 헤더
// 표 — app/overview/page.tsx의 TeamMatrixTable(목표 대비 실적)과 같은 레이아웃 패턴을
// 재사용한다. 계획 데이터가 없는 순수 실적 집계라 "목표" 컬럼군이 없다는 점만 다르다.
export interface MonthlyAnalysisDisplayRow {
  key: string;
  label: string;
  metrics: MonthlyMetricsPeriod | null; // null이면 팀 그룹 헤더 행(값 없이 팀명만 표시)
  variant?: "normal" | "subtotal" | "total";
  indent?: boolean;
}

// whitespace-nowrap — 헤더 라벨("표준매출원가" 등 5자 이상)이 좁은 컬럼에서 줄바꿈되며
// 글자가 밀리지 않도록 한다(사용자 확인). 실제 컬럼 폭은 각 표의 min-width로 확보한다.
export const HEADER_CELL =
  "border border-white/25 bg-[var(--sebang-green-700)] px-2 py-1.5 text-center whitespace-nowrap text-[11px] font-semibold text-white";

export function MonthlyAnalysisTable({
  year,
  month,
  leafLabels,
  rows,
  renderCells,
}: {
  year: number;
  month: number;
  leafLabels: string[];
  rows: MonthlyAnalysisDisplayRow[];
  renderCells: (m: MonthlyMetrics) => ReactNode[];
}) {
  const n = leafLabels.length;
  // 컬럼 수에 비례해 최소 너비를 확보한다 — 좁은 화면에서도 헤더/숫자가 서로 밀리지
  // 않고 필요하면 가로 스크롤이 뜨도록 한다(사용자 확인: "글자가 밀리지 않도록").
  const minWidth = 140 + n * 2 * 90;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" style={{ minWidth }}>
        <thead>
          <tr>
            <th rowSpan={2} className={`${HEADER_CELL} text-left`}>
              구분
            </th>
            <th colSpan={n} className={HEADER_CELL}>
              {year}년 {month}월 (당월)
            </th>
            <th colSpan={n} className={`${HEADER_CELL} pl-3`}>
              {year}년 누계
            </th>
          </tr>
          <tr>
            {leafLabels.map((label, i) => (
              <th key={`mtd-${i}`} className={`${HEADER_CELL} ${i === 0 ? "pl-3" : ""}`}>
                {label}
              </th>
            ))}
            {leafLabels.map((label, i) => (
              <th key={`ytd-${i}`} className={`${HEADER_CELL} ${i === 0 ? "pl-3" : ""}`}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            if (row.metrics === null) {
              return (
                <tr key={row.key} className="border-b border-[var(--light-gray-200)] bg-[var(--light-gray-50)]">
                  <td colSpan={1 + n * 2} className="px-2 py-1.5 text-left text-xs font-bold">
                    {row.label}
                  </td>
                </tr>
              );
            }
            // "OO 요약"(팀별 소계) 행은 밝은 노랑으로, 표 전체 "합계" 행은 기존 F4 목표
            // 대비 실적 표와 같은 초록 톤으로 강조한다(사용자 확인).
            const rowStyle =
              row.variant === "total"
                ? "bg-[var(--green-50)] font-semibold border-t-2 border-[var(--color-border)]"
                : row.variant === "subtotal"
                  ? "bg-[#fff59d] font-semibold"
                  : "";
            return (
              <tr key={row.key} className={`border-b border-[var(--light-gray-200)] last:border-0 ${rowStyle}`}>
                <td className={`px-2 py-1.5 text-left whitespace-nowrap ${row.indent ? "pl-6" : ""}`}>{row.label}</td>
                {renderCells(row.metrics.mtd).map((cell, i) => (
                  <td key={`mtd-${i}`} className={`px-2 py-1.5 text-center whitespace-nowrap ${i === 0 ? "pl-3" : ""}`}>
                    {cell}
                  </td>
                ))}
                {renderCells(row.metrics.ytd).map((cell, i) => (
                  <td key={`ytd-${i}`} className={`px-2 py-1.5 text-center whitespace-nowrap ${i === 0 ? "pl-3" : ""}`}>
                    {cell}
                  </td>
                ))}
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={1 + n * 2} className="px-2 py-3 text-center text-xs text-[var(--color-text-secondary)]">
                데이터가 없습니다.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-4 py-3 text-sm text-[var(--color-danger)]">
      {message}
    </div>
  );
}
