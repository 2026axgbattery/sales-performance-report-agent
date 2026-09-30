"use client";

import { Fragment, useEffect, useState } from "react";

import { ApiError, type MonthlyMetrics, type TeamMonthlyAnalysisResponse, getTeamMonthlyAnalysis } from "@/lib/api";
import { formatMillion, formatPlainPercent, formatQuantity } from "@/lib/format";

import { ErrorBox, HEADER_CELL } from "./MonthlyAnalysisTable";

// 사용자가 제공한 참고 이미지 그대로: 팀(여러 행에 걸쳐 병합)/월/수량/매출액/영업이익/
// 이익률/판관비/판관비율/제조원가/제조원가율/표준매출원가 — 당월|누계 2단 비교가 아니다.
const COLUMNS = ["수량", "매출액", "영업이익", "이익률", "판관비", "판관비율", "제조원가", "제조원가율", "표준매출원가"];

// 사용자 확인: 매출액 등 금액은 소수점 없이 정수로 표기한다(수량·비율은 기존 그대로).
function renderCells(m: MonthlyMetrics) {
  return [
    formatQuantity(m.quantity),
    formatMillion(m.actual_amount, 0),
    formatMillion(m.profit, 0),
    formatPlainPercent(m.profit_rate),
    formatMillion(m.sga_amount, 0),
    formatPlainPercent(m.sga_rate),
    formatMillion(m.mfg_cost, 0),
    formatPlainPercent(m.mfg_cost_rate),
    formatMillion(m.standard_cogs, 0),
  ];
}

const EMPTY_CELLS = COLUMNS.map(() => "-");

export function TeamMonthlyAnalysisPanel({ batchId }: { batchId: string }) {
  const [data, setData] = useState<TeamMonthlyAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTeamMonthlyAnalysis(batchId)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "월별 실적 분석(팀별)을 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [batchId]);

  const body = !data ? (
    <p className="text-sm text-[var(--color-text-secondary)]">불러오는 중…</p>
  ) : (
    <div className="overflow-x-auto">
      {/* border-collapse — 각 셀에 개별 border를 주면서 collapse를 안 하면 셀마다 이중
          테두리(+기본 border-spacing)가 누적돼 폭 계산이 어긋나 보인다(실제로 겪은
          "표준매출원가 오른쪽에 빈 컬럼이 있다" 버그의 원인 중 하나 — 사용자 확인).
          table-fixed도 쓰지 않는다 — 폭을 등분해버려 "표준매출원가" 같은 5자 헤더가
          비좁아지고 글자가 밀린다(auto 레이아웃 + whitespace-nowrap으로 필요한 만큼만
          차지하게 하고, 넘치면 overflow-x-auto로 가로 스크롤한다). */}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className={HEADER_CELL}>팀</th>
            <th className={HEADER_CELL}>월</th>
            {COLUMNS.map((label) => (
              <th key={label} className={HEADER_CELL}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.teams.map((team) => (
            <Fragment key={team.team}>
              {team.months.map((month, i) => (
                <tr key={month.month} className="border-b border-[var(--light-gray-200)]">
                  {i === 0 && (
                    <td
                      rowSpan={team.months.length + 1}
                      className="border border-[var(--light-gray-200)] px-2 py-1.5 text-center align-middle font-semibold whitespace-nowrap text-[var(--sebang-green-700)]"
                    >
                      {team.team}
                    </td>
                  )}
                  <td className="border border-[var(--light-gray-200)] px-2 py-1.5 text-center font-semibold whitespace-nowrap text-[var(--sebang-green-700)]">
                    {month.month}월
                  </td>
                  {(month.metrics ? renderCells(month.metrics) : EMPTY_CELLS).map((cell, ci) => (
                    <td key={ci} className="border border-[var(--light-gray-200)] px-2 py-1.5 text-center whitespace-nowrap">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
              {/* colSpan=1 — 팀 칸은 위 첫 달 행에서 이미 rowSpan으로 이 행까지 차지하고
                  있으므로(rowSpan={team.months.length + 1}), 여기서 또 2칸을 차지하면
                  칸 수가 하나 남아 표 맨 오른쪽에 빈 컬럼이 생긴다(실제로 겪은 버그). */}
              <tr className="border-b-2 border-[var(--color-border)] bg-[#fff59d] font-semibold">
                <td colSpan={1} className="border border-[var(--light-gray-200)] px-2 py-1.5 text-center whitespace-nowrap">
                  {team.team} 요약
                </td>
                {renderCells(team.summary).map((cell, ci) => (
                  <td key={ci} className="border border-[var(--light-gray-200)] px-2 py-1.5 text-center whitespace-nowrap">
                    {cell}
                  </td>
                ))}
              </tr>
            </Fragment>
          ))}
          <tr className="border-t-2 border-[var(--color-border)] bg-[var(--green-50)] font-semibold">
            <td colSpan={2} className="border border-[var(--light-gray-200)] px-2 py-1.5 text-center whitespace-nowrap">
              합계
            </td>
            {renderCells(data.total).map((cell, ci) => (
              <td key={ci} className="border border-[var(--light-gray-200)] px-2 py-1.5 text-center whitespace-nowrap">
                {cell}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-5">
      <h2 className="mb-1 text-base font-bold">월별 실적 분석 — 팀별</h2>
      <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
        단위: 수량 EA, 금액 백만원. 팀별로 1~12월 실적과 연간 합계(&ldquo;팀 요약&rdquo;)를 표시합니다(업로드되지 않은 달은 빈 값).
      </p>
      {error ? <ErrorBox message={error} /> : body}
    </section>
  );
}
