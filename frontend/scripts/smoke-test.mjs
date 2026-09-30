// Day 3 수동 통합 스모크 테스트: 브라우저의 fetch(FormData)와 동일한 인코딩 경로로
// 실제 백엔드(:8000)에 3개월치 데이터를 업로드하고, F4/F5 조회 API까지 확인한다.
// curl은 Windows 콘솔 코드페이지(CP949) 문제로 한글 폼 필드가 깨지므로 사용하지 않는다.
import { readFile } from "node:fs/promises";
import path from "node:path";

const API_BASE = "http://127.0.0.1:8000";
const FIXTURES = path.resolve("../backend/tests/fixtures");

async function upload(entries) {
  const form = new FormData();
  for (const [name, fileType] of entries) {
    const buf = await readFile(path.join(FIXTURES, name));
    form.append("files", new Blob([buf], { type: "text/csv" }), name);
    form.append("file_types", fileType);
  }
  const res = await fetch(`${API_BASE}/uploads`, { method: "POST", body: form });
  const body = await res.json();
  if (!res.ok) throw new Error(`upload 실패: ${JSON.stringify(body)}`);
  return body;
}

console.log("1) 2025-07 + 매핑표 업로드");
await upload([
  ["actual_prev_year.csv", "실적"],
  ["mapping_sample.csv", "매핑표"],
]);

console.log("2) 2026-06 업로드 (매핑표 재사용)");
await upload([["actual_prev_month.csv", "실적"]]);

console.log("3) 2026-07 + 계획 업로드");
const r3 = await upload([
  ["actual_sample.csv", "실적"],
  ["plan_sample.csv", "계획"],
]);
console.log("   ->", JSON.stringify(r3));

const batchId = r3.batch_id;

const overview = await (await fetch(`${API_BASE}/batches/${batchId}/overview`)).json();
console.log("4) overview teams:", overview.teams.map((t) => `${t.team}:${t.actual_amount}`).join(", "));

const anomalies = await (await fetch(`${API_BASE}/batches/${batchId}/anomalies`)).json();
console.log("5) anomalies:", anomalies.anomalies.map((a) => `${a.team}/${a.metric_type}`).join(", "));

const trend = await (await fetch(`${API_BASE}/batches/${batchId}/trend?team=차량대리점`)).json();
console.log(
  "6) 차량대리점 trend:",
  trend.months.map((m) => `${m.month}월=${m.actual_amount ?? "-"}`).join(", "),
);

const thresholdsBefore = await (await fetch(`${API_BASE}/thresholds`)).json();
console.log("7) thresholds:", thresholdsBefore.thresholds.map((t) => t.metric_type).join(", "));

console.log("\n✅ 스모크 테스트 통과: 업로드 -> Overview -> 이상징후 -> 추이 -> 임계치 전체 연동 확인");
