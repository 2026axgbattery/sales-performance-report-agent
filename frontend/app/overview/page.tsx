"use client";

import { useSearchParams } from "next/navigation";
import { Fragment, Suspense, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { BatchPicker } from "@/components/BatchPicker";
import { OverviewDetailTabs } from "@/components/OverviewDetailTabs";
import { OverviewPdfDownloadButton } from "@/components/OverviewPdfDownloadButton";
import { PageHeader } from "@/components/PageHeader";
import {
  ApiError,
  type OverviewResponse,
  type TeamMatrixPeriod,
  type TeamMatrixRow,
  type TrendResponse,
  getOverview,
  getTrend,
} from "@/lib/api";
import { changeTone, formatEok, formatEokNumber, formatPlainPercent, formatQuantity } from "@/lib/format";

export default function OverviewPage() {
  // useSearchParams는 Suspense 경계 안에서만 정적 빌드가 가능하다(Next.js 요구 사항).
  return (
    <Suspense fallback={null}>
      <OverviewPageInner />
    </Suspense>
  );
}

function OverviewPageInner() {
  // F1 업로드 완료 후 "Overview에서 확인" 버튼으로 넘어오면 방금 업로드한 배치를
  // 기본 선택으로 우선한다 (없으면 BatchPicker가 최신 배치를 기본 선택한다).
  const preferredBatchId = useSearchParams().get("batch");
  const [batchId, setBatchId] = useState<string | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [trend, setTrend] = useState<TrendResponse | null>(null);

  useEffect(() => {
    if (!batchId) return;
    let cancelled = false;
    getOverview(batchId)
      .then((data) => {
        if (cancelled) return;
        setOverview(data);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Overview를 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [batchId]);

  // 배치를 바꿔도 선택된 팀은 유지한다 — getTrend가 새 배치의 연도를 기준으로 다시 조회하므로
  // 별도로 초기화하지 않아도 항상 현재 배치와 일치하는 추이가 표시된다.
  useEffect(() => {
    if (!batchId || !selectedTeam) return;
    let cancelled = false;
    getTrend(batchId, selectedTeam)
      .then((data) => {
        if (!cancelled) setTrend(data);
      })
      .catch(() => {
        if (!cancelled) setTrend(null);
      });
    return () => {
      cancelled = true;
    };
  }, [batchId, selectedTeam]);

  // batchId를 바꾸면 새 데이터가 도착하기 전까지 이전 배치의 Overview가 잠깐 보이지 않도록 가드한다.
  const currentOverview = overview && overview.batch_id === batchId ? overview : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="④ 전체 실적 Overview"
        description="팀별 순위, 목표 대비 실적, 전월·전년 동월 대비를 한눈에 확인합니다."
        actions={
          <>
            <BatchPicker value={batchId} onChange={setBatchId} preferredBatchId={preferredBatchId} />
            {batchId && <OverviewPdfDownloadButton batchId={batchId} />}
          </>
        }
      />

      {error && (
        <div className="rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-4 py-3 text-sm text-[var(--color-danger)]">
          {error}
        </div>
      )}

      {currentOverview && (
        <>
          <OverviewSummarySection overview={currentOverview} />

          <TeamMatrixTables
            matrix={currentOverview.team_matrix}
            year={currentOverview.year}
            month={currentOverview.month}
            selectedTeam={selectedTeam}
            onSelectTeam={setSelectedTeam}
          />

          {selectedTeam && (
            <section className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-5">
              <h2 className="mb-3 text-base font-bold">{selectedTeam} — 월별 실적 추이 ({currentOverview.year}년)</h2>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div className="h-64 w-full">
                  {trend ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={trend.months.map((m) => ({ ...m, monthLabel: `${m.month}월` }))}>
                        <CartesianGrid stroke="var(--light-gray-200)" strokeDasharray="3 3" />
                        <XAxis dataKey="monthLabel" stroke="var(--color-text-secondary)" fontSize={12} />
                        {/* 매출액·영업이익은 절대 규모 차이가 커서 축을 공유하면 영업이익 선이
                            거의 평평하게 보인다 — 각자 자체 스케일(auto domain)의 축을 따로
                            둬서 영업이익 변동도 눈에 띄게 한다(사용자 확인). */}
                        <YAxis
                          yAxisId="amount"
                          stroke="var(--color-text-secondary)"
                          fontSize={12}
                          tickFormatter={(v) => formatEok(v)}
                        />
                        <YAxis
                          yAxisId="profit"
                          orientation="right"
                          stroke="var(--sebang-orange)"
                          fontSize={12}
                          domain={["auto", "auto"]}
                          tickFormatter={(v) => formatEok(v)}
                        />
                        <Tooltip formatter={(value) => formatEok(typeof value === "number" ? value : null)} />
                        <Bar yAxisId="amount" dataKey="actual_amount" name="매출액" fill="var(--sebang-dark-gray)" barSize={24} />
                        <Line
                          yAxisId="profit"
                          type="monotone"
                          dataKey="profit"
                          name="영업이익"
                          stroke="var(--sebang-orange)"
                          strokeWidth={2}
                          dot={false}
                          connectNulls={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-sm text-[var(--color-text-secondary)]">불러오는 중…</p>
                  )}
                </div>
                {(() => {
                  const selectedRow = currentOverview.team_matrix.find((r) => r.team === selectedTeam);
                  return selectedRow ? (
                    <YtdAchievementPanel
                      year={currentOverview.year}
                      month={currentOverview.month}
                      ytd={selectedRow.ytd}
                    />
                  ) : null;
                })()}
              </div>
              <p className="mt-2 text-xs text-[var(--color-text-secondary)]">
                데이터가 없는 달은 선으로 이어지지 않습니다 (아직 업로드되지 않은 달).
              </p>
            </section>
          )}

          <OverviewDetailTabs key={currentOverview.batch_id} batchId={currentOverview.batch_id} />
        </>
      )}
    </div>
  );
}

// 누계(YTD) 목표 대비 달성률을 막대 그래프로 보여준다. "예상"이 아니라 "실적"으로
// 표기한다 — 이 MVP는 실적 데이터만 다루고 예측(다음 달 실적 전망)은 PRD상 이후 단계
// (P2)로 명시적으로 미룬 기능이라, 실측값을 예측값처럼 보이게 라벨링하지 않는다.
// 목표/실적 열의 폭을 고정(w-24)해 위쪽 값 라벨·막대·아래쪽 "목표"/"실적" 글자가
// 모두 같은 중심선에 정렬되도록 한다(값 라벨 길이가 달라도 어긋나지 않음, 사용자 확인).
function AchievementBarGraph({
  label,
  planValue,
  actualValue,
  planTopLabel,
  actualTopLabel,
  insideLabel,
}: {
  label: string;
  planValue: number | null;
  actualValue: number;
  planTopLabel: string;
  actualTopLabel: string;
  insideLabel: ReactNode;
}) {
  const maxAbs = Math.max(Math.abs(planValue ?? 0), Math.abs(actualValue), 1);
  const planHeightPct = Math.max((Math.abs(planValue ?? 0) / maxAbs) * 100, 4);
  const actualHeightPct = Math.max((Math.abs(actualValue) / maxAbs) * 100, 4);

  return (
    <div className="flex flex-1 flex-col items-center">
      <div className="mb-2 text-sm font-bold">{label}</div>
      <div className="flex h-32 w-full items-end justify-center gap-6">
        <div className="flex h-full w-24 flex-col items-center justify-end">
          <div className="mb-1 w-full text-center text-[11px] font-bold leading-tight">{planTopLabel}</div>
          <div className="w-14 rounded-t-sm bg-[var(--light-gray-400)]" style={{ height: `${planHeightPct}%` }} />
        </div>
        <div className="flex h-full w-24 flex-col items-center justify-end">
          <div className="mb-1 w-full text-center text-[11px] font-bold leading-tight text-[var(--color-danger)]">
            {actualTopLabel}
          </div>
          <div
            className="flex w-14 items-center justify-center rounded-t-sm bg-[var(--sebang-green-700)]"
            style={{ height: `${actualHeightPct}%` }}
          >
            <span className="px-1 text-center text-[10px] font-semibold leading-tight text-white">{insideLabel}</span>
          </div>
        </div>
      </div>
      <div className="mt-2 flex w-full justify-center gap-6 text-xs text-[var(--color-text-secondary)]">
        <span className="w-24 text-center">목표</span>
        <span className="w-24 text-center">실적</span>
      </div>
    </div>
  );
}

function YtdAchievementPanel({ year, month, ytd }: { year: number; month: number; ytd: TeamMatrixPeriod }) {
  const amountDiff = ytd.plan_amount !== null ? ytd.actual_amount - ytd.plan_amount : null;
  const profitDiff = ytd.plan_profit !== null ? ytd.actual_profit - ytd.plan_profit : null;
  // 영업이익 실적이 (-)이면 목표 대비 % 계산이 의미가 없어(부호가 뒤집혀 오히려 좋아
  // 보이는 착시) 퍼센트 대신 "-"로 표기한다(사용자 확인). 증감액은 그대로 보여준다.
  const profitRateText = ytd.actual_profit < 0 ? "-" : formatPlainPercent(ytd.profit_achievement_rate);

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-base)] p-4">
      <div className="mb-3 text-xs font-semibold text-[var(--color-text-secondary)]">
        누계 목표 대비 달성률 ({year}년 1월~{month}월)
      </div>
      <div className="flex gap-4">
        <AchievementBarGraph
          label="매출액"
          planValue={ytd.plan_amount}
          actualValue={ytd.actual_amount}
          planTopLabel={`${formatEok(ytd.plan_amount)}(${formatQuantity(ytd.plan_quantity)})`}
          actualTopLabel={`${formatEok(ytd.actual_amount)}(${formatQuantity(ytd.actual_quantity)})`}
          insideLabel={
            <>
              {formatPlainPercent(ytd.amount_achievement_rate)}
              <br />({formatEok(amountDiff)})
            </>
          }
        />
        <AchievementBarGraph
          label="영업이익"
          planValue={ytd.plan_profit}
          actualValue={ytd.actual_profit}
          planTopLabel={`${formatEok(ytd.plan_profit)}(${formatPlainPercent(ytd.plan_profit_rate)})`}
          actualTopLabel={`${formatEok(ytd.actual_profit)}(${formatPlainPercent(ytd.actual_profit_rate)})`}
          insideLabel={
            <>
              {profitRateText}
              <br />({formatEok(profitDiff)})
            </>
          }
        />
      </div>
    </div>
  );
}

// README 핵심 수치 카드(assets/readme/stats.svg)와 같은 형태 — 좌측 컬러 띠 + 큰 숫자.
// 띠 색은 값의 상태(tone)를 따른다: 상승=성공 그린, 하락=위험 오렌지, 그 외=브랜드 다크그레이.
function KpiCard({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" | "neutral" }) {
  const toneClass =
    tone === "up" ? "text-[var(--color-success)]" : tone === "down" ? "text-[var(--color-danger)]" : "";
  const barClass =
    tone === "up"
      ? "bg-[var(--color-success)]"
      : tone === "down"
        ? "bg-[var(--color-danger)]"
        : "bg-[var(--color-brand-primary)]";
  return (
    <div className="relative overflow-hidden rounded-lg border border-[var(--color-border)] bg-white py-4 pl-6 pr-4 shadow-[var(--shadow-card)]">
      <div className={`absolute inset-y-0 left-0 w-1.5 ${barClass}`} aria-hidden />
      <div className="text-xs font-semibold text-[var(--color-text-secondary)]">{label}</div>
      <div className={`mt-1 text-[28px] font-extrabold leading-tight tracking-tight ${toneClass}`}>{value}</div>
    </div>
  );
}

// %p(퍼센트포인트) 차이 표기 — 이익률처럼 이미 %인 값끼리의 차이는 "%"가 아니라
// "%p"로 구분해야 혼동이 없다(사용자 확인 캡션 형식).
function formatPP(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%p`;
}

// 상단 요약 카드(수량·매출·영업이익·이익률)와 그 아래 "계획 대비"·"전월 대비" 한 줄
// 요약. 계획 대비는 team_matrix의 "합계" 행(당월) 데이터를 그대로 쓰고, 전월 대비는
// summary의 전월 원시 합계(매출·영업이익)로 직접 계산한다.
function OverviewSummarySection({ overview }: { overview: OverviewResponse }) {
  const { summary } = overview;
  const totalRow = overview.team_matrix.find((r) => r.team === "합계")?.mtd;

  const planAmountDiff = totalRow?.plan_amount != null ? summary.total_actual_amount - totalRow.plan_amount : null;
  const planProfitDiff = totalRow?.profit_diff ?? null;
  const planProfitRateDiff =
    totalRow?.plan_profit_rate != null && totalRow?.actual_profit_rate != null
      ? totalRow.actual_profit_rate - totalRow.plan_profit_rate
      : null;

  const prevAmountDiff = summary.prev_month_available && summary.prev_month_total_amount != null
    ? summary.total_actual_amount - summary.prev_month_total_amount
    : null;
  const prevProfitDiff = summary.prev_month_available && summary.prev_month_total_profit != null
    ? summary.total_profit - summary.prev_month_total_profit
    : null;
  const prevProfitRateDiff =
    summary.prev_month_available && summary.prev_month_total_profit_rate != null
      ? summary.total_profit_rate !== null
        ? summary.total_profit_rate - summary.prev_month_total_profit_rate
        : null
      : null;

  return (
    <section className="space-y-3">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <KpiCard label="수량" value={formatQuantity(summary.total_quantity)} />
        <KpiCard label="매출" value={formatEok(summary.total_actual_amount)} />
        <KpiCard label="영업이익" value={formatEok(summary.total_profit)} tone={changeTone(summary.total_profit)} />
        <KpiCard label="이익률" value={formatPlainPercent(summary.total_profit_rate)} />
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] px-4 py-3 text-sm">
        <p>
          <span className="font-semibold">계획 대비</span>: 매출 {formatEok(planAmountDiff)}
          {totalRow?.amount_achievement_rate != null ? `(${formatPlainPercent(totalRow.amount_achievement_rate)})` : ""} / 영업이익{" "}
          {formatEok(planProfitDiff)} / 영업이익률 {formatPP(planProfitRateDiff)}
        </p>
        <p className="mt-1">
          <span className="font-semibold">전월 대비</span>:{" "}
          {summary.prev_month_available ? (
            <>
              매출 {formatEok(prevAmountDiff)}
              {summary.prev_month_change_pct != null ? `(${formatPlainPercent(summary.prev_month_change_pct)})` : ""} / 영업이익{" "}
              {formatEok(prevProfitDiff)} / 영업이익률 {formatPP(prevProfitRateDiff)}
            </>
          ) : (
            "전월 배치가 없어 비교할 수 없습니다."
          )}
        </p>
      </div>
    </section>
  );
}

// "산전팀"은 실적 데이터에 없는 화면 표시용 합산 그룹(고정형+모티브)이라 추이 조회 대상이
// 될 수 없고, "합계" 행은 클릭해도 보여줄 단일 팀 추이가 없다 — 개별 실팀 행만 클릭 가능하다.
function RateCell({ value }: { value: number | null }) {
  const isOutlier = value !== null && (value < 90 || value > 120);
  return <span className={isOutlier ? "font-semibold text-[var(--color-danger)]" : ""}>{formatPlainPercent(value)}</span>;
}

function TeamMatrixTable({
  title,
  year,
  month,
  matrix,
  leafLabels,
  compareLeafLabels,
  selectedTeam,
  onSelectTeam,
  renderCells,
}: {
  title: string;
  year: number;
  month: number;
  matrix: TeamMatrixRow[];
  leafLabels: [string, string];
  compareLeafLabels?: [string, string];
  selectedTeam: string | null;
  onSelectTeam: (team: string) => void;
  renderCells: (period: TeamMatrixPeriod) => ReactNode[];
}) {
  const compareLabels = compareLeafLabels ?? leafLabels;
  const headerCell = "border border-white/25 bg-[var(--sebang-green-700)] px-3 py-1.5 text-xs font-semibold text-white";
  const dividerPad = "pl-5";
  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-base font-bold">{title}</h2>
        <span className="text-xs text-[var(--color-text-secondary)]">(금액 단위: 억원)</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr>
              <th rowSpan={3} className={`${headerCell} text-center align-middle`}>
                팀
              </th>
              <th colSpan={6} className={`${headerCell} text-center`}>
                {year}년 {month}월
              </th>
              <th colSpan={6} className={`${headerCell} ${dividerPad} text-center`}>
                {year}년 누계
              </th>
            </tr>
            <tr>
              {[0, 1].map((half) => (
                <Fragment key={half}>
                  <th colSpan={2} className={`${headerCell} text-center ${half === 1 ? dividerPad : ""}`}>
                    목표
                  </th>
                  <th colSpan={2} className={`${headerCell} text-center`}>
                    실적
                  </th>
                  <th colSpan={2} className={`${headerCell} text-center`}>
                    대비
                  </th>
                </Fragment>
              ))}
            </tr>
            <tr>
              {[0, 1].map((half) => (
                <Fragment key={half}>
                  <th className={`${headerCell} text-center ${half === 1 ? dividerPad : ""}`}>{leafLabels[0]}</th>
                  <th className={`${headerCell} text-center`}>{leafLabels[1]}</th>
                  <th className={`${headerCell} text-center`}>{leafLabels[0]}</th>
                  <th className={`${headerCell} text-center`}>{leafLabels[1]}</th>
                  <th className={`${headerCell} text-center`}>{compareLabels[0]}</th>
                  <th className={`${headerCell} text-center`}>{compareLabels[1]}</th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row) => {
              const isTotal = row.team === "합계";
              const clickable = !row.is_synthetic && !isTotal;
              const label = isTotal ? "합 계" : row.team;
              return (
                <tr
                  key={row.team}
                  onClick={clickable ? () => onSelectTeam(row.team) : undefined}
                  className={`border-b border-[var(--light-gray-200)] last:border-0 ${
                    isTotal ? "border-t-2 border-[var(--color-border)] bg-[var(--green-50)] font-semibold" : ""
                  } ${clickable ? "cursor-pointer hover:bg-[var(--light-gray-50)]" : ""} ${
                    selectedTeam === row.team ? "bg-[var(--light-gray-50)]" : ""
                  } ${row.is_synthetic ? "italic text-[var(--color-text-secondary)]" : ""}`}
                >
                  <td className="px-3 py-2 text-center font-semibold">{label}</td>
                  {renderCells(row.mtd).map((cell, i) => (
                    <td key={`mtd-${i}`} className={`px-3 py-2 text-right ${i === 0 ? `border-l border-[var(--light-gray-200)] ${dividerPad}` : ""}`}>
                      {cell}
                    </td>
                  ))}
                  {renderCells(row.ytd).map((cell, i) => (
                    <td key={`ytd-${i}`} className={`px-3 py-2 text-right ${i === 0 ? `border-l border-[var(--color-border)] ${dividerPad}` : ""}`}>
                      {cell}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TeamMatrixTables({
  matrix,
  year,
  month,
  selectedTeam,
  onSelectTeam,
}: {
  matrix: TeamMatrixRow[];
  year: number;
  month: number;
  selectedTeam: string | null;
  onSelectTeam: (team: string) => void;
}) {
  return (
    <>
      <TeamMatrixTable
        title="팀별 목표 대비 실적 — 수량·매출액"
        year={year}
        month={month}
        matrix={matrix}
        leafLabels={["수량", "매출액"]}
        selectedTeam={selectedTeam}
        onSelectTeam={onSelectTeam}
        renderCells={(p) => [
          formatQuantity(p.plan_quantity),
          formatEokNumber(p.plan_amount),
          formatQuantity(p.actual_quantity),
          formatEokNumber(p.actual_amount),
          <RateCell key="qty-rate" value={p.quantity_achievement_rate} />,
          <RateCell key="amt-rate" value={p.amount_achievement_rate} />,
        ]}
      />
      <TeamMatrixTable
        title="팀별 목표 대비 실적 — 영업이익"
        year={year}
        month={month}
        matrix={matrix}
        leafLabels={["금액", "이익율"]}
        compareLeafLabels={["금액", "금액(%)"]}
        selectedTeam={selectedTeam}
        onSelectTeam={onSelectTeam}
        renderCells={(p) => [
          formatEokNumber(p.plan_profit),
          formatPlainPercent(p.plan_profit_rate),
          formatEokNumber(p.actual_profit),
          formatPlainPercent(p.actual_profit_rate),
          formatEokNumber(p.profit_diff),
          <RateCell key="profit-rate" value={p.profit_achievement_rate} />,
        ]}
      />
    </>
  );
}
