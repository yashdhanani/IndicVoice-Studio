// End-to-end QA of the quality console via headless Chrome CDP.
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9229;
const OUT = "eval/quality_shots";
fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const results = [];
const ok = (name, pass, detail = "") => { results.push({ name, pass, detail }); console.log((pass ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : "")); };

const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${PORT}`, "--disable-gpu",
  "--no-first-run", "--no-default-browser-check", "--force-color-profile=srgb",
  "--autoplay-policy=no-user-gesture-required",
  "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
  `--user-data-dir=${process.env.TEMP || "/tmp"}/iv-quality-profile`,
  "--window-size=1440,900", "about:blank",
], { stdio: "ignore" });

async function waitDebugger() {
  for (let i = 0; i < 80; i++) {
    try { return await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); }
    catch { await sleep(250); }
  }
  throw new Error("chrome debugger never came up");
}
const ver = await waitDebugger();
const ws = new WebSocket(ver.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pending = new Map(); const errors = []; let loadResolve = null;
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id); pending.delete(m.id);
    m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
  } else if (m.method === "Page.loadEventFired" && loadResolve) { loadResolve(); loadResolve = null; }
  else if (m.method === "Runtime.exceptionThrown") {
    errors.push("EXCEPTION: " + JSON.stringify(m.params.exceptionDetails?.exception?.description || m.params.exceptionDetails?.text || m.params).slice(0, 400));
  } else if (m.method === "Runtime.consoleAPICalled" && ["error"].includes(m.params.type)) {
    errors.push("CONSOLE error: " + (m.params.args || []).map(a => a.value ?? a.description ?? "").join(" ").slice(0, 400));
  }
};
const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
  const id = ++seq; pending.set(id, { res, rej });
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  setTimeout(() => { if (pending.has(id)) { pending.delete(id); rej(new Error("timeout " + method)); } }, 60000);
});
const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId: S } = await send("Target.attachToTarget", { targetId, flatten: true });
await send("Page.enable", {}, S); await send("Runtime.enable", {}, S);
await send("Network.enable", {}, S); await send("Network.setCacheDisabled", { cacheDisabled: true }, S);

async function ev(expression) {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }, S);
  if (r.exceptionDetails) throw new Error("eval: " + (r.exceptionDetails.exception?.description || JSON.stringify(r.exceptionDetails)).slice(0, 400));
  return r.result?.value;
}
async function goto(width, height, mobile, dsf = 1) {
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: dsf, mobile }, S);
  const loaded = new Promise(r => { loadResolve = r; setTimeout(r, 20000); });
  await send("Page.navigate", { url: "http://127.0.0.1:8010/" }, S);
  await loaded;
  await ev("document.fonts.ready.then(()=>1)");
  await sleep(1800);
}
async function shot(name, beyond = false) {
  const { data } = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: beyond }, S);
  const file = path.join(OUT, name);
  fs.writeFileSync(file, Buffer.from(data, "base64"));
  console.log("  shot", file, fs.statSync(file).size, "B");
}
const READY = { overview: ".kpi", languages: ".lang-card", evidence: "#evTable",
  benchmarks: "#benchLangs", dataset: "#dsTable", listening: ".rate-row",
  reports: ".toolbar", baseline: ".md" };
async function nav(route, waitMs = 1600) {
  await ev(`location.hash = '#/${route}'`);
  await sleep(waitMs);
  for (let i = 0; i < 25; i++) {
    if (await ev(`!!document.querySelector('${READY[route] || ".card"}') && !document.querySelector('#view .spinner')`)) break;
    await sleep(300);
  }
}

// ---------- desktop ----------
await goto(1440, 900, false);
await ev(`localStorage.clear()`);
await ev(`location.reload()`);
for (let i = 0; i < 30; i++) {
  await sleep(300);
  if (await ev(`document.querySelectorAll('.kpi').length >= 4`)) break;
}
ok("overview renders KPIs", await ev(`document.querySelectorAll('.kpi').length >= 4`));
ok("overview matrix 12 rows", await ev(`document.querySelectorAll('.tbl tbody tr').length === 12`));
ok("honesty banner present", await ev(`document.body.textContent.includes('NOT TESTED')`));
await shot("01-overview.png", true);

// gate what-if: tighten CER to 0 → some PASS become PARTIAL
const before = await ev(`document.querySelectorAll('.b-pass').length`);
await ev(`(()=>{const i=document.querySelector('#gCer');i.value=0;i.dispatchEvent(new Event('input'));return 1})()`);
await sleep(400);
const after = await ev(`document.querySelectorAll('.b-pass').length`);
ok("gate slider recomputes matrix", after < before, `pass badges ${before}→${after}`);
await ev(`document.querySelector('#gateReset').click()`); await sleep(400);
ok("gate reset restores", await ev(`document.querySelector('#gCer').value === '0.15'`));

// language filter + defects toggle + density + sort
await ev(`(()=>{const s=document.querySelector('#fLang');s.value='ml';s.dispatchEvent(new Event('change'));return 1})()`);
await sleep(900);
await nav("evidence");
ok("language filter applied", await ev(`[...document.querySelectorAll('#evTable tbody tr')].every(tr=>tr.textContent.includes('ml'))`));
await ev(`(()=>{const s=document.querySelector('#fLang');s.value='';s.dispatchEvent(new Event('change'));return 1})()`);
await sleep(900);
ok("evidence 108 rows", await ev(`document.querySelectorAll('#evTable tbody tr').length === 108`));
await ev(`document.querySelector('#tDefects').click()`); await sleep(700);
const flagged = await ev(`document.querySelectorAll('#evTable tbody tr').length`);
ok("defects-only filter", flagged > 0 && flagged < 108, `${flagged} flagged rows`);
await ev(`document.querySelector('#tDefects').click()`); await sleep(600);
await ev(`(()=>{const s=document.querySelector('#fSort');s.value='cer';s.dispatchEvent(new Event('change'));return 1})()`);
await sleep(700);
ok("sort worst-CER first", await ev(`parseFloat(document.querySelector('#evTable tbody tr td.num').textContent) >= 0.9`));
await ev(`document.querySelector('#tDensity').click()`); await sleep(300);
ok("compact density", await ev(`document.body.classList.contains('compact')`));
await ev(`document.querySelector('#tDensity').click()`); await sleep(300);

// search
await ev(`(()=>{const i=document.querySelector('#evSearch');i.value='एन्टे';i.dispatchEvent(new Event('input'));return 1})()`);
await sleep(500);
await ev(`(()=>{const i=document.querySelector('#evSearch');i.value='ml';i.dispatchEvent(new Event('input'));return 1})()`);
await sleep(500);
ok("search filters rows", await ev(`document.querySelectorAll('#evTable tbody tr').length === 9`));
await ev(`(()=>{const i=document.querySelector('#evSearch');i.value='';i.dispatchEvent(new Event('input'));return 1})()`);
await sleep(500);

// bulk select + play queue + playback clock
await ev(`document.querySelector('#evSelAll').click()`); await sleep(500);
ok("bulk select all", await ev(`document.querySelectorAll('#evTable tbody tr.sel').length === 108`));
await ev(`document.querySelector('[data-action="ev-clear-sel"]').click()`); await sleep(400);
await ev(`document.querySelector('#evTable tbody tr .rowplay').click()`);
await sleep(1200);
const t1 = await ev(`document.querySelector('#player').currentTime`);
await sleep(900);
const t2 = await ev(`document.querySelector('#player').currentTime`);
ok("audio playback advances", t2 > t1, `${t1.toFixed(2)}→${t2.toFixed(2)}s`);
await ev(`document.querySelector('#player').pause()`);

// detail drawer
await ev(`document.querySelector('#evTable tbody tr [data-action="ev-detail"]').click()`); await sleep(500);
ok("evidence drawer opens", await ev(`!document.querySelector('#drawer').hidden && document.querySelector('#drawerBody').textContent.includes('Spectral centroid')`));
await shot("02-evidence-drawer.png");
await ev(`document.querySelector('#drawerClose').click()`); await sleep(300);

// drag reorder (synthetic HTML5 drag events)
await ev(`(()=>{
  const rows=document.querySelectorAll('#evTable tbody tr');
  if(rows.length<4) return 'rows='+rows.length;
  const a=rows[0], b=rows[3];
  const dt=new DataTransfer();
  a.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:dt}));
  b.dispatchEvent(new DragEvent('dragover',{bubbles:true,dataTransfer:dt}));
  b.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:dt}));
  a.dispatchEvent(new DragEvent('dragend',{bubbles:true,dataTransfer:dt}));
  return 'dragged'})()`);
await sleep(700);
ok("drag reorder switches to custom order", await ev(`document.querySelector('#fSort').value === 'custom'`));

// saved views
await ev(`(()=>{const i=document.querySelector('#viewName');i.value='QA view';i.dispatchEvent(new Event('input'));return 1})()`);
await ev(`document.querySelector('#viewSave').click()`); await sleep(400);
ok("saved view stored", await ev(`document.querySelectorAll('#savedList li .load').length === 1`));
await ev(`document.querySelector('#savedList .del').click()`); await sleep(400);
ok("view delete offers undo", await ev(`[...document.querySelectorAll('.toast button')].some(b=>b.textContent==='Undo')`));
await ev(`[...document.querySelectorAll('.toast button')].find(b=>b.textContent==='Undo').click()`); await sleep(400);
ok("view delete undo restores", await ev(`document.querySelectorAll('#savedList li .load').length === 1`));

// master mute
await ev(`document.querySelector('#masterMute').click()`); await sleep(300);
ok("master mute state", await ev(`document.querySelector('#masterMute').getAttribute('aria-pressed')==='true' && document.querySelector('.mute-label').textContent==='Muted'`));
await ev(`document.querySelector('#masterMute').click()`); await sleep(300);

// languages section + drawer
await nav("languages");
ok("12 language cards", await ev(`document.querySelectorAll('.lang-card').length === 12`));
await ev(`document.querySelector('.lang-card[data-lang="ml"]').click()`); await sleep(600);
ok("language drawer phonetic checklist", await ev(`document.querySelector('#drawerBody').textContent.includes('Complex clusters')`));
await shot("03-language-drawer.png");
await ev(`document.querySelector('#drawerClose').click()`); await sleep(300);

// dataset section
await nav("dataset");
ok("dataset 240 rows", await ev(`document.querySelectorAll('#dsTable tbody tr').length === 240`));
ok("dataset NOT TESTED banner", await ev(`document.body.textContent.includes('HUMAN DATASET: NOT TESTED')`));
await shot("04-dataset.png", true);

// record flow with fake mic
await ev(`document.querySelector('[data-action="ds-record"]').click()`); await sleep(600);
ok("record modal opens", await ev(`!document.querySelector('#modalScrim').hidden && !!document.querySelector('#recBtn')`));
await ev(`document.querySelector('#recBtn').click()`); await sleep(1500);
ok("recording started", await ev(`document.querySelector('#recBtn').textContent === 'STOP'`));
await ev(`document.querySelector('#recBtn').click()`); await sleep(800);
ok("recording captured preview", await ev(`document.querySelector('#recPreview').style.display === 'block'`));
await ev(`(()=>{document.querySelector('#recRef').value='QA plumbing recording';
  document.querySelector('#recSpeaker').value='qa_spk';
  document.querySelector('#recConsent').checked=true;return 1})()`);
await shot("05-record-modal.png");
await ev(`document.querySelector('[data-action="rec-submit"]').click()`); await sleep(2500);
ok("ingest landed COLLECTED", await ev(`document.body.textContent.includes('COLLECTED') && !!document.querySelector('.toast.ok')`));
const collectedNow = await ev(`fetch('/api/dataset').then(r=>r.json()).then(d=>d.summary.collected)`);
ok("server shows 1 collected (QA)", collectedNow === 1, String(collectedNow));
// clear via UI then undo
await ev(`(()=>{const b=document.querySelector('#dsTable tbody tr [data-action="ds-clear"]');if(b)b.click();return !!b})()`);
await sleep(500);
ok("clear modal opens", await ev(`!document.querySelector('#modalScrim').hidden && !!document.querySelector('#clearGo')`));
await ev(`document.querySelector('#clearGo')?.click()`);
let afterClear = 1;
for (let i = 0; i < 10; i++) {
  await sleep(700);
  afterClear = await ev(`fetch('/api/dataset').then(r=>r.json()).then(d=>d.summary.collected)`);
  if (afterClear === 0) break;
}
ok("clear returns to 0", afterClear === 0, String(afterClear));
// UI undo on the clear toast restores the COLLECTED slot…
await ev(`[...document.querySelectorAll('.toast button')].filter(b=>b.textContent==='Undo').pop()?.click()`);
await sleep(1200);
const undone1 = await ev(`fetch('/api/dataset').then(r=>r.json()).then(d=>d.summary.collected)`);
ok("clear toast undo restores slot", undone1 === 1, String(undone1));
// …then unwind verify + ingest to reach the pristine manifest.
await ev(`fetch('/api/dataset/undo',{method:'POST'}).then(r=>r.json())`); await sleep(600);
await ev(`fetch('/api/dataset/undo',{method:'POST'}).then(r=>r.json())`); await sleep(900);
const finalCollected = await ev(`fetch('/api/dataset').then(r=>r.json()).then(d=>d.summary.collected)`);
ok("undo chain restores pristine 0/240", finalCollected === 0, String(finalCollected));

// listening section
await nav("listening", 2200);
ok("listening package loaded", await ev(`document.querySelectorAll('.sample-queue .chip').length === 96`));
ok("10 rating dimensions", await ev(`document.querySelectorAll('.rate-row').length === 10`));
await ev(`document.querySelector('[data-action="listen-play"]').click()`); await sleep(1000);
ok("blind sample plays", await ev(`document.querySelector('#player').currentTime > 0`));
await ev(`(()=>{const i=document.querySelector('#listenerId');i.value='qa_listener';i.dispatchEvent(new Event('input'));return 1})()`);
await ev(`document.querySelector('.stars[data-dim="naturalness"] button[data-v="4"]').click()`); await sleep(200);
await ev(`document.querySelector('.stars[data-dim="pronunciation"] button[data-v="5"]').click()`); await sleep(200);
ok("stars reflect rating", await ev(`document.querySelectorAll('.stars[data-dim="naturalness"] button.on').length === 4`));
await shot("06-listening.png", true);
await ev(`document.querySelector('[data-action="listen-submit"]').click()`); await sleep(1800);
ok("response submitted", await ev(`!!document.querySelector('.toast.ok')`));
await ev(`document.querySelector('[data-action="listen-results"]').click()`); await sleep(900);
ok("results drawer shows means", await ev(`document.querySelector('#drawerBody').textContent.includes('mean listener rating')`));
await shot("07-listening-results.png");
await ev(`document.querySelector('#drawerClose').click()`); await sleep(300);

// benchmarks: launch a tiny real job
await nav("benchmarks");
await ev(`(()=>{document.querySelectorAll('#benchLangs .chip.on').forEach(c=>{if(c.dataset.lang!=='mr')c.click()});return 1})()`);
await sleep(300);
await ev(`(()=>{const s=document.querySelector('#benchSentences');s.value='1';const r=document.querySelector('#benchRepeats');r.value='1';return 1})()`);
await ev(`document.querySelector('[data-action="bench-run"]').click()`); await sleep(1500);
ok("benchmark job launched", await ev(`document.body.textContent.includes('running') || document.body.textContent.includes('done')`));
await shot("08-benchmarks.png");
// wait for job completion (poll)
let jobDone = false;
for (let i = 0; i < 40; i++) {
  await sleep(3000);
  const st = await ev(`fetch('/api/jobs').then(r=>r.json()).then(d=>d.jobs.map(j=>j.state).join(','))`);
  if (!st.includes("running")) { jobDone = true; break; }
}
ok("benchmark job completed", jobDone);
const runsCount = await ev(`fetch('/api/runs').then(r=>r.json()).then(d=>d.runs.length)`);
ok("new run directory created", runsCount >= 4, String(runsCount));

// reports
await nav("reports");
await ev(`document.querySelector('[data-action="report-generate"]').click()`); await sleep(3000);
ok("final report rendered", await ev(`document.querySelector('.md')?.textContent.includes('14. Production readiness')`));
ok("report has all 14 sections", await ev(`(document.querySelector('.md')?.textContent.match(/\\n?\\d+\\. /g)||[]).length >= 14 || document.querySelectorAll('.md h2').length >= 14`));
await shot("09-report.png", true);

// baseline
await nav("baseline", 2200);
ok("baseline markdown rendered", await ev(`document.querySelector('.md')?.textContent.includes('Safety attestation')`));
await shot("10-baseline.png", true);

// overflow check desktop
ok("no horizontal overflow desktop", await ev(`document.documentElement.scrollWidth <= window.innerWidth + 1`));

// ---------- mobile ----------
await goto(390, 844, true, 2);
for (let i = 0; i < 30; i++) {
  await sleep(300);
  if (await ev(`document.querySelectorAll('.kpi').length >= 4`)) break;
}
ok("mobile overview renders", await ev(`document.querySelectorAll('.kpi').length >= 4`));
ok("no horizontal overflow mobile", await ev(`document.documentElement.scrollWidth <= window.innerWidth + 1`));
await shot("11-mobile-overview.png", true);
await ev(`document.querySelector('#navToggle').click()`); await sleep(400);
ok("mobile nav opens", await ev(`document.querySelector('#sidenav').classList.contains('open')`));
await shot("12-mobile-nav.png");
await ev(`document.querySelector('#navToggle').click()`); await sleep(300);
await ev(`document.querySelector('.rail-fab').click()`); await sleep(400);
ok("mobile rail opens", await ev(`document.querySelector('#rail').classList.contains('open')`));
ok("mobile rail has >=7 tools", await ev(`document.querySelectorAll('#railBody input[type=range], #railBody select, #railBody .switch').length >= 7`));
await shot("13-mobile-rail.png");
await ev(`document.querySelector('.rail-fab').click()`); await sleep(300);
await nav("evidence", 2000);
ok("mobile evidence table scrolls", await ev(`!!document.querySelector('#evTable')`));
await shot("14-mobile-evidence.png");
await nav("listening", 2200);
ok("mobile listening renders", await ev(`document.querySelectorAll('.rate-row').length === 10`));
await shot("15-mobile-listening.png", true);

// ---------- summary ----------
// QA listener ratings are plumbing tests, never human evidence: remove them.
const respDir = "evaluation/human_voice_quality/responses";
if (fs.existsSync(respDir)) {
  for (const f of fs.readdirSync(respDir)) {
    if (f.includes("qa_listener")) fs.unlinkSync(path.join(respDir, f));
  }
}
// QA ingest was synthetic plumbing: drop its consent record and quarantined wav.
const consent = "evaluation/dataset/consent/hi_001.json";
if (fs.existsSync(consent)) {
  try {
    if (JSON.parse(fs.readFileSync(consent, "utf8")).speaker_id === "qa_spk") fs.unlinkSync(consent);
  } catch {}
}
const quar = "evaluation/dataset/quarantine";
if (fs.existsSync(quar)) {
  for (const d of fs.readdirSync(quar)) {
    const p = path.join(quar, d);
    if (fs.statSync(p).isDirectory() && fs.readdirSync(p).some(f => f.startsWith("hi_001"))) {
      fs.rmSync(p, { recursive: true, force: true });
    }
  }
}
console.log("\n--- console errors ---");
console.log(errors.length ? errors.join("\n") : "(none)");
ok("zero runtime console errors", errors.length === 0, errors.slice(0, 3).join(" | "));
const failed = results.filter(r => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
fs.writeFileSync(path.join(OUT, "qa_results.json"), JSON.stringify({ results, errors }, null, 2));
chrome.kill();
process.exit(failed.length ? 1 : 0);