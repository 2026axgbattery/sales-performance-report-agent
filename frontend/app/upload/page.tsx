"use client";

import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import {
  ApiError,
  type UploadFileType,
  type UploadRequiresConfirmation,
  type UploadResult,
  uploadFiles,
} from "@/lib/api";

type OtherFileType = Exclude<UploadFileType, "실적">;

const OTHER_FILE_TYPES: OtherFileType[] = ["계획", "손익계산서", "매핑표"];

interface OtherFileRow {
  id: number;
  file: File | null;
  fileType: OtherFileType;
}

let nextId = 1;

export default function UploadPage() {
  // 실적 파일은 F2 제품코드-제품군 매핑 정제가 적용되는 유일한 입력이라(.docs/02_prd.md F2 참고),
  // 종류를 바꿀 수 없는 별도 구역으로 분리한다 — 계획/손익계산서/매핑표와 섞어서 종류를
  // 잘못 지정할 여지를 없앤다.
  const [actualFile, setActualFile] = useState<File | null>(null);
  const [otherRows, setOtherRows] = useState<OtherFileRow[]>([{ id: nextId++, file: null, fileType: "매핑표" }]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Phase 19(.docs/phase/phase_19_실적파일다중월분할업로드.md) — 실적 파일에 여러 달이
  // 섞여 있고 그중 일부가 이미 배치가 있는 달과 겹치면, 백엔드가 커밋 없이
  // requires_confirmation만 돌려준다. 확인/건너뛰기 버튼을 누를 때 같은 파일들로
  // 다시 요청해야 하므로 그 시점의 entries를 그대로 들고 있는다.
  const [confirmation, setConfirmation] = useState<UploadRequiresConfirmation | null>(null);
  const [pendingEntries, setPendingEntries] = useState<{ file: File; fileType: UploadFileType }[] | null>(
    null,
  );

  function addOtherRow() {
    setOtherRows((prev) => [...prev, { id: nextId++, file: null, fileType: "매핑표" }]);
  }

  function removeOtherRow(id: number) {
    setOtherRows((prev) => prev.filter((r) => r.id !== id));
  }

  function updateOtherRow(id: number, patch: Partial<OtherFileRow>) {
    setOtherRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setConfirmation(null);

    if (!actualFile) {
      setError("실적 파일을 업로드하세요 (필수).");
      return;
    }

    const entries: { file: File; fileType: UploadFileType }[] = [{ file: actualFile, fileType: "실적" }];
    for (const row of otherRows) {
      if (row.file) entries.push({ file: row.file, fileType: row.fileType });
    }

    setSubmitting(true);
    try {
      const response = await uploadFiles(entries);
      if (response.requires_confirmation) {
        setConfirmation(response);
        setPendingEntries(entries);
      } else {
        setResult(response);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "알 수 없는 오류가 발생했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirmOverwrite(overwrite: boolean) {
    if (!pendingEntries) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await uploadFiles(pendingEntries, overwrite);
      if (response.requires_confirmation) {
        // 이론상 도달하지 않는다(같은 파일을 confirm_overwrite와 함께 재요청하면 항상 커밋됨).
        setConfirmation(response);
      } else {
        setResult(response);
        setConfirmation(null);
        setPendingEntries(null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "알 수 없는 오류가 발생했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="① 파일 업로드"
        description="실적 파일은 필수이며, 판매계획·팀별손익계산서·제품분류 매핑표는 선택적으로 함께 업로드할 수 있습니다. 매핑표를 업로드하지 않으면 이전에 저장된 매핑표를 그대로 사용합니다."
      />

      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="rounded-lg border border-[var(--color-brand-primary)] bg-white p-5 shadow-[var(--shadow-card)]">
          <h2 className="text-sm font-bold">실적 파일 (필수)</h2>
          <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
            제품코드-제품군 매핑 정제(F2)는 이 파일에만 적용됩니다.
          </p>
          <input
            type="file"
            accept=".xlsx,.xls,.xlsb,.csv"
            onChange={(e) => setActualFile(e.target.files?.[0] ?? null)}
            className="mt-3 w-full text-sm"
          />
        </div>

        <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-5">
          <h2 className="text-sm font-bold text-[var(--color-text-secondary)]">추가 파일 (선택)</h2>
          {otherRows.map((row) => (
            <div key={row.id} className="flex items-center gap-3">
              <select
                value={row.fileType}
                onChange={(e) => updateOtherRow(row.id, { fileType: e.target.value as OtherFileType })}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-base)] px-3 py-1.5 text-sm"
              >
                {OTHER_FILE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <input
                type="file"
                accept=".xlsx,.xls,.xlsb,.csv"
                onChange={(e) => updateOtherRow(row.id, { file: e.target.files?.[0] ?? null })}
                className="flex-1 text-sm"
              />
              {otherRows.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeOtherRow(row.id)}
                  className="text-xs font-semibold text-[var(--color-text-secondary)] hover:text-[var(--color-danger)]"
                >
                  삭제
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            onClick={addOtherRow}
            className="rounded-md border border-[var(--color-brand-primary)] px-3 py-1.5 text-sm font-semibold text-[var(--color-brand-primary)]"
          >
            + 파일 추가
          </button>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-[var(--color-accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {submitting ? "업로드 중…" : "업로드 및 정제·분석 시작"}
          </button>
        </div>
      </form>

      {error && (
        <div className="rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-4 py-3 text-sm text-[var(--color-danger)]">
          {error}
        </div>
      )}

      {confirmation && (
        <div className="rounded-lg border border-[#F7AD99] bg-[var(--orange-50)] p-5 text-sm">
          <h2 className="mb-2 text-base font-bold text-[var(--color-danger)]">
            이미 데이터가 있는 달이 있습니다 — 덮어쓸까요?
          </h2>
          <p className="mb-1">
            <span className="font-semibold">겹치는 달(기존 데이터 있음):</span>{" "}
            {confirmation.conflicting_periods.join(", ")}
          </p>
          {confirmation.new_periods.length > 0 && (
            <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
              새로운 달({confirmation.new_periods.join(", ")})은 선택과 무관하게 항상 저장됩니다.
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={submitting}
              onClick={() => handleConfirmOverwrite(true)}
              className="rounded-md bg-[var(--color-danger)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              겹치는 달 덮어쓰기
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => handleConfirmOverwrite(false)}
              className="rounded-md border border-[var(--color-border)] px-4 py-2 text-sm font-semibold hover:bg-[var(--light-gray-50)] disabled:opacity-50"
            >
              겹치는 달은 건너뛰고 새 달만 저장
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-5 text-sm">
          <h2 className="mb-3 text-base font-bold">
            업로드 결과{result.batches.length <= 1 ? ` — ${result.target_period}` : ` — ${result.batches.length}개 기간`}
          </h2>
          {result.warning && (
            <p className="mb-3 rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-3 py-2 text-[var(--color-danger)]">
              {result.warning}
            </p>
          )}
          {result.skipped_periods.length > 0 && (
            <p className="mb-3 rounded-md border border-[var(--color-border)] bg-[var(--light-gray-50)] px-3 py-2 text-xs text-[var(--color-text-secondary)]">
              다음 달은 기존 데이터를 그대로 두고 건너뛰었습니다: {result.skipped_periods.join(", ")}
            </p>
          )}

          {result.batches.length <= 1 ? (
            <>
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="전체 행" value={result.total_rows} />
                <Stat label="미매핑" value={result.unmapped_rows} warn={result.unmapped_rows > 0} />
                <Stat label="계산 오류" value={result.calc_error_rows} warn={result.calc_error_rows > 0} />
                <Stat label="이상징후" value={result.anomaly_count} warn={result.anomaly_count > 0} />
              </dl>
              {result.overwrote_existing_batch && (
                <p className="mt-3 text-xs text-[var(--color-text-secondary)]">
                  동일 기간의 기존 데이터를 덮어썼습니다.
                </p>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                <Link
                  href={`/overview?batch=${result.batch_id}`}
                  className="rounded-md bg-[var(--color-accent-primary)] px-4 py-2 text-sm font-semibold text-white"
                >
                  Overview에서 확인 →
                </Link>
                <Link
                  href={`/anomalies?batch=${result.batch_id}`}
                  className="rounded-md border border-[var(--color-border)] px-4 py-2 text-sm font-semibold hover:bg-[var(--light-gray-50)]"
                >
                  이상징후 하이라이트 확인 →
                </Link>
              </div>
            </>
          ) : (
            <div className="space-y-3">
              {result.batches.map((batch) => (
                <div
                  key={batch.batch_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-[var(--color-border)] px-3 py-2"
                >
                  <div>
                    <span className="font-semibold">{batch.target_period}</span>
                    <span className="ml-2 text-xs text-[var(--color-text-secondary)]">
                      행 {batch.total_rows.toLocaleString("ko-KR")} · 미매핑 {batch.unmapped_rows} · 계산오류{" "}
                      {batch.calc_error_rows} · 이상징후 {batch.anomaly_count}
                      {batch.overwrote_existing_batch ? " · 기존 데이터 덮어씀" : ""}
                    </span>
                  </div>
                  <Link
                    href={`/overview?batch=${batch.batch_id}`}
                    className="rounded-md bg-[var(--color-accent-primary)] px-3 py-1.5 text-xs font-semibold text-white"
                  >
                    Overview →
                  </Link>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-[var(--color-text-secondary)]">{label}</dt>
      <dd className={`text-lg font-bold ${warn ? "text-[var(--color-danger)]" : ""}`}>{value.toLocaleString("ko-KR")}</dd>
    </div>
  );
}
