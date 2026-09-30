"use client";

import { useEffect, useRef, useState } from "react";

import { OVERVIEW_PDF_SECTIONS, overviewExportUrl } from "@/lib/api";

// F4 PDF 다운로드 카테고리 선택(Phase 15, 사용자 요청: "아래의 각 탭의 것도 내용이
// 담겨서 출력이 될수 있께 해줘. 대신 내가 다운로드하고 싶은 카테고리를 체크할수 있게").
// 기본은 전체 선택 — 아무것도 체크하지 않으면 다운로드 링크를 비활성화한다(빈 선택이
// "전체 포함"으로 오해되지 않도록).
export function OverviewPdfDownloadButton({ batchId }: { batchId: string }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(OVERVIEW_PDF_SECTIONS.map((s) => s.key));
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  function toggle(key: string) {
    setSelected((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm font-semibold hover:bg-[var(--light-gray-50)]"
      >
        PDF 다운로드 ▾
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-64 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-base)] p-3 shadow-lg">
          <p className="mb-2 text-xs font-semibold text-[var(--color-text-secondary)]">포함할 카테고리</p>
          <div className="space-y-1">
            {OVERVIEW_PDF_SECTIONS.map((section) => (
              <label key={section.key} className="flex items-center gap-2 rounded px-1 py-1 text-xs hover:bg-[var(--light-gray-50)]">
                <input
                  type="checkbox"
                  checked={selected.includes(section.key)}
                  onChange={() => toggle(section.key)}
                />
                {section.label}
              </label>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => setSelected(OVERVIEW_PDF_SECTIONS.map((s) => s.key))}
              className="text-xs font-semibold text-[var(--color-text-secondary)] hover:text-[var(--sebang-green-700)]"
            >
              전체 선택
            </button>
            {selected.length === 0 ? (
              <span className="rounded-md bg-[var(--light-gray-200)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)]">
                카테고리를 선택하세요
              </span>
            ) : (
              <a
                href={overviewExportUrl(batchId, selected)}
                onClick={() => setOpen(false)}
                className="rounded-md bg-[var(--color-accent-primary)] px-3 py-1.5 text-xs font-semibold text-white"
              >
                다운로드
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
