import { describe, expect, it } from "vitest";

import { changeTone, formatEok, formatEokNumber, formatPercent, formatPlainPercent, formatQuantity } from "@/lib/format";

describe("formatEok", () => {
  it("converts won amounts to 억 with one decimal", () => {
    expect(formatEok(717_885_0000)).toBe("71.8억"); // PRD F4 목업과 동일한 표기 스타일
    expect(formatEok(0)).toBe("0.0억");
  });

  it("returns a dash for null/undefined", () => {
    expect(formatEok(null)).toBe("-");
    expect(formatEok(undefined)).toBe("-");
  });
});

describe("formatEokNumber", () => {
  it("converts won amounts to 억 without the 억 suffix (F4 팀별 목표 대비 실적 표 전용)", () => {
    expect(formatEokNumber(717_885_0000)).toBe("71.8");
    expect(formatEokNumber(0)).toBe("0.0");
  });

  it("returns a dash for null/undefined", () => {
    expect(formatEokNumber(null)).toBe("-");
    expect(formatEokNumber(undefined)).toBe("-");
  });
});

describe("formatPercent", () => {
  it("adds a + sign for positive values and keeps - for negative", () => {
    expect(formatPercent(19.6)).toBe("+19.6%");
    expect(formatPercent(-16.2)).toBe("-16.2%");
    expect(formatPercent(0)).toBe("0.0%");
  });

  it("returns a dash for missing values (비교 불가)", () => {
    expect(formatPercent(null)).toBe("-");
  });
});

describe("formatPlainPercent", () => {
  it("does not add a leading plus sign", () => {
    expect(formatPlainPercent(79.8)).toBe("79.8%");
  });
});

describe("formatQuantity", () => {
  it("rounds and adds thousands separators", () => {
    expect(formatQuantity(12400)).toBe("12,400");
  });

  it("returns a dash for missing values", () => {
    expect(formatQuantity(null)).toBe("-");
  });
});

describe("changeTone", () => {
  it("classifies positive/negative/neutral/missing values", () => {
    expect(changeTone(5)).toBe("up");
    expect(changeTone(-5)).toBe("down");
    expect(changeTone(0)).toBe("neutral");
    expect(changeTone(null)).toBe("neutral");
  });
});
