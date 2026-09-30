"use client";

import { useEffect, useState } from "react";

import { BatchPicker } from "@/components/BatchPicker";
import { PageHeader } from "@/components/PageHeader";
import { ApiError, type ThresholdItem, getThresholds, recomputeBatch, updateThresholds } from "@/lib/api";

const METRIC_DESCRIPTIONS: Record<string, string> = {
  전월대비: "전월 대비 매출/이익 증감률 — 이 비율(±) 이상 변동하면 이상징후로 표시합니다.",
  전년대비: "전년 동월 대비 증감률 — 이 비율(±) 이상 변동하면 이상징후로 표시합니다.",
  계획대비: "계획 대비 달성률 — 이 범위를 벗어나면 이상징후로 표시합니다.",
  흑자전환: "손익 흑자→적자 전환 — 임계치 없이 조건 충족 시 항상 표시합니다.",
  단가변동: "평균단가 변동률 — 전월 대비 이 비율(±) 이상 변동하면 표시합니다.",
  판관비급증: "판관비/기타비용 급증 — 전월 대비 이 비율 이상 증가하면 표시합니다 (감소는 표시하지 않음).",
};

export default function ThresholdsPage() {
  const [thresholds, setThresholds] = useState<ThresholdItem[] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);

  useEffect(() => {
    getThresholds()
      .then(setThresholds)
      .catch((err) => setError(err instanceof ApiError ? err.message : "임계치를 불러오지 못했습니다."));
  }, []);

  function updateField(metricType: string, field: keyof ThresholdItem, value: string) {
    setThresholds((prev) =>
      (prev ?? []).map((t) =>
        t.metric_type === metricType ? { ...t, [field]: value === "" ? null : Number(value) } : t,
      ),
    );
    setDirty(true);
    setMessage(null);
  }

  async function handleSave() {
    if (!thresholds) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateThresholds(
        thresholds.map((t) => ({
          metric_type: t.metric_type,
          threshold_value: t.threshold_value,
          threshold_low: t.threshold_low,
          threshold_high: t.threshold_high,
        })),
      );
      setThresholds(updated);
      setDirty(false);
      setMessage("저장했습니다. 다음 분석부터 적용됩니다.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRecompute() {
    if (!batchId) {
      setError("재계산할 배치(월)를 먼저 선택하세요.");
      return;
    }
    setError(null);
    try {
      const result = await recomputeBatch(batchId);
      setMessage(`${batchId} 배치를 재계산했습니다 (이상징후 ${result.anomaly_count}건).`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "재계산에 실패했습니다.");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="⑥ 임계치 설정"
        description="이상징후 판단 기준을 직접 조정할 수 있습니다. 고정값이 아니며, 저장 버튼을 눌러야 반영됩니다."
      />

      {error && (
        <div className="rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-4 py-3 text-sm text-[var(--color-danger)]">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-md border border-[#99D5DD] bg-[var(--green-50)] px-4 py-3 text-sm text-[var(--sebang-green-700)]">
          {message}
        </div>
      )}
      {dirty && !message && (
        <div className="rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-4 py-3 text-sm text-[var(--color-danger)]">
          저장하지 않은 변경 사항이 있습니다.
        </div>
      )}

      {thresholds && (
        <div className="divide-y divide-[var(--light-gray-200)] rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)]">
          {thresholds.map((t) => (
            <div key={t.metric_type} className="grid grid-cols-1 items-center gap-3 p-4 sm:grid-cols-[1fr_auto]">
              <div>
                <div className="text-sm font-semibold">{t.metric_type}</div>
                <div className="text-xs text-[var(--color-text-secondary)]">{METRIC_DESCRIPTIONS[t.metric_type]}</div>
              </div>
              <div className="flex items-center gap-2 justify-self-start sm:justify-self-end">
                {t.metric_type === "흑자전환" ? (
                  <span className="rounded bg-[var(--light-gray-200)] px-3 py-1 text-xs text-[var(--color-text-secondary)]">
                    임계치 없음
                  </span>
                ) : t.metric_type === "계획대비" ? (
                  <>
                    <input
                      type="number"
                      value={t.threshold_low ?? ""}
                      onChange={(e) => updateField(t.metric_type, "threshold_low", e.target.value)}
                      className="w-20 rounded-md border border-[var(--color-border)] px-2 py-1 text-right text-sm"
                    />
                    <span className="text-xs text-[var(--color-text-secondary)]">% ↓</span>
                    <input
                      type="number"
                      value={t.threshold_high ?? ""}
                      onChange={(e) => updateField(t.metric_type, "threshold_high", e.target.value)}
                      className="w-20 rounded-md border border-[var(--color-border)] px-2 py-1 text-right text-sm"
                    />
                    <span className="text-xs text-[var(--color-text-secondary)]">% ↑</span>
                  </>
                ) : (
                  <>
                    <input
                      type="number"
                      value={t.threshold_value ?? ""}
                      onChange={(e) => updateField(t.metric_type, "threshold_value", e.target.value)}
                      className="w-24 rounded-md border border-[var(--color-border)] px-2 py-1 text-right text-sm"
                    />
                    <span className="text-xs text-[var(--color-text-secondary)]">%</span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between border-t border-[var(--color-border)] pt-4">
        <button
          onClick={handleSave}
          disabled={saving || !dirty}
          className="rounded-md bg-[var(--color-accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {saving ? "저장 중…" : "저장"}
        </button>

        <div className="flex items-center gap-3">
          <span className="text-sm text-[var(--color-text-secondary)]">저장 후 즉시 재계산:</span>
          <BatchPicker value={batchId} onChange={setBatchId} />
          <button
            onClick={handleRecompute}
            className="rounded-md border border-[var(--color-brand-primary)] px-3 py-1.5 text-sm font-semibold text-[var(--color-brand-primary)]"
          >
            재계산
          </button>
        </div>
      </div>
    </div>
  );
}
