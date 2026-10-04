// 앱을 실제로 조작하는 장면을 녹화한다 (Phase 27). 장면마다 나레이션 길이에 맞춰 진행하고 시작 시각을 timeline.json에 남긴다.
// 사용법: node record.mjs --out <폴더> --audio <wav 폴더> --live <8월 실적 파일> [--base http://localhost:3100]
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const argv = Object.fromEntries(
  process.argv.slice(2).reduce((acc, cur, i, arr) => (cur.startsWith("--") ? [...acc, [cur.slice(2), arr[i + 1]]] : acc), []),
);
const OUT = argv.out;
const AUDIO = argv.audio;
const LIVE_FILE = argv.live;
const BASE = argv.base ?? "http://localhost:3100";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const narration = JSON.parse(fs.readFileSync(path.join(HERE, "narration.json"), "utf8"));
const PAD_MS = 400;

function wavSeconds(file) {
  const buf = fs.readFileSync(file);
  const rate = buf.readUInt32LE(24);
  const bits = buf.readUInt16LE(34);
  const channels = buf.readUInt16LE(22);
  let pos = 12;
  while (pos < buf.length - 8) {
    const id = buf.toString("ascii", pos, pos + 4);
    const size = buf.readUInt32LE(pos + 4);
    if (id === "data") return Math.min(size, buf.length - pos - 8) / (rate * channels * (bits / 8));
    pos += 8 + size;
  }
  throw new Error(`data chunk not found: ${file}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 화면에 주입하는 오버레이(커서·클릭 표시·자막·카드) ─────────────────────────
const CARD_STYLE = `
  position:fixed;inset:0;z-index:2147483645;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:28px;
  color:#fff;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;text-align:center;
  background-color:#242c32;
  background-image:linear-gradient(rgba(255,255,255,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.045) 1px,transparent 1px),linear-gradient(135deg,#242c32,#333f48);
  background-size:40px 40px,40px 40px,100% 100%;`;

const titleCard = `
  <div style="position:absolute;inset:0 auto 0 0;width:10px;background:#eb3300"></div>
  <img src="/rocket-emblem.png" style="width:120px;height:120px;border-radius:50%;box-shadow:0 4px 24px rgba(0,0,0,.4)">
  <div style="font-size:52px;font-weight:800;line-height:1.3;letter-spacing:-1px">영업실적·손익 분석 및<br>보고서 자동 생성 <span style="color:#eb3300">Agent</span></div>
  <div style="font-size:24px;color:#66c1cb;font-weight:700;letter-spacing:2px">AX전문가과정 · 과제개발결과 발표</div>
  <div style="font-size:26px;color:#d6d9da">국내영업본부 국내영업기획팀 김영우 책임</div>`;

const asIsToBeCard = `
  <div style="position:absolute;inset:0 auto 0 0;width:10px;background:#eb3300"></div>
  <div style="font-size:40px;font-weight:800">매월 반복되는 실적 분석, 이렇게 바뀝니다</div>
  <div style="display:flex;align-items:stretch;gap:36px">
    <div style="width:430px;padding:30px 34px;border-radius:18px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.18);text-align:left">
      <div style="font-size:22px;font-weight:700;color:#adb2b6;letter-spacing:2px">AS-IS · 엑셀 수작업</div>
      <div style="font-size:64px;font-weight:800;margin:10px 0 14px;color:#f7ad99">월 12시간</div>
      <div style="font-size:23px;line-height:1.9;color:#d6d9da">SAP 데이터 가공·집계·보고서 수기 작성<br>수기 오류 월 1~3건<br>이상징후는 익월에야 발견</div>
    </div>
    <div style="align-self:center;font-size:56px;color:#eb3300;font-weight:800">→</div>
    <div style="width:430px;padding:30px 34px;border-radius:18px;background:rgba(0,151,169,.18);border:1px solid #33acba;text-align:left">
      <div style="font-size:22px;font-weight:700;color:#66c1cb;letter-spacing:2px">TO-BE · 업로드 한 번</div>
      <div style="font-size:64px;font-weight:800;margin:10px 0 14px;color:#fff">1~2시간</div>
      <div style="font-size:23px;line-height:1.9;color:#e8f6f8">자동 정제·집계·이상징후 판정<br>수기 오류 0건<br>업로드 당일·익일 발견</div>
    </div>
  </div>`;

const outroCard = `
  <div style="position:absolute;inset:0 auto 0 0;width:10px;background:#eb3300"></div>
  <img src="/rocket-emblem.png" style="width:96px;height:96px;border-radius:50%">
  <div style="font-size:44px;font-weight:800;line-height:1.35">업로드 한 번으로<br>집계 → 이상징후 → 보고서 초안까지</div>
  <div style="display:flex;gap:22px">
    <div style="padding:18px 30px;border-radius:14px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);font-size:24px">집계·분석 <b style="color:#66c1cb">12시간 → 1~2시간</b></div>
    <div style="padding:18px 30px;border-radius:14px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);font-size:24px">이상징후 발견 <b style="color:#66c1cb">익월 → 당일</b></div>
    <div style="padding:18px 30px;border-radius:14px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);font-size:24px">판단 기준 <b style="color:#66c1cb">조정 가능 7종</b></div>
  </div>
  <div style="font-size:22px;color:#adb2b6">데모 주소(가상 데이터) · sales-performance-report-agent.vercel.app</div>
  <div style="font-size:30px;font-weight:700;color:#d6d9da">감사합니다</div>`;

const OVERLAY_INIT = `(() => {
  if (window.__demoInit) return; window.__demoInit = true;
  const START_CARD = ${JSON.stringify(titleCard)};
  const CARD_STYLE = ${JSON.stringify(CARD_STYLE)};
  const setup = () => {
    const root = document.documentElement;
    const css = document.createElement('style');
    css.textContent = \`
      #__cur{position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:30px;height:30px;will-change:transform;display:none}
      .__rip{position:fixed;z-index:2147483646;pointer-events:none;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;border:3px solid #eb3300;animation:__rip .6s ease-out forwards}
      @keyframes __rip{from{transform:scale(.4);opacity:.95}to{transform:scale(4.2);opacity:0}}
      #__cap{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:2147483644;width:max-content;max-width:1100px;padding:12px 28px;border-radius:12px;
        background:rgba(36,44,50,.94);color:#fff;font:700 23px/1.45 'Malgun Gothic',sans-serif;text-align:center;border-left:7px solid #eb3300;
        box-shadow:0 6px 24px rgba(0,0,0,.35);display:none}\`;
    root.appendChild(css);
    const cur = document.createElement('div'); cur.id = '__cur';
    cur.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#fff" stroke="#242c32" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    root.appendChild(cur);
    const cap = document.createElement('div'); cap.id = '__cap'; root.appendChild(cap);
    const card = document.createElement('div'); card.id = '__card'; card.style.cssText = CARD_STYLE + 'display:none;transition:opacity .5s';
    root.appendChild(card);
    window.addEventListener('mousemove', (e) => { cur.style.display = 'block'; cur.style.transform = 'translate(' + e.clientX + 'px,' + e.clientY + 'px)'; }, true);
    window.addEventListener('mousedown', (e) => {
      const r = document.createElement('div'); r.className = '__rip'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
      root.appendChild(r); setTimeout(() => r.remove(), 700);
    }, true);
    window.__setCaption = (t) => { sessionStorage.setItem('__cap', t || ''); cap.textContent = t || ''; cap.style.display = t ? 'block' : 'none'; };
    window.__showCard = (html) => { sessionStorage.setItem('__card', html); card.innerHTML = html; card.style.opacity = '1'; card.style.display = 'flex'; };
    window.__hideCard = () => { sessionStorage.setItem('__card', ''); card.style.opacity = '0'; setTimeout(() => { card.style.display = 'none'; }, 520); };
    if (sessionStorage.getItem('__card') === null) sessionStorage.setItem('__card', START_CARD);
    const savedCard = sessionStorage.getItem('__card'); if (savedCard) window.__showCard(savedCard);
    const savedCap = sessionStorage.getItem('__cap'); if (savedCap) window.__setCaption(savedCap);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup); else setup();
})();`;

// ── 녹화 ───────────────────────────────────────────────────────────────────
fs.mkdirSync(OUT, { recursive: true });
const videoDir = path.join(OUT, "video-raw");
fs.rmSync(videoDir, { recursive: true, force: true });

const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
  recordVideo: { dir: videoDir, size: { width: 1280, height: 720 } },
});
await context.addInitScript(OVERLAY_INIT);
const page = await context.newPage();
const t0 = Date.now();
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));

let mouse = { x: 640, y: 360 };
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
async function glide(x, y, ms = 520) {
  const steps = Math.max(8, Math.round(ms / 16));
  const from = { ...mouse };
  for (let i = 1; i <= steps; i++) {
    const k = ease(i / steps);
    await page.mouse.move(from.x + (x - from.x) * k, from.y + (y - from.y) * k);
    await sleep(ms / steps);
  }
  mouse = { x, y };
}
async function point(locator, { dx = 0, dy = 0 } = {}) {
  await locator.scrollIntoViewIfNeeded();
  await sleep(150);
  const box = await locator.boundingBox();
  await glide(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy);
}
async function click(locator, opts) {
  await point(locator, opts);
  await sleep(200);
  await page.mouse.click(mouse.x, mouse.y);
  await sleep(150);
}
async function scrollTo(y, ms = 1100) {
  await page.evaluate((top) => window.scrollTo({ top, behavior: "smooth" }), y);
  await sleep(ms);
}
async function scrollToLocator(locator, offset = 90, ms = 1100) {
  const top = await locator.evaluate((el, off) => el.getBoundingClientRect().top + window.scrollY - off, offset);
  await scrollTo(Math.max(0, top), ms);
}

const timeline = { scenes: [] };
async function scene(i, body, { caption = true } = {}) {
  const s = narration.scenes[i];
  const dur = wavSeconds(path.join(AUDIO, `${s.id}.wav`)) * 1000;
  const start = Date.now();
  timeline.scenes.push({ id: s.id, startMs: start - t0, audioMs: dur });
  await page.evaluate((t) => window.__setCaption(t), caption ? s.caption : "");
  await body();
  const remain = start + dur + PAD_MS - Date.now();
  if (remain > 0) await sleep(remain);
  else console.log(`  (경고) ${s.id} 동작이 나레이션보다 ${(-remain / 1000).toFixed(1)}초 길었음`);
  console.log(`${s.id} ${s.title}: ${((Date.now() - start) / 1000).toFixed(1)}초 (음성 ${(dur / 1000).toFixed(1)}초)`);
}

await page.goto(`${BASE}/upload`, { waitUntil: "networkidle" });
await page.locator("#__card").waitFor({ state: "visible" });

// s0 제목 카드
await scene(0, async () => {}, { caption: false });
// s1 As-Is → To-Be 카드
await scene(1, async () => {
  await page.evaluate((html) => window.__showCard(html), asIsToBeCard);
}, { caption: false });
await page.evaluate(() => window.__hideCard());
await sleep(600);

// s2 파일 업로드 — 결과 카드를 나레이션 후반부에 충분히 보여주려고 앞 동작을 빠르게 진행한다
await scene(2, async () => {
  await sleep(300);
  const fileInput = page.locator('input[type="file"]').first();
  await point(fileInput, { dx: -200 });
  await sleep(300);
  await fileInput.setInputFiles(LIVE_FILE);
  await sleep(700);
  await click(page.getByRole("button", { name: /업로드 및 정제/ }));
  await page.getByText(/업로드 결과/).first().waitFor({ timeout: 60000 });
  await sleep(400);
  await scrollTo(10000, 900);
});

// s3 Overview
await scene(3, async () => {
  await click(page.getByRole("link", { name: /F4 Overview/ }));
  await page.getByText("팀별 목표 대비 실적 — 수량·매출액").waitFor({ timeout: 60000 });
  await sleep(1800);
  await scrollToLocator(page.getByText("팀별 목표 대비 실적 — 수량·매출액"), 20, 1100);
  await sleep(700);
  await click(page.locator("table tbody tr", { hasText: "고정형" }).first());
  await page.getByText(/고정형 — 월별 실적 추이/).waitFor({ timeout: 30000 });
  await sleep(400);
  await scrollToLocator(page.getByText(/고정형 — 월별 실적 추이/), 20, 1100);
});

// s4 상세 분석 탭
await scene(4, async () => {
  const tab = (name) => page.getByRole("button", { name }).first();
  await scrollToLocator(tab(/월별 실적 분석\(팀별\)/), 70, 800);
  await click(tab(/월별 실적 분석\(제품군별\)/));
  await sleep(900);
  await click(tab(/월별 실적 분석\(거래처별\)/));
  await sleep(900);
  await click(tab(/손익 상세 분석/));
  await sleep(700);
});

// s5 이상징후
await scene(5, async () => {
  await scrollTo(0, 400);
  await click(page.getByRole("link", { name: /F5 이상징후/ }));
  await page.getByText("영향 금액").first().waitFor({ timeout: 60000 });
  await sleep(1500);
  await click(page.getByRole("button", { name: /^단가변동/ }).first());
  await sleep(1500);
  await click(page.getByRole("button", { name: /^고정형/ }).first());
  await sleep(700);
});

// s6 임계치 설정
await scene(6, async () => {
  await click(page.getByRole("link", { name: /F6 임계치/ }));
  await page.getByText("전월대비").first().waitFor({ timeout: 60000 });
  await sleep(500);
  await point(page.locator('input[type="number"]').first());
  await sleep(500);
  await point(page.locator('input[type="number"]').nth(2));
});

// s7 보고서 초안
await scene(7, async () => {
  await click(page.getByRole("link", { name: /F7 보고서/ }));
  await page.getByRole("button", { name: "초안 생성" }).waitFor({ timeout: 60000 });
  await click(page.getByRole("button", { name: "초안 생성" }));
  await page.getByText(/Re-arrange 전체 다운로드/).waitFor({ timeout: 90000 });
  await sleep(1000);
  await scrollTo(380, 1000);
  await sleep(500);
  const note = page.getByPlaceholder(/배경 설명/).first();
  await click(note);
  await page.keyboard.type("단가 조정 반영 시점 차이", { delay: 60 });
  await sleep(400);
  await scrollTo(0, 700);
  await point(page.getByRole("link", { name: /보고서 초안 엑셀 다운로드/ }));
});

// s8 마무리 카드
await page.evaluate(() => window.__setCaption(""));
await scene(8, async () => {
  await page.evaluate((html) => window.__showCard(html), outroCard);
}, { caption: false });

timeline.endMs = Date.now() - t0;
console.log("총 녹화 길이(초):", (timeline.endMs / 1000).toFixed(1));
const video = page.video();
await context.close();
const videoPath = await video.path();
await browser.close();
timeline.video = videoPath;
fs.writeFileSync(path.join(OUT, "timeline.json"), JSON.stringify(timeline, null, 2));
console.log("영상:", videoPath);
console.log("페이지 오류:", problems.length ? problems.join("\n") : "없음");
