"use client";

import { useEffect, useMemo, useState } from "react";
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
import { PageHeader } from "@/components/PageHeader";
import {
  ApiError,
  type ReportDraft,
  type ReportItem,
  type TrendResponse,
  type UpdateReportItemInput,
  createReportDraft,
  getTrend,
  reportExportUrl,
  reportRefinedExportUrl,
  updateReportItem,
} from "@/lib/api";
import { formatEok } from "@/lib/format";

function groupByTeam(items: ReportItem[]): Map<string, ReportItem[]> {
  const groups = new Map<string, ReportItem[]>();
  for (const item of items) {
    const list = groups.get(item.chart_ref) ?? [];
    list.push(item);
    groups.set(item.chart_ref, list);
  }
  return groups;
}

export default function ReportsPage() {
  const [batchId, setBatchId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ReportDraft | null>(null);
  const [draftBatchId, setDraftBatchId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trends, setTrends] = useState<Record<string, TrendResponse>>({});

  const currentDraft = draft && draftBatchId === batchId ? draft : null;
  const groups = useMemo(
    () => (currentDraft ? groupByTeam(currentDraft.items) : new Map<string, ReportItem[]>()),
    [currentDraft],
  );

  useEffect(() => {
    if (!currentDraft) return;
    let cancelled = false;
    const teams = Array.from(groups.keys());
    Promise.all(teams.map((team) => getTrend(currentDraft.batch_id, team)))
      .then((results) => {
        if (cancelled) return;
        const next: Record<string, TrendResponse> = {};
        teams.forEach((team, i) => {
          next[team] = results[i];
        });
        setTrends(next);
      })
      .catch(() => {
        if (!cancelled) setTrends({});
      });
    return () => {
      cancelled = true;
    };
  }, [currentDraft, groups]);

  async function handleGenerate() {
    if (!batchId) return;
    setGenerating(true);
    setError(null);
    try {
      const created = await createReportDraft(batchId);
      setDraft(created);
      setDraftBatchId(batchId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "보고서 초안 생성에 실패했습니다.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleItemUpdate(itemId: string, updates: UpdateReportItemInput) {
    if (!currentDraft) return;
    try {
      const updated = await updateReportItem(currentDraft.draft_id, itemId, updates);
      setDraft(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "수정 내용을 저장하지 못했습니다.");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="⑥ 보고서 초안 자동 생성 · 검토"
        description="이상징후 리스트를 근거로 팀별 추이 그래프와 수치 기반 코멘트를 자동 생성합니다. 코멘트 수정, 배경 설명 추가, 오탐지 제외가 가능합니다."
        actions={
          <>
            <BatchPicker value={batchId} onChange={setBatchId} />
            <button
              onClick={handleGenerate}
              disabled={!batchId || generating}
              className="rounded-md bg-[var(--color-accent-primary)] px-4 py-2 text-sm font-semibold text-white hover:bg-[#C82B00] disabled:opacity-50"
            >
              {generating ? "생성 중…" : "초안 생성"}
            </button>
          </>
        }
      />

      {error && (
        <div className="rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-4 py-3 text-sm text-[var(--color-danger)]">
          {error}
        </div>
      )}

      {currentDraft && (
        <div className="flex flex-wrap justify-end gap-2">
          <a
            href={reportRefinedExportUrl(currentDraft.draft_id)}
            className="rounded-md border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text-primary)] hover:bg-[var(--light-gray-50)]"
          >
            실적 Re-arrange 전체 다운로드 (xlsx)
          </a>
          <a
            href={reportExportUrl(currentDraft.draft_id)}
            className="rounded-md border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text-primary)] hover:bg-[var(--light-gray-50)]"
          >
            ⑦ 보고서 초안 엑셀 다운로드 (제외 항목 제외)
          </a>
        </div>
      )}

      {currentDraft && currentDraft.items.length === 0 && (
        <p className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-6 text-center text-sm text-[var(--color-text-secondary)]">
          이 배치에는 이상징후가 없어 보고서 항목이 생성되지 않았습니다.
        </p>
      )}

      {currentDraft &&
        Array.from(groups.entries()).map(([team, items]) => {
          const trend = trends[team];
          return (
            <section
              key={team}
              className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-5"
            >
              <h2 className="mb-3 text-base font-bold">{team}</h2>
              {trend ? (
                <div className="h-56 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={trend.months.map((m) => ({ ...m, monthLabel: `${m.month}월` }))}>
                      <CartesianGrid stroke="var(--light-gray-200)" strokeDasharray="3 3" />
                      <XAxis dataKey="monthLabel" stroke="var(--color-text-secondary)" fontSize={12} />
                      <YAxis stroke="var(--color-text-secondary)" fontSize={12} tickFormatter={(v) => formatEok(v)} />
                      <Tooltip formatter={(value) => formatEok(typeof value === "number" ? value : null)} />
                      <Bar dataKey="actual_amount" name="매출액" fill="var(--sebang-dark-gray)" barSize={24} />
                      <Line type="monotone" dataKey="profit" name="영업이익" stroke="var(--sebang-orange)" strokeWidth={2} dot={false} connectNulls={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-sm text-[var(--color-text-secondary)]">추이 불러오는 중…</p>
              )}
              <ul className="mt-4 space-y-3">
                {items.map((item) => (
                  <ReportItemRow key={item.item_id} item={item} onUpdate={handleItemUpdate} />
                ))}
              </ul>
            </section>
          );
        })}
    </div>
  );
}

function ReportItemRow({
  item,
  onUpdate,
}: {
  item: ReportItem;
  onUpdate: (itemId: string, updates: UpdateReportItemInput) => Promise<void>;
}) {
  const [comment, setComment] = useState(item.user_comment ?? item.auto_comment);
  const [note, setNote] = useState(item.background_note ?? "");

  return (
    <li
      className={`rounded-md border p-3 text-sm ${
        item.is_excluded
          ? "border-[var(--light-gray-200)] bg-[var(--light-gray-50)] opacity-60"
          : "border-[var(--light-gray-200)]"
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex-shrink-0 rounded bg-[var(--light-gray-50)] px-2 py-0.5 text-xs font-bold text-[var(--color-text-secondary)]">
          {item.metric_type}
        </span>
        <div className="flex-1 space-y-2">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onBlur={() => {
              if (comment !== (item.user_comment ?? item.auto_comment)) {
                onUpdate(item.item_id, { user_comment: comment });
              }
            }}
            rows={2}
            className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-2 text-sm"
          />
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => {
              if (note !== (item.background_note ?? "")) {
                onUpdate(item.item_id, { background_note: note });
              }
            }}
            placeholder="배경 설명 (특이비용 사유, 거래처 이슈 등)"
            className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-2 text-xs"
          />
        </div>
        <label className="flex flex-shrink-0 items-center gap-1 text-xs text-[var(--color-text-secondary)]">
          <input
            type="checkbox"
            checked={item.is_excluded}
            onChange={(e) => onUpdate(item.item_id, { is_excluded: e.target.checked })}
          />
          제외
        </label>
      </div>
    </li>
  );
}
