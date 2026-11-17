/* ============================================================
   IndicVoice Studio — app engine
   Wire protocol (src/call_server.py /ws/voice):
     out: binary 16 kHz mono PCM16-LE frames
     in : binary PCM16 audio + JSON events
          transcript / partial_transcript / reply / state /
          flush / latency
   ============================================================ */
"use strict";

/* ---------------- constants ---------------- */

const LANGS = [
  { code: "hi", native: "हिन्दी", en: "Hindi" },
  { code: "gu", native: "ગુજરાતી", en: "Gujarati" },
  { code: "mr", native: "मराठी", en: "Marathi" },
  { code: "bn", native: "বাংলা", en: "Bengali" },
  { code: "ta", native: "தமிழ்", en: "Tamil" },
  { code: "te", native: "తెలుగు", en: "Telugu" },
  { code: "kn", native: "ಕನ್ನಡ", en: "Kannada" },
  { code: "ml", native: "മലയാളം", en: "Malayalam" },
  { code: "pa", native: "ਪੰਜਾਬੀ", en: "Punjabi" },
  { code: "or", native: "ଓଡ଼ିଆ", en: "Odia" },
  { code: "as", native: "অসমীয়া", en: "Assamese" },
  { code: "en", native: "English", en: "Indian English" },
];
const LANG_BY_CODE = Object.fromEntries(LANGS.map(l => [l.code, l]));
const langLabel = c => (LANG_BY_CODE[c] ? `${LANG_BY_CODE[c].native} · ${LANG_BY_CODE[c].en}` : c);

const DEFAULTS = {
  lang: "hi", sttLang: "", endpoint: 0.5, backchannel: true, streaming: true,
  volume: 90, micGain: 1.0, vizStyle: "orb", vizIntensity: 70, particles: true,
  autoScroll: true, muted: false, token: "",
};
const STORE_KEY = "indicvoice.studio.v1";

const $ = id => document.getElementById(id);

/* ---------------- settings ---------------- */

let settings = { ...DEFAULTS };
try {
  const saved = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
  settings = { ...DEFAULTS, ...saved };
} catch { /* fresh start */ }
const urlToken = new URLSearchParams(location.search).get("token");
if (urlToken) settings.token = urlToken;

function saveSettings() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(settings)); } catch { /* private mode */ }
}

/* ---------------- toasts ---------------- */

function toast(msg, kind = "info", opts = {}) {
  const rack = $("toastRack");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<span class="toast-icon"></span><span class="toast-msg"></span>`;
  el.querySelector(".toast-msg").textContent = msg;
  if (opts.action) {
    const btn = document.createElement("button");
    btn.className = "toast-action";
    btn.textContent = opts.action;
    btn.onclick = () => { opts.onAction?.(); dismiss(); };
    el.appendChild(btn);
  }
  rack.appendChild(el);
  while (rack.children.length > 4) rack.firstChild.remove();
  let gone = false;
  const dismiss = () => {
    if (gone) return; gone = true;
    el.classList.add("out");
    setTimeout(() => el.remove(), 320);
  };
  setTimeout(dismiss, opts.ms || (opts.action ? 6500 : 3800));
  return dismiss;
}

/* ---------------- transcript store ---------------- */

const messages = [];
let msgSeq = 0;
let liveAgentEl = null;      // streaming agent bubble
let liveAgentMsg = null;
let filterRole = "all";
let filterText = "";

const listEl = $("transcriptList");

function fmtTime(d) {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function updateCount() {
  $("msgCount").textContent = messages.filter(m => m.role !== "sys").length;
  $("emptyState").style.display = messages.length ? "none" : "";
}

function applyFilters() {
  for (const m of messages) {
    if (!m.el) continue;
    const roleOk = filterRole === "all" || m.role === filterRole || m.role === "sys";
    const textOk = !filterText || m.text.toLowerCase().includes(filterText);
    m.el.classList.toggle("is-hidden", !(roleOk && textOk));
  }
}

function scrollTranscript() {
  if (settings.autoScroll) listEl.scrollTop = listEl.scrollHeight;
}

function addMessage(role, text, lang, extra = {}) {
  const m = { id: ++msgSeq, role, text, lang: lang || settings.lang, time: new Date(), ...extra };
  const el = document.createElement("div");
  m.el = el;
  if (role === "sys") {
    el.className = "msg msg-sys";
    el.textContent = text;
  } else {
    el.className = `msg msg-${role}`;
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    meta.innerHTML = `<span class="msg-role">${role === "you" ? "You" : "IndicVoice"}</span>
      <span class="msg-lang"></span><span class="msg-time">${fmtTime(m.time)}</span>`;
    meta.querySelector(".msg-lang").textContent = LANG_BY_CODE[m.lang]?.native || m.lang;
    const body = document.createElement("p");
    body.className = "msg-text";
    body.textContent = text;
    el.append(meta, body);
    m.bodyEl = body; m.metaEl = meta;
    if (extra.asr_ms != null) attachLatencyChip(m, extra.asr_ms);
  }
  messages.push(m);
  listEl.appendChild(el);
  updateCount(); applyFilters(); scrollTranscript();
  return m;
}

function attachLatencyChip(m, ms) {
  if (!m.el || m.el.querySelector(".msg-lat")) return;
  const chip = document.createElement("span");
  chip.className = "msg-lat";
  chip.textContent = `heard in ${Math.round(ms)} ms`;
  m.el.appendChild(chip);
}

function sealAgentMessage() {
  if (liveAgentEl) liveAgentEl.classList.remove("msg-live");
  liveAgentEl = null; liveAgentMsg = null;
}

function appendAgentSentence(text, lang) {
  if (!liveAgentMsg) {
    liveAgentMsg = addMessage("agent", text, lang);
    liveAgentEl = liveAgentMsg.el;
    liveAgentEl.classList.add("msg-live");
  } else {
    liveAgentMsg.text += (liveAgentMsg.text ? " " : "") + text;
    liveAgentMsg.bodyEl.textContent = liveAgentMsg.text;
    if (lang) liveAgentMsg.lang = lang;
    scrollTranscript();
  }
}

function transcriptText() {
  return messages.map(m => {
    if (m.role === "sys") return `— ${m.text} —`;
    const who = m.role === "you" ? "You" : "IndicVoice";
    return `[${fmtTime(m.time)}] ${who} (${langLabel(m.lang)}): ${m.text}`;
  }).join("\n");
}

function downloadBlob(name, mime, content) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function stamp() {
  const d = new Date();
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove(); return ok;
  }
}

$("copyTranscript").onclick = async () => {
  if (!messages.length) return toast("Nothing to copy yet — start a call first.", "warn");
  (await copyText(transcriptText()))
    ? toast("Transcript copied to clipboard.", "ok")
    : toast("Copy failed — use Download instead.", "error");
};
$("downloadTranscript").onclick = () => {
  if (!messages.length) return toast("Nothing to download yet.", "warn");
  downloadBlob(`indicvoice-transcript-${stamp()}.txt`, "text/plain;charset=utf-8", transcriptText());
  toast("Transcript downloaded.", "ok");
};
$("exportJson").onclick = () => {
  if (!messages.length) return toast("Nothing to export yet.", "warn");
  const data = messages.map(({ el, bodyEl, metaEl, ...rest }) => ({ ...rest, time: rest.time.toISOString() }));
  downloadBlob(`indicvoice-session-${stamp()}.json`, "application/json", JSON.stringify(data, null, 2));
  toast("Session exported as JSON.", "ok");
};
$("clearTranscript").onclick = () => {
  if (!messages.length) return;
  const snapshot = messages.slice();
  const els = snapshot.map(m => m.el);
  messages.length = 0; sealAgentMessage();
  els.forEach(el => el.remove());
  updateCount();
  toast("Conversation cleared.", "warn", {
    action: "Undo",
    onAction: () => {
      snapshot.forEach(m => { messages.push(m); listEl.appendChild(m.el); });
      updateCount(); applyFilters(); scrollTranscript();
      toast("Conversation restored.", "ok");
    },
  });
};
$("transcriptSearch").addEventListener("input", e => {
  filterText = e.target.value.trim().toLowerCase(); applyFilters();
});
document.querySelectorAll(".chip[data-role]").forEach(chip => {
  chip.onclick = () => {
    document.querySelectorAll(".chip[data-role]").forEach(c => c.classList.remove("is-on"));
    chip.classList.add("is-on");
    filterRole = chip.dataset.role; applyFilters();
  };
});
$("autoScroll").checked = settings.autoScroll;
$("autoScroll").onchange = e => { settings.autoScroll = e.target.checked; saveSettings(); };

document.querySelectorAll(".try-chip").forEach(chip => {
  chip.onclick = () => {
    setLanguage(chip.dataset.lang);
    toast(`Language set to ${langLabel(chip.dataset.lang)} — start the call and say it.`, "info");
  };
});

/* ---------------- telemetry ---------------- */

const METRICS = {
  asr: { hist: [], color: "#00e5c0", el: $("mAsr"), avg: $("avgAsr"), spark: $("sparkAsr") },
  llm: { hist: [], color: "#ffb020", el: $("mLlm"), avg: $("avgLlm"), spark: $("sparkLlm") },
  tts: { hist: [], color: "#ff2e88", el: $("mTts"), avg: $("avgTts"), spark: $("sparkTts") },
  first: { hist: [], color: "#4cc9f0", el: $("mFirst"), avg: $("avgFirst"), spark: $("sparkFirst") },
};
const session = { turns: 0, interrupts: 0, calls: 0, langs: new Set(), talkMs: 0 };

function drawSpark(metric) {
  const cv = metric.spark;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = cv.clientWidth || 220, h = 44;
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const hist = metric.hist;
  if (!hist.length) {
    ctx.strokeStyle = "rgba(154,147,184,.25)";
    ctx.setLineDash([3, 5]);
    ctx.beginPath(); ctx.moveTo(0, h - 6); ctx.lineTo(w, h - 6); ctx.stroke();
    ctx.setLineDash([]);
    return;
  }
  const max = Math.max(...hist, 100);
  const n = hist.length;
  const x = i => n === 1 ? w / 2 : (i / (Math.max(n - 1, 1))) * (w - 8) + 4;
  const y = v => h - 5 - (v / max) * (h - 12);
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, metric.color + "55");
  grad.addColorStop(1, metric.color + "00");
  ctx.beginPath();
  hist.forEach((v, i) => i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(0), y(v)));
  ctx.strokeStyle = metric.color; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.stroke();
  ctx.lineTo(x(n - 1), h); ctx.lineTo(x(0), h); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  ctx.beginPath();
  ctx.arc(x(n - 1), y(hist[n - 1]), 3, 0, Math.PI * 2);
  ctx.fillStyle = "#fff"; ctx.fill();
  ctx.strokeStyle = metric.color; ctx.lineWidth = 2; ctx.stroke();
}

function pushMetric(key, value) {
  const m = METRICS[key];
  if (value == null || !isFinite(value)) return;
  m.hist.push(value);
  if (m.hist.length > 48) m.hist.shift();
  m.el.textContent = Math.round(value);
  m.avg.textContent = Math.round(m.hist.reduce((a, b) => a + b, 0) / m.hist.length);
  drawSpark(m);
  const card = m.el.closest(".metric-card");
  card.classList.remove("flash"); void card.offsetWidth; card.classList.add("flash");
}

function handleLatency(ev) {
  pushMetric("asr", ev.asr_ms);
  pushMetric("llm", ev.llm_ms);
  pushMetric("tts", ev.tts_ms);
  pushMetric("first", ev.first_audio_ms);
  $("cntAsr").textContent = METRICS.asr.hist.length;
}

function updateSessionStats() {
  $("statTurns").textContent = session.turns;
  $("statInterrupts").textContent = session.interrupts;
  $("statCalls").textContent = session.calls;
  $("statLangs").textContent = session.langs.size;
  $("statUptime").textContent = fmtDur(session.talkMs);
}
function fmtDur(ms) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/* pipeline strip */
const pipeTimers = {};
function hotPipe(name, ms = 0) {
  const node = document.querySelector(`.pipe-node[data-pipe="${name}"]`);
  if (!node) return;
  node.classList.add("is-hot");
  clearTimeout(pipeTimers[name]);
  if (ms > 0) pipeTimers[name] = setTimeout(() => node.classList.remove("is-hot"), ms);
}
function coldPipe(name) {
  const node = document.querySelector(`.pipe-node[data-pipe="${name}"]`);
  if (node) node.classList.remove("is-hot");
}
function setPipeline(state) {
  ["mic", "vad", "stt", "llm", "tts", "spk"].forEach(coldPipe);
  if (state === "listening") { hotPipe("mic"); hotPipe("vad"); }
  if (state === "thinking") { hotPipe("mic"); hotPipe("stt"); hotPipe("llm"); }
  if (state === "speaking") { hotPipe("tts"); hotPipe("spk"); }
}

/* ---------------- health ---------------- */

let healthData = null;
const CARD_GRADS = [
  "linear-gradient(90deg,#ffb703,#ff2e88)", "linear-gradient(90deg,#00e5c0,#4cc9f0)",
  "linear-gradient(90deg,#6c5ce7,#ff2e88)", "linear-gradient(90deg,#ff9f1c,#ffb703)",
  "linear-gradient(90deg,#4cc9f0,#6c5ce7)", "linear-gradient(90deg,#ff2e88,#b14cff)",
  "linear-gradient(90deg,#2dd4a7,#00e5c0)", "linear-gradient(90deg,#ffb020,#ff4d5e)",
  "linear-gradient(90deg,#b14cff,#4cc9f0)", "linear-gradient(90deg,#ff7a3d,#ff2e88)",
  "linear-gradient(90deg,#00e5c0,#2dd4a7)", "linear-gradient(90deg,#6c5ce7,#ffb703)",
];

function renderHealth() {
  const grid = $("voiceGrid");
  grid.innerHTML = "";
  const voices = healthData?.voices || {};
  LANGS.forEach((l, i) => {
    const v = voices[l.code] || {};
    const card = document.createElement("div");
    card.className = "voice-card reveal";
    card.style.setProperty("--d", `${0.03 * i}s`);
    card.style.setProperty("--vc-grad", CARD_GRADS[i % CARD_GRADS.length]);
    card.dataset.lang = l.code;
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.title = `Use ${l.en} for the next call`;
    const ttsOk = !!v.ready, asrOk = !!v.asr;
    card.innerHTML = `
      <span class="voice-pick">selected</span>
      <p class="voice-native">${l.native}</p>
      <p class="voice-en">${l.en} · ${l.code}</p>
      <div class="voice-tags">
        <span class="vtag vtag-backend">${v.backend || "…"}</span>
        <span class="vtag"><span class="dot ${ttsOk ? "dot-ok" : "dot-bad"}"></span>voice ${ttsOk ? "ready" : "missing"}</span>
        <span class="vtag"><span class="dot ${asrOk ? "dot-ok" : "dot-warn"}"></span>${asrOk ? "ASR local" : "ASR cloud"}</span>
      </div>`;
    const pick = () => { setLanguage(l.code); toast(`Language set to ${l.native} · ${l.en}.`, "ok"); };
    card.onclick = pick;
    card.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } };
    if (l.code === settings.lang) card.classList.add("is-selected");
    grid.appendChild(card);
  });

  const llm = healthData?.llm;
  const llmReady = $("llmReady");
  if (llm?.ready) {
    $("llmSub").textContent = `${llm.backend} · ${llm.model}`;
    llmReady.textContent = "READY"; llmReady.className = "ready-chip ok";
  } else if (llm) {
    $("llmSub").textContent = llm.error || "not configured";
    llmReady.textContent = "OFFLINE"; llmReady.className = "ready-chip bad";
  } else {
    $("llmSub").textContent = "server unreachable";
    llmReady.textContent = "UNKNOWN"; llmReady.className = "ready-chip";
  }

  const pill = $("serverPill"), pillText = $("serverPillText");
  const dot = pill.querySelector(".dot");
  if (!healthData) {
    dot.className = "dot dot-bad"; pillText.textContent = "server offline";
    pill.title = "Could not reach /health — is call_server running?";
  } else {
    const ready = Object.values(voices).filter(v => v.ready).length;
    if (ready === LANGS.length) {
      dot.className = "dot dot-ok"; pillText.textContent = "all 12 voices ready";
    } else {
      dot.className = "dot dot-warn"; pillText.textContent = `${ready}/12 voices ready`;
    }
    pill.title = `LLM: ${llm?.ready ? llm.backend + " · " + llm.model : "offline"}${healthData.supertonic ? " · Supertonic available" : ""}`;
  }
}

async function fetchHealth() {
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 6000);
    const res = await fetch("/health", { signal: ctl.signal });
    clearTimeout(t);
    healthData = res.ok ? await res.json() : null;
  } catch { healthData = null; }
  renderHealth();
}
$("refreshHealth").onclick = () => { fetchHealth(); toast("Refreshing model status…", "info", { ms: 1600 }); };

/* ---------------- visualizer ---------------- */

const viz = {
  canvas: $("orbCanvas"),
  ctx: null,
  style: settings.vizStyle,
  intensity: settings.vizIntensity / 100,
  particlesOn: settings.particles,
  level: 0,
  freq: new Uint8Array(128),
  particles: [],
  size: 0, dpr: 1,
  state: "idle",
  flash: 0,
};
viz.ctx = viz.canvas.getContext("2d");

for (let i = 0; i < 64; i++) {
  viz.particles.push({
    a: Math.random() * Math.PI * 2,
    r: 0.62 + Math.random() * 0.34,
    sp: (0.00025 + Math.random() * 0.0007) * (Math.random() < 0.5 ? 1 : -1),
    sz: 0.8 + Math.random() * 2.1,
    tw: Math.random() * Math.PI * 2,
  });
}

function resizeViz() {
  const rect = viz.canvas.getBoundingClientRect();
  viz.dpr = Math.min(window.devicePixelRatio || 1, 2);
  viz.size = Math.max(10, rect.width);
  viz.canvas.width = viz.size * viz.dpr;
  viz.canvas.height = viz.size * viz.dpr;
}
new ResizeObserver(resizeViz).observe(viz.canvas);
resizeViz();

const STATE_COLORS = {
  idle:        { a: "#6c5ce7", b: "#3b2f7a", glow: "rgba(108,92,231,.4)",  bar: "#8b7dff" },
  connecting:  { a: "#4cc9f0", b: "#2b5f8a", glow: "rgba(76,201,240,.45)", bar: "#4cc9f0" },
  listening:   { a: "#00e5c0", b: "#0f7a8a", glow: "rgba(0,229,192,.5)",  bar: "#00e5c0" },
  thinking:    { a: "#ffb020", b: "#a3541e", glow: "rgba(255,176,32,.5)", bar: "#ffb020" },
  speaking:    { a: "#ffb703", b: "#ff2e88", glow: "rgba(255,122,61,.55)", bar: "#ff7a3d" },
  interrupted: { a: "#ff2e88", b: "#ff4d5e", glow: "rgba(255,46,136,.6)", bar: "#ff2e88" },
};

function vizFrame(t) {
  requestAnimationFrame(vizFrame);
  const { ctx, size } = viz;
  if (!size) return;
  ctx.setTransform(viz.dpr, 0, 0, viz.dpr, 0, 0);
  ctx.clearRect(0, 0, size, size);

  /* pick analyser + target level */
  let target = 0;
  const eng = engine;
  if (eng.running && eng.playAnalyser && viz.state === "speaking") {
    eng.playAnalyser.getByteFrequencyData(viz.freq);
    target = avgBand(viz.freq, 0, 64) / 255;
  } else if (eng.running && eng.micAnalyser && (viz.state === "listening" || viz.state === "thinking")) {
    eng.micAnalyser.getByteFrequencyData(viz.freq);
    target = avgBand(viz.freq, 0, 48) / 255;
    if (viz.state === "listening" && target > 0.09) hotPipe("vad");
  } else {
    viz.freq.fill(0);
    target = 0.05 + 0.035 * Math.sin(t / 1100);   // idle breathing
  }
  target *= viz.intensity;
  viz.level += (target - viz.level) * 0.16;
  viz.flash = Math.max(0, viz.flash - 0.02);

  const c = STATE_COLORS[viz.state] || STATE_COLORS.idle;
  const cx = size / 2, cy = size / 2;
  const base = size * 0.26;
  const R = base * (1 + viz.level * 0.55 + viz.flash * 0.12);
  const spin = t * (viz.state === "thinking" ? 0.0016 : 0.00042);

  /* halo */
  const halo = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 2.4);
  halo.addColorStop(0, c.glow);
  halo.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = halo;
  ctx.fillRect(0, 0, size, size);

  if (viz.style === "orb") drawOrb(ctx, cx, cy, R, c, t, spin);
  else if (viz.style === "bars") drawBars(ctx, cx, cy, R, c, t, spin);
  else drawRings(ctx, cx, cy, R, c, t, spin);

  /* particles */
  if (viz.particlesOn) {
    const speed = 1 + viz.level * 5 + (viz.state === "thinking" ? 2.2 : 0);
    for (const p of viz.particles) {
      p.a += p.sp * speed * 16;
      const pr = R * (p.r + 0.55) + Math.sin(t / 900 + p.tw) * 4;
      const x = cx + Math.cos(p.a) * pr, y = cy + Math.sin(p.a) * pr;
      const alpha = 0.25 + 0.5 * Math.abs(Math.sin(t / 700 + p.tw)) * (0.4 + viz.level);
      ctx.beginPath();
      ctx.arc(x, y, p.sz * (0.8 + viz.level * 0.8), 0, Math.PI * 2);
      ctx.fillStyle = c.bar;
      ctx.globalAlpha = Math.min(alpha, 0.85);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }
}

function avgBand(arr, lo, hi) {
  let s = 0;
  for (let i = lo; i < hi; i++) s += arr[i];
  return s / (hi - lo);
}

function coreGradient(ctx, cx, cy, R, c) {
  const g = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.35, R * 0.1, cx, cy, R);
  g.addColorStop(0, "#fff7ea");
  g.addColorStop(0.25, c.a);
  g.addColorStop(0.75, c.b);
  g.addColorStop(1, "rgba(17,13,36,.9)");
  return g;
}

function drawOrb(ctx, cx, cy, R, c, t, spin) {
  /* reactive spikes */
  const N = 90;
  ctx.save();
  ctx.translate(cx, cy); ctx.rotate(spin * 0.4);
  ctx.beginPath();
  for (let i = 0; i <= N; i++) {
    const a = (i / N) * Math.PI * 2;
    const bin = viz.freq[Math.floor((i % N) / N * 64)] / 255;
    const wob = Math.sin(a * 5 + t / 480) * 0.03;
    const r = R * (1.06 + bin * viz.intensity * 0.5 + wob);
    const x = Math.cos(a) * r, y = Math.sin(a) * r;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.closePath();
  ctx.strokeStyle = c.bar; ctx.globalAlpha = 0.55; ctx.lineWidth = 1.6;
  ctx.shadowColor = c.glow; ctx.shadowBlur = 18;
  ctx.stroke();
  ctx.restore();

  /* core */
  ctx.save();
  ctx.shadowColor = c.glow; ctx.shadowBlur = 34;
  ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fillStyle = coreGradient(ctx, cx, cy, R, c); ctx.fill();
  ctx.restore();

  /* rotating dashed ring */
  ctx.save();
  ctx.translate(cx, cy); ctx.rotate(-spin);
  ctx.beginPath(); ctx.arc(0, 0, R * 1.5, 0, Math.PI * 2);
  ctx.setLineDash([2, 14]);
  ctx.strokeStyle = c.bar; ctx.globalAlpha = 0.5; ctx.lineWidth = 2; ctx.stroke();
  ctx.restore();

  /* thinking comet */
  if (viz.state === "thinking") {
    ctx.save();
    ctx.translate(cx, cy); ctx.rotate(spin * 2.4);
    ctx.beginPath(); ctx.arc(0, 0, R * 1.28, 0, Math.PI * 0.7);
    ctx.strokeStyle = c.a; ctx.lineWidth = 3.4; ctx.lineCap = "round";
    ctx.shadowColor = c.glow; ctx.shadowBlur = 16; ctx.stroke();
    ctx.restore();
  }
}

function drawBars(ctx, cx, cy, R, c, t, spin) {
  const N = 72;
  ctx.save();
  ctx.translate(cx, cy); ctx.rotate(spin * 0.3);
  ctx.lineCap = "round";
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    const bin = viz.freq[Math.floor(i / N * 64)] / 255;
    const len = R * (0.16 + bin * viz.intensity * 0.95) + 3;
    const r0 = R * 1.02;
    ctx.beginPath();
    ctx.moveTo(Math.cos(a) * r0, Math.sin(a) * r0);
    ctx.lineTo(Math.cos(a) * (r0 + len), Math.sin(a) * (r0 + len));
    const g = ctx.createLinearGradient(0, 0, Math.cos(a) * (r0 + len), Math.sin(a) * (r0 + len));
    g.addColorStop(0, c.a); g.addColorStop(1, c.b);
    ctx.strokeStyle = g;
    ctx.lineWidth = 3.6;
    ctx.shadowColor = c.glow; ctx.shadowBlur = 10;
    ctx.stroke();
  }
  ctx.restore();
  ctx.save();
  ctx.shadowColor = c.glow; ctx.shadowBlur = 28;
  ctx.beginPath(); ctx.arc(cx, cy, R * 0.82, 0, Math.PI * 2);
  ctx.fillStyle = coreGradient(ctx, cx, cy, R * 0.82, c); ctx.fill();
  ctx.restore();
}

function drawRings(ctx, cx, cy, R, c, t, spin) {
  for (let k = 0; k < 5; k++) {
    const band = avgBand(viz.freq, k * 12, k * 12 + 12) / 255;
    const r = R * (0.55 + k * 0.3) * (1 + band * viz.intensity * 0.35);
    ctx.save();
    ctx.translate(cx, cy); ctx.rotate(spin * (k % 2 ? 1 : -1) * (1 + k * 0.3));
    ctx.beginPath();
    const gap = 0.5 + 0.25 * Math.sin(t / 800 + k);
    ctx.arc(0, 0, r, gap, Math.PI * 2 - gap);
    ctx.strokeStyle = k % 2 ? c.a : c.bar;
    ctx.globalAlpha = 0.4 + band * 0.6;
    ctx.lineWidth = 2.6 + band * 3;
    ctx.shadowColor = c.glow; ctx.shadowBlur = 14;
    ctx.stroke();
    ctx.restore();
  }
  ctx.save();
  ctx.shadowColor = c.glow; ctx.shadowBlur = 30;
  ctx.beginPath(); ctx.arc(cx, cy, R * 0.4 * (1 + viz.level * 0.5), 0, Math.PI * 2);
  ctx.fillStyle = coreGradient(ctx, cx, cy, R * 0.4, c); ctx.fill();
  ctx.restore();
}

requestAnimationFrame(vizFrame);

/* ---------------- state machine ---------------- */

let appState = "idle";
function setState(s) {
  appState = s;
  viz.state = s === "idle" ? "idle" : s;
  const badge = $("stateBadge");
  badge.dataset.state = s;
  const labels = {
    idle: "Ready", connecting: "Connecting", listening: "Listening",
    thinking: "Thinking", speaking: "Speaking", interrupted: "Interrupted",
  };
  $("stateText").textContent = labels[s] || s;
  $("orbHint").style.opacity = (s === "idle" || s === "connecting") ? "" : "0";
  document.querySelector(".orb-wrap").classList.toggle("is-live", s !== "idle" && s !== "connecting");
  setPipeline(s);
}

/* ---------------- audio engine ---------------- */

const WORKLET_CODE = `class MicProcessor extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(1024); this.n = 0; }
  process(inputs) {
    const ch = inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.buf[this.n++] = ch[i];
      if (this.n === this.buf.length) { this.port.postMessage(this.buf.slice(0)); this.n = 0; }
    }
    return true;
  }
}
registerProcessor("mic-processor", MicProcessor);`;

const engine = {
  running: false,
  ws: null, ctx: null, stream: null, node: null,
  micGainNode: null, micAnalyser: null,
  playGain: null, playAnalyser: null,
  playAt: 0, sources: new Set(),
  micMuted: false,
  intentionalClose: false,
  callStart: 0, timerId: null, drainId: null,
};

function applyOutputVolume() {
  if (engine.playGain && engine.ctx) {
    const v = settings.muted ? 0 : (settings.volume / 100);
    engine.playGain.gain.setTargetAtTime(v, engine.ctx.currentTime, 0.03);
  }
}

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const p = new URLSearchParams();
  p.set("lang", settings.lang);
  if (settings.sttLang) p.set("stt_lang", settings.sttLang);
  if (settings.token) p.set("token", settings.token);
  p.set("backchannel", settings.backchannel ? "1" : "0");
  p.set("endpoint", String(settings.endpoint));
  p.set("streaming", settings.streaming ? "1" : "0");
  return `${proto}://${location.host}/ws/voice?${p}`;
}

async function ensureAudioGraph() {
  if (engine.ctx) return;
  let ctx;
  try { ctx = new AudioContext({ sampleRate: 16000 }); }
  catch { ctx = new AudioContext(); }
  engine.ctx = ctx;
  if (ctx.state === "suspended") await ctx.resume();

  engine.stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const src = ctx.createMediaStreamSource(engine.stream);

  const workletUrl = URL.createObjectURL(new Blob([WORKLET_CODE], { type: "application/javascript" }));
  await ctx.audioWorklet.addModule(workletUrl);
  URL.revokeObjectURL(workletUrl);
  engine.node = new AudioWorkletNode(ctx, "mic-processor");

  engine.micGainNode = ctx.createGain();
  engine.micGainNode.gain.value = settings.micGain;
  engine.micAnalyser = ctx.createAnalyser();
  engine.micAnalyser.fftSize = 256;
  engine.micAnalyser.smoothingTimeConstant = 0.7;

  const zero = ctx.createGain(); zero.gain.value = 0;   // keep graph pulled, never echo mic
  src.connect(engine.micGainNode);
  engine.micGainNode.connect(engine.node);
  engine.micGainNode.connect(engine.micAnalyser);
  engine.node.connect(zero);
  engine.micAnalyser.connect(zero);
  zero.connect(ctx.destination);

  engine.playGain = ctx.createGain();
  engine.playAnalyser = ctx.createAnalyser();
  engine.playAnalyser.fftSize = 256;
  engine.playAnalyser.smoothingTimeConstant = 0.72;
  engine.playGain.connect(engine.playAnalyser);
  engine.playAnalyser.connect(ctx.destination);
  applyOutputVolume();

  engine.node.port.onmessage = ev => {
    if (!engine.ws || engine.ws.readyState !== 1) return;
    const raw = ev.data;
    let f32 = raw;
    if (Math.abs(ctx.sampleRate - 16000) > 1) {
      const n = Math.max(1, Math.round(raw.length * 16000 / ctx.sampleRate));
      f32 = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const pos = i * ctx.sampleRate / 16000;
        const a = Math.floor(pos), b = Math.min(a + 1, raw.length - 1);
        f32[i] = raw[a] + (raw[b] - raw[a]) * (pos - a);
      }
    }
    const gain = engine.micMuted ? 0 : settings.micGain;
    const i16 = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) {
      i16[i] = Math.max(-1, Math.min(1, f32[i] * gain)) * 32767;
    }
    engine.ws.send(i16.buffer);
  };
}

function connectWS() {
  engine.intentionalClose = false;
  setState("connecting");
  const ws = new WebSocket(wsUrl());
  ws.binaryType = "arraybuffer";
  engine.ws = ws;

  ws.onopen = () => {
    if (engine.ws !== ws) return;
    engine.running = true;
    engine.callStart = Date.now();
    session.calls++; updateSessionStats();
    setState("listening");
    $("callBtn").classList.add("is-live");
    $("callBtnLabel").textContent = "End call";
    $("micMute").disabled = false;
    $("callTimer").hidden = false;
    addMessage("sys", `Call connected · ${langLabel(settings.lang)} · ${engine.ctx.sampleRate} Hz`);
    chime([660, 880], 0.12);
    clearInterval(engine.timerId);
    engine.timerId = setInterval(() => {
      $("callTimer").textContent = fmtDur(Date.now() - engine.callStart);
    }, 1000);
    clearInterval(engine.drainId);
    engine.drainId = setInterval(() => {
      if (appState === "speaking" && engine.sources.size === 0) setState("listening");
    }, 160);
  };

  ws.onmessage = ev => {
    if (engine.ws !== ws) return;
    if (typeof ev.data === "string") {
      let msg; try { msg = JSON.parse(ev.data); } catch { return; }
      handleEvent(msg);
      return;
    }
    playChunk(ev.data);
  };

  ws.onclose = ev => {
    if (engine.ws !== ws) return;
    const wasRunning = engine.running;
    teardownCall(false);
    if (ev.code === 4401) {
      toast("The server requires a valid access token — set it in the Control deck.", "error", { ms: 7000 });
      addMessage("sys", "Connection rejected: access token required");
    } else if (ev.code === 4408) {
      toast("Call ended after 3 minutes of silence.", "info");
      addMessage("sys", "Call ended (idle timeout)");
    } else if (wasRunning && !engine.intentionalClose) {
      toast("Connection lost — start the call again when ready.", "warn");
      addMessage("sys", "Connection lost");
    }
  };
  ws.onerror = () => { /* onclose follows with the code */ };
}

function handleEvent(msg) {
  switch (msg.type) {
    case "partial_transcript":
      $("capYou").hidden = false;
      $("capYouText").textContent = msg.text;
      hotPipe("stt", 1400);
      break;
    case "transcript": {
      $("capYou").hidden = true; $("capYouText").textContent = "";
      sealAgentMessage();
      const m = addMessage("you", msg.text, settings.lang, { asr_ms: msg.asr_ms });
      session.turns++; session.langs.add(settings.lang); updateSessionStats();
      hotPipe("stt", 1200);
      if (msg.asr_ms != null) pushMetric("asr", msg.asr_ms);
      break;
    }
    case "reply": {
      const lang = msg.lang || settings.lang;
      session.langs.add(lang);
      $("stageLangChip").textContent = langLabel(lang);
      $("capAgent").hidden = false;
      $("capAgentText").textContent = msg.text;
      appendAgentSentence(msg.text, lang);
      updateSessionStats();
      break;
    }
    case "state":
      if (msg.value === "thinking") {
        setState("thinking");
        $("capAgent").hidden = true; $("capAgentText").textContent = "";
        hotPipe("llm");
      } else if (msg.value === "interrupted") {
        session.interrupts++; updateSessionStats();
        viz.flash = 1;
        setState("interrupted");
        setTimeout(() => { if (engine.running && appState === "interrupted") setState("listening"); }, 650);
      }
      if (msg.lang) $("stageLangChip").textContent = langLabel(msg.lang);
      break;
    case "flush":
      flushPlayback();
      break;
    case "latency":
      handleLatency(msg);
      break;
  }
}

function playChunk(buf) {
  const ctx = engine.ctx;
  if (!ctx) return;
  const i16 = new Int16Array(buf);
  if (!i16.length) return;
  const audio = ctx.createBuffer(1, i16.length, 16000);
  const ch = audio.getChannelData(0);
  for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 32768;
  const src = ctx.createBufferSource();
  src.buffer = audio;
  src.connect(engine.playGain);
  engine.playAt = Math.max(engine.playAt, ctx.currentTime + 0.02);
  src.start(engine.playAt);
  engine.playAt += audio.duration;
  engine.sources.add(src);
  src.onended = () => engine.sources.delete(src);
  if (appState !== "speaking") setState("speaking");
  hotPipe("tts"); hotPipe("spk");
}

function flushPlayback() {
  for (const src of engine.sources) { try { src.stop(); } catch { /* already stopped */ } }
  engine.sources.clear();
  if (engine.ctx) engine.playAt = engine.ctx.currentTime;
}

function teardownCall(closeWs = true) {
  if (closeWs && engine.ws) {
    engine.intentionalClose = true;
    try { engine.ws.close(); } catch { /* noop */ }
  }
  engine.ws = null;
  engine.running = false;
  flushPlayback();
  clearInterval(engine.timerId); engine.timerId = null;
  clearInterval(engine.drainId); engine.drainId = null;
  if (engine.callStart) {
    session.talkMs += Date.now() - engine.callStart;
    engine.callStart = 0; updateSessionStats();
  }
  $("callTimer").hidden = true;
  $("callBtn").classList.remove("is-live");
  $("callBtnLabel").textContent = "Start call";
  $("callBtn").disabled = false;
  $("micMute").disabled = true;
  $("capYou").hidden = true; $("capAgent").hidden = true;
  sealAgentMessage();
  setState("idle");
}

async function destroyAudio() {
  if (engine.node) { try { engine.node.disconnect(); } catch {} engine.node = null; }
  if (engine.stream) { engine.stream.getTracks().forEach(t => t.stop()); engine.stream = null; }
  if (engine.ctx) { try { await engine.ctx.close(); } catch {} engine.ctx = null; }
  engine.micAnalyser = null; engine.playAnalyser = null;
  engine.playGain = null; engine.micGainNode = null;
}

async function startCall() {
  if (engine.running || $("callBtn").disabled) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    toast("This browser cannot access a microphone here. Use Chrome/Edge over HTTPS or localhost.", "error", { ms: 7000 });
    return;
  }
  $("callBtn").disabled = true;
  $("callBtnLabel").textContent = "Connecting…";
  try {
    await ensureAudioGraph();
  } catch (err) {
    $("callBtn").disabled = false;
    $("callBtnLabel").textContent = "Start call";
    await destroyAudio();
    const name = err?.name || "";
    if (name === "NotAllowedError" || name === "SecurityError") {
      toast("Microphone permission denied — allow mic access in the browser, then try again.", "error", { ms: 7000 });
    } else if (name === "NotFoundError") {
      toast("No microphone found on this device.", "error");
    } else {
      toast(`Could not open the microphone: ${err?.message || err}`, "error", { ms: 6000 });
    }
    return;
  }
  connectWS();
}

async function stopCall() {
  const wasLive = engine.running;
  teardownCall(true);
  await destroyAudio();
  if (wasLive) {
    addMessage("sys", "Call ended");
    chime([520, 390], 0.1);
  }
}

let reconnectTimer = null;
function scheduleReconnect() {
  if (!engine.running) return;
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    if (!engine.running) return;
    flushPlayback();
    sealAgentMessage();
    engine.intentionalClose = true;
    const old = engine.ws;
    engine.ws = null;
    if (old) { try { old.close(); } catch {} }
    addMessage("sys", "Reconnecting with updated call settings…");
    connectWS();
  }, 550);
}

$("callBtn").onclick = () => (engine.running ? stopCall() : startCall());

$("micMute").onclick = () => {
  engine.micMuted = !engine.micMuted;
  $("micMute").setAttribute("aria-pressed", String(engine.micMuted));
  toast(engine.micMuted ? "Microphone muted — the agent can't hear you." : "Microphone live.", engine.micMuted ? "warn" : "ok", { ms: 2200 });
};

/* chimes — tied to visible connect/disconnect/test events, obey master mute */
function chime(freqs, dur = 0.12) {
  if (settings.muted) return;
  try {
    const ctx = engine.ctx || new AudioContext();
    const own = !engine.ctx;
    if (ctx.state === "suspended") ctx.resume();
    const g = ctx.createGain();
    g.gain.value = 0.0001;
    g.connect(ctx.destination);
    const vol = 0.12 * (settings.volume / 100);
    freqs.forEach((f, i) => {
      const o = ctx.createOscillator();
      o.type = "sine"; o.frequency.value = f;
      const t0 = ctx.currentTime + i * dur;
      o.connect(g);
      o.start(t0); o.stop(t0 + dur);
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.exponentialRampToValueAtTime(Math.max(vol, 0.0002), t0 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    });
    setTimeout(() => { g.disconnect(); if (own) ctx.close(); }, (freqs.length * dur + 0.3) * 1000);
  } catch { /* audio unavailable */ }
}

$("speakerTest").onclick = () => {
  if (settings.muted) return toast("Sound is muted — unmute with the top-bar button first.", "warn");
  chime([523.25, 659.25, 783.99], 0.14);
  hotPipe("spk", 900);
  viz.flash = 0.7;
  toast("Test chime played — if you heard it, your speaker path works.", "ok", { ms: 2600 });
};

/* master mute */
function renderMute() {
  $("masterMute").setAttribute("aria-pressed", String(settings.muted));
  $("masterMuteLabel").textContent = settings.muted ? "Muted" : "Sound on";
}
$("masterMute").onclick = () => {
  settings.muted = !settings.muted;
  saveSettings(); renderMute(); applyOutputVolume();
  toast(settings.muted ? "All sound muted." : "Sound on.", settings.muted ? "warn" : "ok", { ms: 1800 });
};
renderMute();

/* ---------------- control deck wiring ---------------- */

function fillLangSelects() {
  const langSel = $("ctlLang"), sttSel = $("ctlSttLang");
  langSel.innerHTML = ""; sttSel.innerHTML = `<option value="">Auto (match language)</option>`;
  for (const l of LANGS) {
    langSel.add(new Option(`${l.native} · ${l.en}`, l.code));
    sttSel.add(new Option(`${l.native} · ${l.en}`, l.code));
  }
}
fillLangSelects();

function setLanguage(code) {
  if (!LANG_BY_CODE[code]) return;
  settings.lang = code; saveSettings();
  $("ctlLang").value = code;
  $("stageLangChip").textContent = langLabel(code);
  document.querySelectorAll(".voice-card").forEach(c =>
    c.classList.toggle("is-selected", c.dataset.lang === code));
  scheduleReconnect();
}

function syncControls() {
  $("ctlLang").value = settings.lang;
  $("ctlSttLang").value = settings.sttLang;
  $("sttHint").textContent = settings.sttLang ? langLabel(settings.sttLang) : "auto";
  $("ctlEndpoint").value = settings.endpoint;
  $("endpointOut").textContent = `${Number(settings.endpoint).toFixed(2)} s`;
  $("ctlBackchannel").checked = settings.backchannel;
  $("ctlStreaming").checked = settings.streaming;
  $("ctlToken").value = settings.token;
  $("ctlVolume").value = settings.volume;
  $("volumeOut").textContent = `${settings.volume}%`;
  $("ctlMicGain").value = settings.micGain;
  $("micGainOut").textContent = `${Number(settings.micGain).toFixed(1)}×`;
  $("ctlVizStyle").value = settings.vizStyle;
  $("ctlVizIntensity").value = settings.vizIntensity;
  $("vizIntensityOut").textContent = `${settings.vizIntensity}%`;
  $("ctlParticles").checked = settings.particles;
  $("stageLangChip").textContent = langLabel(settings.lang);
  viz.style = settings.vizStyle;
  viz.intensity = settings.vizIntensity / 100;
  viz.particlesOn = settings.particles;
}
syncControls();

$("ctlLang").onchange = e => setLanguage(e.target.value);
$("ctlSttLang").onchange = e => {
  settings.sttLang = e.target.value; saveSettings();
  $("sttHint").textContent = settings.sttLang ? langLabel(settings.sttLang) : "auto";
  scheduleReconnect();
};
$("ctlEndpoint").oninput = e => {
  settings.endpoint = Number(e.target.value);
  $("endpointOut").textContent = `${settings.endpoint.toFixed(2)} s`;
  saveSettings();
};
$("ctlEndpoint").onchange = scheduleReconnect;
$("ctlBackchannel").onchange = e => { settings.backchannel = e.target.checked; saveSettings(); scheduleReconnect(); };
$("ctlStreaming").onchange = e => { settings.streaming = e.target.checked; saveSettings(); scheduleReconnect(); };
$("ctlToken").oninput = e => { settings.token = e.target.value.trim(); saveSettings(); };
$("ctlToken").onchange = scheduleReconnect;

$("ctlVolume").oninput = e => {
  settings.volume = Number(e.target.value);
  $("volumeOut").textContent = `${settings.volume}%`;
  saveSettings(); applyOutputVolume();
};
$("ctlMicGain").oninput = e => {
  settings.micGain = Number(e.target.value);
  $("micGainOut").textContent = `${settings.micGain.toFixed(1)}×`;
  if (engine.micGainNode && engine.ctx) {
    engine.micGainNode.gain.setTargetAtTime(settings.micGain, engine.ctx.currentTime, 0.05);
  }
  saveSettings();
};
$("ctlVizStyle").onchange = e => { settings.vizStyle = e.target.value; viz.style = e.target.value; saveSettings(); };
$("ctlVizIntensity").oninput = e => {
  settings.vizIntensity = Number(e.target.value);
  viz.intensity = settings.vizIntensity / 100;
  $("vizIntensityOut").textContent = `${settings.vizIntensity}%`;
  saveSettings();
};
$("ctlParticles").onchange = e => { settings.particles = e.target.checked; viz.particlesOn = e.target.checked; saveSettings(); };

$("resetSettings").onclick = () => {
  const token = settings.token;
  Object.assign(settings, DEFAULTS, { token });
  saveSettings(); syncControls(); renderMute(); applyOutputVolume();
  document.querySelectorAll(".voice-card").forEach(c =>
    c.classList.toggle("is-selected", c.dataset.lang === settings.lang));
  scheduleReconnect();
  toast("Controls reset to defaults.", "ok");
};

$("randomLang").onclick = () => {
  const ready = healthData
    ? LANGS.filter(l => healthData.voices?.[l.code]?.ready)
    : LANGS;
  const pool = ready.length ? ready : LANGS;
  const pick = pool[Math.floor(Math.random() * pool.length)];
  setLanguage(pick.code);
  toast(`Surprise: ${pick.native} · ${pick.en}! Start the call and speak it.`, "info");
};

/* ---------------- keyboard ---------------- */

document.addEventListener("keydown", e => {
  const tag = e.target.tagName;
  if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || tag === "BUTTON" || e.target.isContentEditable) return;
  if (e.code === "Space") { e.preventDefault(); engine.running ? stopCall() : startCall(); }
  else if (e.key === "m" || e.key === "M") $("masterMute").click();
});

/* ---------------- scroll spy ---------------- */

const spy = new IntersectionObserver(entries => {
  for (const en of entries) {
    if (en.isIntersecting) {
      document.querySelectorAll(".nav-link").forEach(a =>
        a.classList.toggle("is-active", a.dataset.section === en.target.id));
    }
  }
}, { rootMargin: "-35% 0px -55% 0px" });
["studio", "voices", "telemetry"].forEach(id => spy.observe($(id)));

/* ---------------- boot ---------------- */

fetchHealth();
setInterval(fetchHealth, 45000);
Object.values(METRICS).forEach(drawSpark);
window.addEventListener("resize", () => Object.values(METRICS).forEach(drawSpark));
updateSessionStats();

if (!window.isSecureContext) {
  toast("Microphone needs a secure context — open via 127.0.0.1 or run start_voice_phone.bat (HTTPS).", "warn", { ms: 9000 });
}

/* small hook for automated QA */
window.__iv = {
  engine, settings, handleEvent, playChunk, setState, messages, session, viz,
  vizFrame, drawOrb, drawBars, drawRings, startCall, stopCall, setLanguage,
  fetchHealth, addMessage, toast, applyOutputVolume, flushPlayback,
};