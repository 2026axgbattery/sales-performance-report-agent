"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  type PLComparisonFilterOptions,
  type PLComparisonLine,
  getPlComparison,
  getPlComparisonFilterOptions,
} from "@/lib/api";
import { changeTone, formatPercent } from "@/lib/format";

import { MultiSelectDropdown } from "./MultiSelectDropdown";

interface PLComparisonPanelProps {
  batchId: string;
}

const FILTER_FIELDS: { key: keyof FilterState; label: string; optionsKey: keyof PLComparisonFilterOptions }[] = [
  { key: "team", label: "팀", optionsKey: "teams" },
  { key: "customer", label: "고객", optionsKey: "customer" },
  { key: "product_code", label: "상품", optionsKey: "product_code" },
  { key: "desc", label: "DESC", optionsKey: "desc" },
  { key: "product_group_1", label: "제품구분1", optionsKey: "product_group_1" },
  { key: "product_group_2", label: "제품구분2", optionsKey: "product_group_2" },
  { key: "product_group_3", label: "제품구분3", optionsKey: "product_group_3" },
];

// 각 필터는 여러 값을 동시에 체크해서 선택할 수 있다(사용자 확인 — 드릴다운 다중 선택).
interface FilterState {
  team: string[];
  customer: string[];
  product_code: string[];
  desc: string[];
  product_group_1: string[];
  product_group_2: string[];
  product_group_3: string[];
}

const EMPTY_FILTERS: FilterState = {
  team: [],
  customer: [],
  product_code: [],
  desc: [],
  product_group_1: [],
  product_group_2: [],
  product_group_3: [],
};

// 참고 파일(2026년 08월 4. 손익분석(2단계 배포용)_구조파악용.xlsb) "검색용" 시트의
// "1) 계획 대비" 표 "구분" 열 트리 구조를 그대로 반영한다 — 원본은 매출원가/판관비
// 아래 재료비→원재료/주재료/부재료/기타, 노무비→직접/간접, 경비→변동/고정/외주가공,
// 판관비→변동/고정→세부 항목 순으로 중첩되어 있다. 백엔드 LINE_ITEMS는 이미 이 순서
// 그대로 반환하므로, 여기서는 들여쓰기 단계만 매핑한다(0=대분류/최종합계,
// 1=중간 소계, 2=세부 항목).
const LINE_ITEM_INDENT: Record<string, 0 | 1 | 2> = {
  quantity: 0,
  sales_final: 0,
  raw_material_sunyeon: 2,
  raw_material_gyeongyeon: 2,
  raw_material_calcium: 2,
  raw_material_total: 1,
  main_material_jeonjo: 2,
  main_material_kaba: 2,
  main_material_gyeorimpan: 2,
  main_material_total: 1,
  other_material_supplies: 1,
  other_material_etc: 1,
  material_total: 1,
  labor_variable_direct: 2,
  labor_fixed_direct: 2,
  labor_direct: 1,
  labor_indirect: 2,
  labor_total: 1,
  expense_variable: 2,
  expense_fixed: 2,
  expense_outsourcing: 2,
  expense_total: 1,
  other_cogs: 1,
  cogs_final: 0,
  sga_vehicle: 2,
  sga_delivery: 2,
  sga_export: 2,
  sga_installation: 2,
  sga_warranty: 2,
  sga_defect_loss: 2,
  sga_ocean_freight: 2,
  sga_variable: 1,
  sga_personnel: 2,
  sga_welfare: 2,
  sga_entertainment: 2,
  sga_fees: 2,
  sga_other: 2,
  sga_fixed: 1,
  sga_final: 0,
  total_cost: 0,
  operating_profit_final: 0,
};

// 사용자 확인: 핵심 지표(매출수량·매출액·매출원가·판관비 계·영업이익) 행은 연초록,
// 재료비/노무비/경비/기타/변동판관비 계/고정판관비 계 등 중간 소계 행은 연노랑으로
// 강조 표시한다.
const GREEN_HIGHLIGHT_KEYS = new Set(["quantity", "sales_final", "cogs_final", "sga_final", "operating_profit_final"]);
const YELLOW_HIGHLIGHT_KEYS = new Set([
  "material_total",
  "labor_total",
  "expense_total",
  "other_cogs",
  "sga_variable",
  "sga_fixed",
]);

const HEADER_CELL = "border border-white/25 bg-[var(--sebang-green-700)] px-2 py-1.5 text-center text-[11px] font-semibold text-white";

function labelClass(key: string): string {
  const indent = LINE_ITEM_INDENT[key] ?? 0;
  const weight = indent === 0 ? "font-semibold" : indent === 1 ? "font-medium" : "font-normal";
  const pad = indent === 0 ? "pl-2" : indent === 1 ? "pl-5" : "pl-8";
  return `${pad} ${weight}`;
}

function rowClass(key: string): string {
  if (GREEN_HIGHLIGHT_KEYS.has(key)) return "bg-[var(--green-50)]";
  // design.md의 SEBANG 팔레트에는 노랑 토큰이 없다 — 이 표에서 소계 행만 구분하기
  // 위한 연노랑을 이 컴포넌트 전용으로 별도 지정한다(사용자 확인, green-50과
  // 밝기를 맞춘 톤). Tailwind가 정적으로 인식해야 하므로 클래스 리터럴로 둔다.
  if (YELLOW_HIGHLIGHT_KEYS.has(key)) return "bg-[#fdf6d8]";
  return "";
}

function formatNum(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return Math.round(value).toLocaleString("ko-KR");
}

function formatRatio(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value.toFixed(1)}%`;
}

function DiffCell({ value, isRate }: { value: number | null; isRate?: boolean }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <td className="px-2 py-1.5 text-right text-[var(--color-text-secondary)]">-</td>;
  }
  const tone = changeTone(value);
  const text = isRate ? formatPercent(value * 100) : formatNum(value);
  return (
    <td
      className={`px-2 py-1.5 text-right ${
        tone === "up" ? "text-[var(--color-success)]" : tone === "down" ? "text-[var(--color-danger)]" : ""
      }`}
    >
      {text}
    </td>
  );
}

export function PLComparisonPanel({ batchId }: PLComparisonPanelProps) {
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [filterOptions, setFilterOptions] = useState<PLComparisonFilterOptions | null>(null);
  const [lines, setLines] = useState<PLComparisonLine[] | null>(null);
  const [planComparisonAvailable, setPlanComparisonAvailable] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 배치가 바뀔 때 필터를 초기화하는 건 호출부(overview/page.tsx)가 key={batchId}로
  // 컴포넌트를 통째로 다시 마운트해서 처리한다(react-hooks/set-state-in-effect 대응) —
  // 여기서는 그 배치에 실제로 존재하는 값으로 드롭다운만 채운다.
  useEffect(() => {
    let cancelled = false;
    getPlComparisonFilterOptions(batchId)
      .then((data) => {
        if (!cancelled) setFilterOptions(data);
      })
      .catch(() => {
        if (!cancelled) setFilterOptions(null);
      });
    return () => {
      cancelled = true;
    };
  }, [batchId]);

  useEffect(() => {
    let cancelled = false;
    getPlComparison(batchId, {
      team: filters.team.length ? filters.team : undefined,
      customer: filters.customer.length ? filters.customer : undefined,
      product_code: filters.product_code.length ? filters.product_code : undefined,
      desc: filters.desc.length ? filters.desc : undefined,
      product_group_1: filters.product_group_1.length ? filters.product_group_1 : undefined,
      product_group_2: filters.product_group_2.length ? filters.product_group_2 : undefined,
      product_group_3: filters.product_group_3.length ? filters.product_group_3 : undefined,
    })
      .then((data) => {
        if (cancelled) return;
        setLines(data.lines);
        setPlanComparisonAvailable(data.plan_comparison_available);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "손익 상세를 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [batchId, filters]);

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] p-5">
      <h2 className="mb-1 text-base font-bold">손익 상세 분석 (계획 대비 · 전월 대비)</h2>
      <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
        팀·고객·상품·제품구분으로 드릴다운해서 계정과목별 계획 대비·전월 대비를 확인합니다. 계획(손익계산서)은
        팀 기준으로만 비교됩니다 — 고객·상품 필터는 실적에만 적용됩니다.
      </p>

      <div className="mb-4 flex flex-wrap gap-2">
        {FILTER_FIELDS.map(({ key, label, optionsKey }) => (
          <MultiSelectDropdown
            key={key}
            label={label}
            options={filterOptions?.[optionsKey] ?? []}
            selected={filters[key]}
            onChange={(values) => setFilters((prev) => ({ ...prev, [key]: values }))}
          />
        ))}
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-4 py-3 text-sm text-[var(--color-danger)]">
          {error}
        </div>
      )}

      {lines && (
        <div className="space-y-5">
          <div>
            <h3 className="mb-2 text-sm font-bold">① 계획 대비</h3>
            {!planComparisonAvailable && (
              <p className="mb-2 rounded-md border border-[#F7AD99] bg-[var(--orange-50)] px-3 py-2 text-xs text-[var(--color-danger)]">
                고객·상품·DESC·제품구분 필터가 걸려 있어 계획대비(단위당/총액/증감율)는 비교
                불가입니다 — 계획은 팀×월 단위로만 존재해 이 필터들을 적용할 수 없습니다. 팀
                필터만 남기면 다시 계산됩니다.
              </p>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm">
                <thead>
                  <tr>
                    <th className={HEADER_CELL} rowSpan={2}>
                      구분
                    </th>
                    <th className={HEADER_CELL} colSpan={3}>
                      계획
                    </th>
                    <th className={HEADER_CELL} colSpan={3}>
                      실적
                    </th>
                    <th className={HEADER_CELL} colSpan={3}>
                      계획 대비
                    </th>
                  </tr>
                  <tr>
                    <th className={HEADER_CELL}>단위당</th>
                    <th className={HEADER_CELL}>총액</th>
                    <th className={HEADER_CELL}>비중</th>
                    <th className={HEADER_CELL}>단위당</th>
                    <th className={HEADER_CELL}>총액</th>
                    <th className={HEADER_CELL}>비중</th>
                    <th className={HEADER_CELL}>단위당</th>
                    <th className={HEADER_CELL}>총액</th>
                    <th className={HEADER_CELL}>증감율</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <tr key={line.key} className={`border-b border-[var(--light-gray-200)] last:border-0 ${rowClass(line.key)}`}>
                      <td className={`py-1.5 ${labelClass(line.key)}`}>{line.label}</td>
                      <td className="px-2 py-1.5 text-right">{formatNum(line.plan_unit)}</td>
                      <td className="px-2 py-1.5 text-right">{formatNum(line.plan_total)}</td>
                      <td className="px-2 py-1.5 text-right">{formatRatio(line.plan_ratio)}</td>
                      <td className="px-2 py-1.5 text-right">{formatNum(line.actual_unit)}</td>
                      <td className="px-2 py-1.5 text-right">{formatNum(line.actual_total)}</td>
                      <td className="px-2 py-1.5 text-right">{formatRatio(line.actual_ratio)}</td>
                      <DiffCell value={line.diff_unit} />
                      <DiffCell value={line.diff_total} />
                      <DiffCell value={line.change_rate} isRate />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-bold">② 전월 대비</h3>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm">
                <thead>
                  <tr>
                    <th className={HEADER_CELL} rowSpan={2}>
                      구분
                    </th>
                    <th className={HEADER_CELL} colSpan={3}>
                      당월
                    </th>
                    <th className={HEADER_CELL} colSpan={3}>
                      전월
                    </th>
                    <th className={HEADER_CELL} colSpan={3}>
                      전월 대비
                    </th>
                  </tr>
                  <tr>
                    <th className={HEADER_CELL}>단위당</th>
                    <th className={HEADER_CELL}>총액</th>
                    <th className={HEADER_CELL}>비중</th>
                    <th className={HEADER_CELL}>단위당</th>
                    <th className={HEADER_CELL}>총액</th>
                    <th className={HEADER_CELL}>비중</th>
                    <th className={HEADER_CELL}>단위당</th>
                    <th className={HEADER_CELL}>총액</th>
                    <th className={HEADER_CELL}>증감율</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <tr key={line.key} className={`border-b border-[var(--light-gray-200)] last:border-0 ${rowClass(line.key)}`}>
                      <td className={`py-1.5 ${labelClass(line.key)}`}>{line.label}</td>
                      <td className="px-2 py-1.5 text-right">{formatNum(line.actual_unit)}</td>
                      <td className="px-2 py-1.5 text-right">{formatNum(line.actual_total)}</td>
                      <td className="px-2 py-1.5 text-right">{formatRatio(line.actual_ratio)}</td>
                      <td className="px-2 py-1.5 text-right">{formatNum(line.prev_month_unit)}</td>
                      <td className="px-2 py-1.5 text-right">{formatNum(line.prev_month_total)}</td>
                      <td className="px-2 py-1.5 text-right">{formatRatio(line.prev_month_ratio)}</td>
                      <DiffCell value={line.diff_prev_month_unit} />
                      <DiffCell value={line.diff_prev_month_total} />
                      <DiffCell value={line.change_rate_prev_month} isRate />
                    </tr>
                  ))}
                  {lines.every((l) => !l.prev_month_available) && (
                    <tr>
                      <td colSpan={10} className="px-2 py-2 text-center text-xs text-[var(--color-text-secondary)]">
                        전월 배치가 없어 전월 대비를 계산할 수 없습니다.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
