"use client";

import { useEffect, useState } from "react";

import { type BatchSummary, listBatches } from "@/lib/api";

interface BatchPickerProps {
  value: string | null;
  onChange: (batchId: string) => void;
  /** 목록에 있으면 이 배치를 기본 선택으로 우선한다 (예: F1 업로드 직후 ?batch= 링크로 들어온 경우).
   * 없으면 기존처럼 가장 최근(연/월 기준) 배치를 기본 선택한다. */
  preferredBatchId?: string | null;
}

export function BatchPicker({ value, onChange, preferredBatchId }: BatchPickerProps) {
  const [batches, setBatches] = useState<BatchSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listBatches()
      .then((result) => {
        if (cancelled) return;
        setBatches(result);
        if (!value && result.length > 0) {
          const preferred = preferredBatchId && result.some((b) => b.batch_id === preferredBatchId);
          onChange(preferred ? preferredBatchId! : result[0].batch_id);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return <p className="text-sm text-[var(--color-danger)]">배치 목록을 불러오지 못했습니다: {error}</p>;
  }

  if (batches === null) {
    return <p className="text-sm text-[var(--color-text-secondary)]">불러오는 중…</p>;
  }

  if (batches.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-secondary)]">
        업로드된 실적이 없습니다. F1 업로드 화면에서 먼저 데이터를 업로드하세요.
      </p>
    );
  }

  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-base)] px-3 py-1.5 text-sm"
    >
      {batches.map((b) => (
        <option key={b.batch_id} value={b.batch_id}>
          {b.year}년 {b.month}월
        </option>
      ))}
    </select>
  );
}
