import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  anomaliesExportUrl,
  createReportDraft,
  getOverview,
  getReportDraft,
  getThresholds,
  overviewExportUrl,
  reportExportUrl,
  updateReportItem,
  updateThresholds,
  uploadFiles,
} from "@/lib/api";

const originalFetch = global.fetch;

beforeEach(() => {
  global.fetch = vi.fn();
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

function mockJsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("getThresholds", () => {
  it("returns the thresholds array from the API response", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      mockJsonResponse(200, {
        thresholds: [{ metric_type: "전월대비", threshold_value: 10, threshold_low: null, threshold_high: null }],
      }),
    );

    const thresholds = await getThresholds();
    expect(thresholds).toHaveLength(1);
    expect(thresholds[0].metric_type).toBe("전월대비");
    expect(global.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/thresholds",
      undefined,
    );
  });

  it("throws an ApiError with the backend detail message on failure", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockJsonResponse(400, { detail: "알 수 없는 판단 기준입니다: 없는기준" }),
    );

    await expect(getThresholds()).rejects.toThrow(ApiError);
    await expect(getThresholds()).rejects.toThrow("알 수 없는 판단 기준입니다");
  });
});

describe("updateThresholds", () => {
  it("PUTs the updates as JSON and returns the updated thresholds", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      mockJsonResponse(200, {
        thresholds: [{ metric_type: "전월대비", threshold_value: 25, threshold_low: null, threshold_high: null }],
      }),
    );

    const result = await updateThresholds([{ metric_type: "전월대비", threshold_value: 25 }]);
    expect(result[0].threshold_value).toBe(25);

    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ updates: [{ metric_type: "전월대비", threshold_value: 25 }] });
  });
});

describe("getOverview", () => {
  it("requests the batch-specific overview endpoint", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      mockJsonResponse(200, { batch_id: "b1", year: 2026, month: 7, summary: {}, teams: [] }),
    );

    const overview = await getOverview("b1");
    expect(overview.batch_id).toBe("b1");
    expect(global.fetch).toHaveBeenCalledWith("http://127.0.0.1:8000/batches/b1/overview", undefined);
  });
});

describe("createReportDraft", () => {
  it("POSTs the batch_id as JSON and returns the created draft", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      mockJsonResponse(200, {
        draft_id: "d1",
        batch_id: "b1",
        created_at: "2026-07-01T00:00:00+00:00",
        status: "초안",
        items: [],
      }),
    );

    const draft = await createReportDraft("b1");
    expect(draft.draft_id).toBe("d1");

    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/reports");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ batch_id: "b1" });
  });
});

describe("getReportDraft", () => {
  it("requests the draft-specific endpoint", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      mockJsonResponse(200, {
        draft_id: "d1",
        batch_id: "b1",
        created_at: "2026-07-01T00:00:00+00:00",
        status: "초안",
        items: [],
      }),
    );

    const draft = await getReportDraft("d1");
    expect(draft.draft_id).toBe("d1");
    expect(global.fetch).toHaveBeenCalledWith("http://127.0.0.1:8000/reports/d1", undefined);
  });
});

describe("updateReportItem", () => {
  it("PATCHes the item-specific endpoint with only the given fields", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      mockJsonResponse(200, {
        draft_id: "d1",
        batch_id: "b1",
        created_at: "2026-07-01T00:00:00+00:00",
        status: "초안",
        items: [],
      }),
    );

    await updateReportItem("d1", "i1", { is_excluded: true });

    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/reports/d1/items/i1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ is_excluded: true });
  });
});

describe("export URL helpers", () => {
  it("build the correct download endpoint URLs", () => {
    expect(overviewExportUrl("b1")).toBe("http://127.0.0.1:8000/batches/b1/export/overview");
    expect(anomaliesExportUrl("b1")).toBe("http://127.0.0.1:8000/batches/b1/export/anomalies");
    expect(reportExportUrl("d1")).toBe("http://127.0.0.1:8000/reports/d1/export");
  });
});

describe("uploadFiles", () => {
  it("builds multipart form data with matching files/file_types order", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      mockJsonResponse(200, {
        batch_id: "b1",
        target_period: "2026-07",
        files: [],
        overwrote_existing_batch: false,
        total_rows: 1,
        unmapped_rows: 0,
        calc_error_rows: 0,
        aggregated_groups: 1,
        anomaly_count: 0,
        warning: null,
        requires_confirmation: false,
        batches: [],
        skipped_periods: [],
      }),
    );

    const file = new File(["a,b\n1,2"], "actual.csv", { type: "text/csv" });
    const result = await uploadFiles([{ file, fileType: "실적" }]);

    if (result.requires_confirmation) throw new Error("expected a committed result");
    expect(result.batch_id).toBe("b1");
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/uploads");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect(form.get("file_types")).toBe("실적");
    expect((form.get("files") as File).name).toBe("actual.csv");
  });
});
