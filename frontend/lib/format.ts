/** F4/F5 화면에서 공통으로 쓰는 숫자 포맷 유틸리티. */

const EOK = 100_000_000; // 1억

export function formatEok(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "-";
  return `${formatEokNumber(amount)}억`;
}

// F4 팀별 목표 대비 실적 표(TeamMatrixTable) 전용 — 사용자 확인: 촘촘한 표에 셀마다
// "억"이 반복되면 글자가 밀려 보이므로, 숫자만 표시하고 단위는 표 제목 옆에 한 번만
// 표기한다(TeamMatrixTable의 "(단위: 억원)").
export function formatEokNumber(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "-";
  const eok = amount / EOK;
  const rounded = Math.round(eok * 10) / 10;
  return rounded.toLocaleString("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatPlainPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value.toFixed(digits)}%`;
}

export function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value).toLocaleString("ko-KR")}`;
}

// F4 "월별 실적 분석" 탭(Phase 14) — 백엔드가 이미 백만원 단위로 변환해 보내는 값을
// 그대로 표시한다(참고 이미지 단위 표기 "단위 : EA,백만원", 표 전체에 한 번만 적힘).
export function formatMillion(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function changeTone(value: number | null | undefined): "up" | "down" | "neutral" {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) return "neutral";
  return value > 0 ? "up" : "down";
}
