/**
 * FastAPI 백엔드(backend/) API 클라이언트.
 * 엔드포인트는 backend/app/routers/{uploads,thresholds,analytics,reports}.py 참고.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    let detail = `요청이 실패했습니다 (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body?.detail)) {
        detail = body.detail.map((d: { msg?: string }) => d.msg).join(", ");
      }
    } catch {
      // 응답 본문이 JSON이 아닌 경우 기본 메시지를 사용한다.
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

// ── F1. 업로드 ────────────────────────────────────────────────

export type UploadFileType = "실적" | "계획" | "손익계산서" | "매핑표";

export interface UploadBatchSummary {
  batch_id: string;
  target_period: string;
  overwrote_existing_batch: boolean;
  total_rows: number;
  unmapped_rows: number;
  calc_error_rows: number;
  aggregated_groups: number;
  anomaly_count: number;
}

// Phase 19(.docs/phase/phase_19_실적파일다중월분할업로드.md) — 실적 파일 하나에 여러
// 달 데이터가 섞여 있으면 백엔드가 달별로 자동 분할해 배치를 만든다. 기존 배치와
// 겹치는 달이 있으면 먼저 requires_confirmation=true 응답만 오고(batch_id 등은 없음),
// confirm_overwrite를 붙여 같은 파일로 재요청해야 실제로 커밋된다.
export interface UploadResult extends UploadBatchSummary {
  files: { file_name: string; file_type: string }[];
  warning: string | null;
  requires_confirmation: false;
  batches: UploadBatchSummary[];
  skipped_periods: string[];
}

export interface UploadRequiresConfirmation {
  requires_confirmation: true;
  conflicting_periods: string[];
  new_periods: string[];
  files: { file_name: string; file_type: string }[];
  warning: string | null;
}

export async function uploadFiles(
  entries: { file: File; fileType: UploadFileType }[],
  confirmOverwrite?: boolean,
): Promise<UploadResult | UploadRequiresConfirmation> {
  const form = new FormData();
  for (const { file, fileType } of entries) {
    form.append("files", file, file.name);
    form.append("file_types", fileType);
  }
  if (confirmOverwrite !== undefined) {
    form.append("confirm_overwrite", String(confirmOverwrite));
  }
  return request<UploadResult | UploadRequiresConfirmation>("/uploads", { method: "POST", body: form });
}

// ── F4/F5 조회 ────────────────────────────────────────────────

export interface BatchSummary {
  batch_id: string;
  year: number;
  month: number;
  upload_date: string;
}

export async function listBatches(): Promise<BatchSummary[]> {
  const { batches } = await request<{ batches: BatchSummary[] }>("/batches");
  return batches;
}

export interface TeamOverview {
  team: string;
  quantity: number;
  actual_amount: number;
  profit: number;
  profit_rate: number | null;
  sga_amount: number;
  plan_amount: number | null;
  achievement_rate: number | null;
  prev_month_available: boolean;
  prev_month_amount: number | null;
  prev_month_change_pct: number | null;
  prev_month_profit_change_pct: number | null;
  prev_year_month_available: boolean;
  prev_year_month_amount: number | null;
  prev_year_change_pct: number | null;
}

export interface CumulativeTeamOverview {
  team: string;
  quantity: number;
  actual_amount: number;
  profit: number;
  profit_rate: number | null;
  plan_amount: number | null;
  achievement_rate: number | null;
}

export interface CumulativeOverview {
  up_to_month: number;
  teams: CumulativeTeamOverview[];
  total: Omit<CumulativeTeamOverview, "team">;
}

// 팀별 목표·실적·대비 통합 매트릭스 (당월+누계, 수량·매출액·영업이익).
// 목표 수량·목표 영업이익은 손익계산서(team_pl_record) 업로드분("매출수량"·"영업이익(A)")
// 근거이며, 업로드되지 않았으면 null로 남는다(0으로 대체하지 않음). "산전팀"은 실적
// 데이터에 실존하는 팀이 아니라 고정형+모티브를 합산한 화면 표시용 그룹이다(PRD F4 ③
// 차량대리점/차량OE/산전 3그룹 체계, 사용자 확인).
export interface TeamMatrixPeriod {
  plan_quantity: number | null;
  actual_quantity: number;
  quantity_achievement_rate: number | null;
  plan_amount: number | null;
  actual_amount: number;
  amount_achievement_rate: number | null;
  plan_profit: number | null;
  actual_profit: number;
  plan_profit_rate: number | null;
  actual_profit_rate: number | null;
  profit_diff: number | null;
  profit_achievement_rate: number | null;
}

export interface TeamMatrixRow {
  team: string;
  is_synthetic: boolean;
  mtd: TeamMatrixPeriod;
  ytd: TeamMatrixPeriod;
}

export interface OverviewResponse {
  batch_id: string;
  year: number;
  month: number;
  summary: {
    total_quantity: number;
    total_actual_amount: number;
    total_profit: number;
    total_profit_rate: number | null;
    total_plan_amount: number | null;
    total_achievement_rate: number | null;
    prev_month_change_pct: number | null;
    prev_year_change_pct: number | null;
    prev_month_available: boolean;
    prev_month_total_amount: number | null;
    prev_month_total_profit: number | null;
    prev_month_total_profit_rate: number | null;
  };
  teams: TeamOverview[];
  cumulative: CumulativeOverview;
  team_matrix: TeamMatrixRow[];
}

export async function getOverview(batchId: string): Promise<OverviewResponse> {
  return request<OverviewResponse>(`/batches/${batchId}/overview`);
}

export interface TrendMonth {
  month: number;
  quantity: number | null;
  actual_amount: number | null;
  profit: number | null;
  sga_amount: number | null;
}

export interface TrendResponse {
  team: string;
  year: number;
  months: TrendMonth[];
}

export async function getTrend(batchId: string, team: string): Promise<TrendResponse> {
  return request<TrendResponse>(`/batches/${batchId}/trend?team=${encodeURIComponent(team)}`);
}

export interface AnomalyFlag {
  flag_id: string;
  team: string;
  product_group: string | null;
  metric_type: string;
  actual_value: number | null;
  threshold_value: number | null;
  impact_amount: number | null;
  is_confirmed_by_user: boolean;
  // 사용자 요청("전월 얼마에서 당월 얼마로 얼마 변동, 이렇게 표현하면 좋겠어") —
  // 유형별로 실제 비교한 두 원시 값(예: 전월대비는 전월/당월 매출액, 계획대비는
  // 팀 계획/팀 실적). backend/app/services/analytics.py의 _before_after_for_flag 참고.
  before_value: number | null;
  after_value: number | null;
  // "단가변동"에만 채워진다(Phase 20) — 폐지된 "누계평균대비"의 누계 비교(연초~직전월
  // 평균단가)를 단가변동 쪽에서 전월 비교와 함께 보여주기 위한 값.
  cumulative_before_value: number | null;
}

export async function getAnomalies(batchId: string): Promise<AnomalyFlag[]> {
  const { anomalies } = await request<{ anomalies: AnomalyFlag[] }>(`/batches/${batchId}/anomalies`);
  return anomalies;
}

// ── F4 확장. 계획/전월 대비 상세 드릴다운 (backend/app/services/pl_comparison.py) ──

export interface PLComparisonLine {
  key: string;
  label: string;
  plan_unit: number | null;
  plan_total: number;
  plan_ratio: number | null;
  actual_unit: number | null;
  actual_total: number;
  actual_ratio: number | null;
  diff_unit: number | null;
  diff_total: number | null;
  change_rate: number | null;
  prev_month_available: boolean;
  prev_month_unit: number | null;
  prev_month_total: number | null;
  prev_month_ratio: number | null;
  diff_prev_month_unit: number | null;
  diff_prev_month_total: number | null;
  change_rate_prev_month: number | null;
}

export interface PLComparisonResponse {
  batch_id: string;
  team: string;
  // Phase 18(.docs/phase/phase_18_손익항목계획대비판정.md) — 드릴다운 필터(고객/상품/
  // DESC/제품구분1~3)가 걸려 있으면 false. 계획(team_pl_record)은 팀×월 단위로만
  // 존재해 그 필터들을 적용할 수 없는데, 필터링된 실적만 팀 전체 계획과 비교하면
  // 왜곡된 값이 나오므로 이때는 각 라인의 diff_unit/diff_total/change_rate가 null로 온다.
  plan_comparison_available: boolean;
  lines: PLComparisonLine[];
}

// 각 필터는 다중 선택을 지원한다(사용자 확인) — 같은 파라미터를 여러 번 반복해
// (예: ?customer=A&customer=B) 값들을 OR로 묶어 전달한다.
export interface PLComparisonFilters {
  team?: string[];
  customer?: string[];
  product_code?: string[];
  desc?: string[];
  product_group_1?: string[];
  product_group_2?: string[];
  product_group_3?: string[];
}

export async function getPlComparison(
  batchId: string,
  filters: PLComparisonFilters = {},
): Promise<PLComparisonResponse> {
  const params = new URLSearchParams();
  for (const [key, values] of Object.entries(filters)) {
    for (const value of values ?? []) {
      params.append(key, value);
    }
  }
  const query = params.toString();
  return request<PLComparisonResponse>(`/batches/${batchId}/pl-comparison${query ? `?${query}` : ""}`);
}

export interface PLComparisonFilterOptions {
  teams: string[];
  customer: string[];
  product_code: string[];
  desc: string[];
  product_group_1: string[];
  product_group_2: string[];
  product_group_3: string[];
}

export async function getPlComparisonFilterOptions(batchId: string): Promise<PLComparisonFilterOptions> {
  return request<PLComparisonFilterOptions>(`/batches/${batchId}/pl-comparison/filters`);
}

// ── F4 확장(Phase 14). 월별 실적 분석 탭 3종 — 계획 대비가 아니라 순수 실적 집계
// (backend/app/services/monthly_analysis.py). 금액류는 이미 백만원 단위로 변환돼 온다.

export interface MonthlyMetrics {
  quantity: number;
  actual_amount: number;
  profit: number;
  profit_rate: number | null;
  sga_amount: number;
  sga_rate: number | null;
  mfg_cost: number;
  mfg_cost_rate: number | null;
  standard_cogs: number;
  avg_unit_price: number | null;
}

export interface MonthlyMetricsPeriod {
  mtd: MonthlyMetrics;
  ytd: MonthlyMetrics;
}

// 팀별 탭은 당월|누계 2단 비교가 아니라, 참고 이미지 형식대로 팀마다 1~12월 행을
// 나열하고 그 아래 "팀 요약"(연간 합계) 행을 붙인다(사용자 확인).
export interface TeamMonthlyAnalysisMonth {
  month: number;
  metrics: MonthlyMetrics | null; // 해당 달에 업로드된 배치가 없으면 null
}

export interface TeamMonthlyAnalysisRow {
  team: string;
  months: TeamMonthlyAnalysisMonth[];
  summary: MonthlyMetrics;
}

export interface TeamMonthlyAnalysisResponse {
  year: number;
  teams: TeamMonthlyAnalysisRow[];
  total: MonthlyMetrics;
}

export async function getTeamMonthlyAnalysis(batchId: string): Promise<TeamMonthlyAnalysisResponse> {
  return request<TeamMonthlyAnalysisResponse>(`/batches/${batchId}/monthly-analysis/team`);
}

export interface ProductGroupMonthlyRow extends MonthlyMetricsPeriod {
  product_group_2: string | null;
}

export interface ProductGroupMonthlyGroup {
  team: string;
  rows: ProductGroupMonthlyRow[];
  subtotal: MonthlyMetricsPeriod;
}

export interface ProductGroupMonthlyAnalysisResponse {
  year: number;
  month: number;
  groups: ProductGroupMonthlyGroup[];
  total: MonthlyMetricsPeriod;
}

export async function getProductGroupMonthlyAnalysis(
  batchId: string,
  filters: { team?: string[] } = {},
): Promise<ProductGroupMonthlyAnalysisResponse> {
  const params = new URLSearchParams();
  for (const team of filters.team ?? []) params.append("team", team);
  const query = params.toString();
  return request<ProductGroupMonthlyAnalysisResponse>(
    `/batches/${batchId}/monthly-analysis/product-group${query ? `?${query}` : ""}`,
  );
}

export interface CustomerMonthlyRow extends MonthlyMetricsPeriod {
  customer: string | null;
}

export interface CustomerMonthlyGroup {
  team: string;
  rows: CustomerMonthlyRow[];
  subtotal: MonthlyMetricsPeriod;
}

export interface CustomerMonthlyAnalysisResponse {
  year: number;
  month: number;
  groups: CustomerMonthlyGroup[];
  total: MonthlyMetricsPeriod;
}

export async function getCustomerMonthlyAnalysis(
  batchId: string,
  filters: { team?: string[]; part?: string[] } = {},
): Promise<CustomerMonthlyAnalysisResponse> {
  const params = new URLSearchParams();
  for (const team of filters.team ?? []) params.append("team", team);
  for (const part of filters.part ?? []) params.append("part", part);
  const query = params.toString();
  return request<CustomerMonthlyAnalysisResponse>(
    `/batches/${batchId}/monthly-analysis/customer${query ? `?${query}` : ""}`,
  );
}

// 제품군별/거래처별 탭 공용 드릴다운 필터 옵션(팀·파트) — 이 배치에 실제로 존재하는 값만.
export interface MonthlyAnalysisFilterOptions {
  teams: string[];
  parts: string[];
}

export async function getMonthlyAnalysisFilterOptions(batchId: string): Promise<MonthlyAnalysisFilterOptions> {
  return request<MonthlyAnalysisFilterOptions>(`/batches/${batchId}/monthly-analysis/filters`);
}

// ── F6. 임계치 설정 ────────────────────────────────────────────

export interface ThresholdItem {
  metric_type: string;
  threshold_value: number | null;
  threshold_low: number | null;
  threshold_high: number | null;
}

export async function getThresholds(): Promise<ThresholdItem[]> {
  const { thresholds } = await request<{ thresholds: ThresholdItem[] }>("/thresholds");
  return thresholds;
}

export async function updateThresholds(updates: Partial<ThresholdItem>[]): Promise<ThresholdItem[]> {
  const { thresholds } = await request<{ thresholds: ThresholdItem[] }>("/thresholds", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  });
  return thresholds;
}

export async function recomputeBatch(
  batchId: string,
): Promise<{ batch_id: string; aggregated_groups: number; anomaly_count: number }> {
  return request(`/batches/${batchId}/recompute`, { method: "POST" });
}

// ── F7. 보고서 초안 ────────────────────────────────────────────

export interface ReportItem {
  item_id: string;
  flag_id: string | null;
  auto_comment: string;
  user_comment: string | null;
  chart_ref: string;
  is_excluded: boolean;
  background_note: string | null;
  team: string;
  product_group: string | null;
  metric_type: string;
  actual_value: number | null;
  impact_amount: number | null;
}

export interface ReportDraft {
  draft_id: string;
  batch_id: string;
  created_at: string;
  status: string;
  items: ReportItem[];
}

export async function createReportDraft(batchId: string): Promise<ReportDraft> {
  return request<ReportDraft>("/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ batch_id: batchId }),
  });
}

export async function getReportDraft(draftId: string): Promise<ReportDraft> {
  return request<ReportDraft>(`/reports/${draftId}`);
}

// ── F8. 보고서 초안 검토·수정 ──────────────────────────────────

export interface UpdateReportItemInput {
  user_comment?: string | null;
  background_note?: string | null;
  is_excluded?: boolean;
}

export async function updateReportItem(
  draftId: string,
  itemId: string,
  updates: UpdateReportItemInput,
): Promise<ReportDraft> {
  return request<ReportDraft>(`/reports/${draftId}/items/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

// ── F9. 결과 다운로드 ──────────────────────────────────────────

// Phase 15 — 카테고리 체크박스로 선택한 섹션만 PDF에 담는다(사용자 요청). 생략하면
// 백엔드가 전체 섹션을 포함한다.
export const OVERVIEW_PDF_SECTIONS = [
  { key: "team_matrix", label: "팀별 목표 대비 실적" },
  { key: "monthly_team", label: "월별 실적 분석(팀별)" },
  { key: "monthly_product_group", label: "월별 실적 분석(제품군별)" },
  { key: "monthly_customer", label: "월별 실적 분석(거래처별)" },
  { key: "pl_comparison", label: "손익 상세 분석" },
] as const;

export function overviewExportUrl(batchId: string, sections?: string[]): string {
  const base = `${API_BASE_URL}/batches/${batchId}/export/overview`;
  if (!sections || sections.length === 0) return base;
  const params = new URLSearchParams();
  for (const s of sections) params.append("sections", s);
  return `${base}?${params.toString()}`;
}

export function anomaliesExportUrl(batchId: string): string {
  return `${API_BASE_URL}/batches/${batchId}/export/anomalies`;
}

export function reportExportUrl(draftId: string): string {
  return `${API_BASE_URL}/reports/${draftId}/export`;
}

// F7 신규 다운로드 버튼(Phase 15) — raw+매핑을 거쳐 정제된 실적 Re-arrange용 수식
// 시트 전체를 xlsx로 받는다(draft_id가 가리키는 배치 기준).
export function reportRefinedExportUrl(draftId: string): string {
  return `${API_BASE_URL}/reports/${draftId}/export/refined`;
}
