"use client";

import { useEffect, useRef, useState } from "react";

// F4 드릴다운 화면들이 공유하는 다중 선택 드롭다운(원래 PLComparisonPanel 전용이었다가,
// 사용자 요청으로 "손익 상세분석에 적용한 것과 같이" 월별 실적 분석 탭들도 같은 컴포넌트를
// 쓰도록 공용으로 뺐다).
export function MultiSelectDropdown({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  function toggle(value: string) {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  }

  const buttonText = selected.length === 0 ? `${label} 전체` : `${label} (${selected.length})`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`rounded-md border px-2 py-1.5 text-xs ${
          selected.length > 0
            ? "border-[var(--sebang-green-700)] bg-[var(--green-50)] font-semibold text-[var(--sebang-green-700)]"
            : "border-[var(--color-border)] bg-[var(--color-bg-base)]"
        }`}
      >
        {buttonText} ▾
      </button>
      {open && (
        <div className="absolute z-10 mt-1 max-h-64 w-56 overflow-y-auto rounded-md border border-[var(--color-border)] bg-[var(--color-bg-base)] p-2 shadow-lg">
          <button
            type="button"
            onClick={() => onChange([])}
            className="mb-1 w-full rounded px-2 py-1 text-left text-xs font-semibold text-[var(--color-text-secondary)] hover:bg-[var(--light-gray-50)]"
          >
            전체 선택 해제
          </button>
          {options.map((value) => (
            <label
              key={value}
              className="flex items-center gap-2 rounded px-2 py-1 text-xs hover:bg-[var(--light-gray-50)]"
            >
              <input type="checkbox" checked={selected.includes(value)} onChange={() => toggle(value)} />
              <span className="truncate">{value}</span>
            </label>
          ))}
          {options.length === 0 && <p className="px-2 py-1 text-xs text-[var(--color-text-secondary)]">선택 가능한 값 없음</p>}
        </div>
      )}
    </div>
  );
}
