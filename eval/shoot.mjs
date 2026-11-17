// Visual QA: drive headless Chrome over CDP, capture full-page + live-state shots.
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9223;
const OUT = "eval/shots";
fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${PORT}`, "--disable-gpu",
  "--no-first-run", "--no-default-browser-check", "--force-color-profile=srgb",
  `--user-data-dir=${process.env.TEMP || "/tmp"}/iv-shoot-profile`,
  "--window-size=1440,900", "about:blank",
], { stdio: "ignore" });

async function waitDebugger() {
  for (let i = 0; i < 60; i++) {
    try { return await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); }
    catch { await sleep(250); }
  }
  throw new Error("chrome debugger never came up");
}

const ver = await waitDebugger();
const ws = new WebSocket(ver.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

let seq = 0;
const pending = new Map();
const errors = [];
let loadResolve = null;
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
  } else if (m.method === "Page.loadEventFired" && loadResolve) {
    loadResolve(); loadResolve = null;
  } else if (m.method === "Runtime.exceptionThrown") {
    errors.push("EXCEPTION: " + JSON.stringify(m.params.exceptionDetails?.exception?.description || m.params.exceptionDetails?.text || m.params).slice(0, 300));
  } else if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type)) {
    errors.push(`CONSOLE ${m.params.type}: ` + (m.params.args || []).map(a => a.value ?? a.description ?? "").join(" ").slice(0, 300));
  }
};
const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
  const id = ++seq;
  pending.set(id, { res, rej });
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  setTimeout(() => { if (pending.has(id)) { pending.delete(id); rej(new Error("timeout " + method)); } }, 30000);
});

const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId: S } = await send("Target.attachToTarget", { targetId, flatten: true });
await send("Page.enable", {}, S);
await send("Runtime.enable", {}, S);

async function goto(width, height, mobile, dsf = 1) {
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: dsf, mobile }, S);
  const loaded = new Promise(r => { loadResolve = r; setTimeout(r, 15000); });
  await send("Page.navigate", { url: "http://127.0.0.1:8000/" }, S);
  await loaded;
  await send("Runtime.evaluate", { expression: "document.fonts.ready.then(() => 1)", awaitPromise: true }, S);
  await sleep(2600); // entrance animations, health fetch, orb frames
}

async function shot(name, beyondViewport) {
  const { data } = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: beyondViewport }, S);
  const file = path.join(OUT, name);
  fs.writeFileSync(file, Buffer.from(data, "base64"));
  console.log("saved", file, fs.statSync(file).size, "bytes");
}

const SEED = `(() => {
  const iv = window.__iv; const q = s => document.querySelector(s);
  iv.engine.running = true;
  const fake = { getByteFrequencyData(a) { const t = performance.now();
    for (let i = 0; i < a.length; i++) a[i] = Math.max(0, Math.min(255, 140 + 85 * Math.sin(i / 5.5 + t / 280) + 45 * Math.sin(i / 2.1 - t / 160))); } };
  iv.engine.playAnalyser = fake; iv.engine.micAnalyser = fake;
  iv.addMessage('sys', 'Call connected · हिन्दी · Hindi · 16000 Hz');
  iv.handleEvent({ type: 'transcript', text: 'नमस्ते! मेरा ऑर्डर नंबर एक दो तीन है।', asr_ms: 38 });
  iv.handleEvent({ type: 'reply', text: 'सुनिए, मैं आपके ऑर्डर की स्थिति जाँचता हूँ।', lang: 'hi', partial: true });
  iv.handleEvent({ type: 'reply', text: 'क्या आप बता सकते हैं कि यह ऑर्डर किस दिन दिया गया था?', lang: 'hi', partial: true });
  iv.handleEvent({ type: 'transcript', text: 'यह ऑर्डर मैंने कल दिया था।', asr_ms: 41 });
  iv.handleEvent({ type: 'reply', text: 'ठीक है! आपका ऑर्डर कल शाम तक पहुँच जाएगा।', lang: 'hi', partial: true });
  iv.addMessage('you', 'Great, thank you!', 'en', { asr_ms: 52 });
  iv.addMessage('agent', "You're welcome! Anything else I can help with?", 'en');
  iv.handleEvent({ type: 'latency', asr_ms: 38, llm_ms: 610, tts_ms: 430, first_audio_ms: 1080 });
  iv.handleEvent({ type: 'latency', asr_ms: 44, llm_ms: 580, tts_ms: 410, first_audio_ms: 1035 });
  iv.handleEvent({ type: 'latency', asr_ms: 31, llm_ms: 655, tts_ms: 468, first_audio_ms: 1150 });
  iv.session.turns = 3; iv.session.interrupts = 1; iv.session.calls = 1;
  iv.session.langs.add('hi'); iv.session.langs.add('en'); iv.session.talkMs = 161000;
  q('#statTurns').textContent = '3'; q('#statInterrupts').textContent = '1';
  q('#statCalls').textContent = '1'; q('#statLangs').textContent = '2'; q('#statUptime').textContent = '02:41';
  q('#capAgent').hidden = false; q('#capAgentText').textContent = "You're welcome! Anything else I can help with?";
  q('#callTimer').hidden = false; q('#callTimer').textContent = '02:41';
  q('#callBtn').classList.add('is-live'); q('#callBtnLabel').textContent = 'End call';
  q('#micMute').disabled = false;
  iv.setState('speaking');
  return 1;
})()`;

// 1. desktop full page, idle
await goto(1440, 900, false);
await shot("desktop-full.png", true);
// 2. desktop live-call state, viewport
await send("Runtime.evaluate", { expression: SEED }, S);
await sleep(800);
await shot("desktop-live.png", false);
// 3. mobile full page, idle
await goto(390, 844, true, 2);
await shot("mobile-full.png", true);
// 4. mobile live state, viewport
await send("Runtime.evaluate", { expression: SEED }, S);
await sleep(800);
await shot("mobile-live.png", false);
// 5. tablet full page
await goto(1000, 900, false);
await shot("tablet-full.png", true);

console.log("\n--- console errors/warnings ---");
console.log(errors.length ? errors.join("\n") : "(none)");
chrome.kill();
process.exit(0);