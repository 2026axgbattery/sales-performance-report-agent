"use client";

import { useState } from "react";

import { CustomerMonthlyAnalysisPanel } from "./CustomerMonthlyAnalysisPanel";
import { PLComparisonPanel } from "./PLComparisonPanel";
import { ProductGroupMonthlyAnalysisPanel } from "./ProductGroupMonthlyAnalysisPanel";
import { TeamMonthlyAnalysisPanel } from "./TeamMonthlyAnalysisPanel";

// F4 Overview의 "손익 상세 분석" 영역을 탭으로 확장한다(Phase 14, 사용자 요청: "손익 상세
// 분석의 위치에 내용을 탭 형태로 해서 누를 때마다 다른 화면이 나올 수 있게"). 앞의 3개
// 탭(월별 실적 분석 팀별/제품군별/거래처별)은 계획 대비가 아닌 순수 실적 집계이고, 마지막
// "손익 상세 분석" 탭은 기존 PLComparisonPanel(계획·전월 대비 드릴다운)을 그대로 재사용한다.
const TABS = [
  { key: "team", label: "월별 실적 분석(팀별)" },
  { key: "product-group", label: "월별 실적 분석(제품군별)" },
  { key: "customer", label: "월별 실적 분석(거래처별)" },
  { key: "pl-comparison", label: "손익 상세 분석" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export function OverviewDetailTabs({ batchId }: { batchId: string }) {
  const [activeTab, setActiveTab] = useState<TabKey>("team");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 border-b border-[var(--color-border)]">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold ${
              activeTab === tab.key
                ? "border-[var(--sebang-green-700)] text-[var(--sebang-green-700)]"
                : "border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "team" && <TeamMonthlyAnalysisPanel batchId={batchId} />}
      {activeTab === "product-group" && <ProductGroupMonthlyAnalysisPanel batchId={batchId} />}
      {activeTab === "customer" && <CustomerMonthlyAnalysisPanel batchId={batchId} />}
      {activeTab === "pl-comparison" && <PLComparisonPanel batchId={batchId} />}
    </div>
  );
}
