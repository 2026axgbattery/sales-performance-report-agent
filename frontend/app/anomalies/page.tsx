"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { BatchPicker } from "@/components/BatchPicker";
import { PageHeader } from "@/components/PageHeader";
import { ApiError, type AnomalyFlag, anomaliesExportUrl, getAnomalies } from "@/lib/api";
import { formatEok, formatPercent, formatPlainPercent } from "@/lib/format";

// 이상징후 유형별 원시 값 표시 단위. "단위당 매출액"(손익항목계획대비의 sales_final)만
// 억 단위로는 항상 "0.0억"이 되어버리는 단가라 원 단위로 그대로 보여준다.
function formatWon(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function toneForFlag(flag: AnomalyFlag): "danger" | "success" {
  switch (flag.metric_type) {
    case "흑자전환":
    case "판관비급증":
      return "danger";
    case "단가변동":
      // 사용자 확인: "전월대비 단가가 감소했으면 안좋은 영향 - 이지. 분석은 당월을
      // 기준으로 영향성을 보는거야" — 판정 기준(actual_value=당월이 전월/누계 대비
      // 몇 % 움직였는지)의 방향으로 색을 정한다. impact_amount(매출액 차이)로 정하면
      // 단가는 올랐는데 수량 감소로 매출액이 줄어드는 경우처럼 서로 다른 지표가
      // 섞여 실제 판정 방향과 반대로 보일 수 있어(한 차례 그렇게 고쳤다가 되돌림).
      return (flag.actual_value ?? 0) < 0 ? "danger" : "success";
    case "계획대비":
      return (flag.actual_value ?? 0) < (flag.threshold_value ?? 100) ? "danger" : "success";
    default: // 전월대비, 전년대비, 손익항목계획대비
      return (flag.actual_value ?? 0) < 0 ? "danger" : "success";
  }
}

// 사용자 요청: "전월 얼마에서 당월 얼마로 얼마 변동, 이렇게 표현하면 좋겠어" —
// before_value/after_value가 있으면 실제 두 값을 그대로 문장에 넣는다(없으면 %만
// 보여주던 예전 문구로 폴백 — 이론상 항상 채워지지만 방어적으로 둔다).
function describeFlag(flag: AnomalyFlag): string {
  const groupLabel = flag.product_group ? ` · ${flag.product_group}` : " · 미매핑";
  const has = flag.before_value !== null && flag.after_value !== null;
  const diff = has ? flag.after_value! - flag.before_value! : null;
  const diffWord = diff !== null && diff < 0 ? "감소" : "증가";

  switch (flag.metric_type) {
    case "흑자전환":
      return has
        ? `${flag.team}${groupLabel} — 영업이익 전월 ${formatEok(flag.before_value)}에서 당월 ${formatEok(flag.after_value)}로 흑자에서 적자로 전환했습니다`
        : `${flag.team}${groupLabel} — 흑자에서 적자로 전환 (영업이익 ${formatEok(flag.actual_value)})`;

    case "계획대비":
      // Phase 17부터 계획대비는 팀 단위로만 판정해 product_group이 항상 null이다 —
      // "· 미매핑"이 아니라 "팀 전체"를 뜻하므로 groupLabel을 붙이지 않는다.
      return has
        ? `${flag.team} — 매출액 계획 ${formatEok(flag.before_value)} 대비 실적 ${formatEok(flag.after_value)}로 ${formatPlainPercent(flag.actual_value)} 달성했습니다`
        : `${flag.team} — 계획 대비 ${formatPlainPercent(flag.actual_value)} 달성`;

    case "단가변동": {
      // 사용자 요청(Phase 20, .docs/phase/phase_20_단가변동누계평균통합.md): "당월
      // 평균단가와 전월, 누계를 한꺼번에 비교" — 폐지된 "누계평균대비"의 누계 비교를
      // 여기로 흡수했으므로, 전월/누계 중 하나가 비교 불가여도 나머지는 그대로 보여준다.
      const current = flag.after_value;
      const prevPart =
        current !== null && flag.before_value !== null
          ? `전월 ${formatWon(flag.before_value)}(${formatWon(Math.abs(current - flag.before_value))}, ${formatPercent(
              ((current - flag.before_value) / flag.before_value) * 100,
            )} 차이)`
          : "전월 비교 불가";
      const cumPart =
        current !== null && flag.cumulative_before_value !== null
          ? `누계평균 ${formatWon(flag.cumulative_before_value)}(${formatWon(
              Math.abs(current - flag.cumulative_before_value),
            )}, ${formatPercent(((current - flag.cumulative_before_value) / flag.cumulative_before_value) * 100)} 차이)`
          : "누계평균 비교 불가";
      return `${flag.team}${groupLabel} — 당월 평균단가 ${formatWon(current)}, ${prevPart}, ${cumPart}`;
    }

    case "판관비급증":
      return has
        ? `${flag.team}${groupLabel} — 판관비 전월 ${formatEok(flag.before_value)}에서 당월 ${formatEok(flag.after_value)}로 ${formatEok(Math.abs(diff!))} 증가했습니다(${formatPercent(flag.actual_value)})`
        : `${flag.team}${groupLabel} — 판관비 전월 대비 ${formatPercent(flag.actual_value)}`;

    case "손익항목계획대비": {
      // pl_item_analysis.py의 "단위당 매출액"(sales_final)만 억 단위로는 항상
      // "0.0억"이 되어버리는 단가라 원 단위로 보여준다.
      const isUnitBasis = flag.product_group === "매출액";
      const fmt = isUnitBasis ? formatWon : formatEok;
      const label = isUnitBasis ? "단위당 매출액" : flag.product_group;
      return has
        ? `${flag.team} — ${label} 계획 ${fmt(flag.before_value)} 대비 실적 ${fmt(flag.after_value)}로 ${fmt(Math.abs(diff!))} ${diffWord}했습니다(${formatPercent(flag.actual_value)})`
        : `${flag.team} — ${label} 계획 대비 ${formatPercent(flag.actual_value)}`;
    }

    default: {
      // 전월대비/전년대비 — 모두 매출액을 서로 다른 기준과 비교한다.
      const compareLabel = flag.metric_type === "전년대비" ? "전년동월" : "전월";
      return has
        ? `${flag.team}${groupLabel} — 매출액 ${compareLabel} ${formatEok(flag.before_value)}에서 당월 ${formatEok(flag.after_value)}로 ${formatEok(Math.abs(diff!))} ${diffWord}했습니다(${formatPercent(flag.actual_value)})`
        : `${flag.team}${groupLabel} — ${flag.metric_type} ${formatPercent(flag.actual_value)}`;
    }
  }
}

export default function AnomaliesPage() {
  return (
    <Suspense fallback={null}>
      <AnomaliesPageInner />
    </Suspense>
  );
}

function AnomaliesPageInner() {
  const preferredBatchId = useSearchParams().get("batch");
  const [batchId, setBatchId] = useState<string | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyFlag[] | null>(null);
  const [anomaliesBatchId, setAnomaliesBatchId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("전체");
  const [teamFilter, setTeamFilter] = useState<string>("전체");

  useEffect(() => {
    if (!batchId) return;
    let cancelled = false;
    getAnomalies(batchId)
      .then((data) => {
        if (cancelled) return;
        setAnomalies(data);
        setAnomaliesBatchId(batchId);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "이상징후 목록을 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [batchId]);

  // batchId를 바꾸면 새 데이터가 도착하기 전까지 이전 배치의 목록이 잠깐 보이지 않도록 가드한다.
  const currentAnomalies = anomaliesBatchId === batchId ? anomalies : null;

  const metricTypes = useMemo(() => {
    if (!currentAnomalies) return [];
    return Array.from(new Set(currentAnomalies.map((a) => a.metric_type)));
  }, [currentAnomalies]);

  const teams = useMemo(() => {
    if (!currentAnomalies) return [];
    return Array.from(new Set(currentAnomalies.map((a) => a.team)));
  }, [currentAnomalies]);

  // 판단 기준 필터 버튼의 개수는 "팀 필터를 적용했을 때" 기준으로, 팀 필터 버튼의
  // 개수는 "판단 기준 필터를 적용했을 때" 기준으로 보여준다(두 필터를 동시에 걸 수
  // 있으므로, 각 버튼 행이 서로 다른 필터가 이미 적용된 상태를 기준으로 세야 실제로
  // 클릭했을 때 몇 건이 보일지와 숫자가 일치한다).
  const byTeam = useMemo(() => {
    if (!currentAnomalies) return [];
    return teamFilter === "전체" ? currentAnomalies : currentAnomalies.filter((a) => a.team === teamFilter);
  }, [currentAnomalies, teamFilter]);

  const byMetric = useMemo(() => {
    if (!currentAnomalies) return [];
    return filter === "전체" ? currentAnomalies : currentAnomalies.filter((a) => a.metric_type === filter);
  }, [currentAnomalies, filter]);

  const filtered = useMemo(() => {
    if (teamFilter === "전체") return byMetric;
    return byMetric.filter((a) => a.team === teamFilter);
  }, [byMetric, teamFilter]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="⑤ 이상징후 하이라이트"
        description="임계치를 초과한 항목을 영향 금액순으로 정렬했습니다."
        actions={
          <>
            <BatchPicker value={batchId} onChange={setBatchId} preferredBatchId={preferredBatchId} />
            {batchId && (
              <a
                href={anomaliesExportUrl(batchId)}
                className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm font-semibold hover:bg-[var(--light-gray-50)]"
              >
                엑셀 다운로드
              </a>
            )}
          </>
        }
      />

      {error && (
        <div className="rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-4 py-3 text-sm text-[var(--color-danger)]">
          {error}
        </div>
      )}

      {currentAnomalies && (
        <>
          <div className="flex flex-wrap gap-2">
            {["전체", ...metricTypes].map((m) => (
              <button
                key={m}
                onClick={() => setFilter(m)}
                className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${
                  filter === m
                    ? "border-[var(--color-brand-primary)] bg-[var(--color-brand-primary)] text-white"
                    : "border-[var(--color-border)] bg-[var(--light-gray-50)] text-[var(--color-text-secondary)]"
                }`}
              >
                {m} {m !== "전체" ? `(${byTeam.filter((a) => a.metric_type === m).length})` : `(${byTeam.length})`}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            {["전체", ...teams].map((t) => (
              <button
                key={t}
                onClick={() => setTeamFilter(t)}
                className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${
                  teamFilter === t
                    ? "border-[var(--sebang-green-700)] bg-[var(--sebang-green-700)] text-white"
                    : "border-[var(--color-border)] bg-[var(--light-gray-50)] text-[var(--color-text-secondary)]"
                }`}
              >
                {t} {t !== "전체" ? `(${byMetric.filter((a) => a.team === t).length})` : `(${byMetric.length})`}
              </button>
            ))}
          </div>

          {filtered.length === 0 ? (
            <p className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-6 text-center text-sm text-[var(--color-text-secondary)]">
              이상징후가 없습니다.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--light-gray-200)] rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)]">
              {filtered.map((flag) => {
                const tone = toneForFlag(flag);
                return (
                  <li key={flag.flag_id} className="flex items-start gap-4 p-4">
                    <span
                      className={`mt-0.5 flex-shrink-0 rounded px-2 py-0.5 text-xs font-bold ${
                        tone === "danger"
                          ? "bg-[var(--orange-50)] text-[var(--color-danger)]"
                          : "bg-[var(--green-50)] text-[var(--sebang-green-700)]"
                      }`}
                    >
                      {flag.metric_type}
                    </span>
                    <div className="flex-1 text-sm">{describeFlag(flag)}</div>
                    <div className="flex-shrink-0 text-right">
                      <div
                        className={`text-sm font-bold ${
                          tone === "danger" ? "text-[var(--color-danger)]" : "text-[var(--sebang-green-700)]"
                        }`}
                      >
                        {formatEok(flag.impact_amount)}
                      </div>
                      <div className="text-[11px] text-[var(--color-text-secondary)]">영향 금액</div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
