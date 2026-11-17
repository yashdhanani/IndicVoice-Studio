"""Real-time voice-calling server: browser WebSocket + telephony mu-law.

Run it::

    python -m src.call_server --port 8000
    # then open http://127.0.0.1:8000 in a browser (mic + speaker call)

Two sockets are exposed:

``/ws/voice``
    Browser audio. The client sends raw **16 kHz PCM16 little-endian** frames and
    receives the same back. JSON text frames carry events
    (``{"type": "transcript" | "reply" | "state" | "flush"}``).

``/ws/telephony``
    Twilio/Exotel-style media stream: JSON frames with base64 **8 kHz mu-law**
    in ``media.payload``; replies come back in the same shape, plus ``flush``.

Internally everything is 16 kHz float32; the telephony edge converts to 8 kHz
mu-law and back. Speaker bleed is gated (frames are silenced while the agent is
talking unless they are clearly louder than the expected echo) and sustained
user speech (0.45 s by default) cancels playback.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hmac
import json
import math
import queue
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from scipy import signal

from . import config
from .config import SAMPLE_RATE, TELEPHONY_RATE, resolve_lang
from .sts_pipeline import (
    VAD_WINDOW,
    VAD_WINDOW_SECONDS,
    AgentConfig,
    LLMClient,
    VoiceAgent,
    _clean_transcript,
)
from .streaming_stt import StreamingSTT

# --------------------------------------------------------------------------- #
# Codecs
# --------------------------------------------------------------------------- #

_ULAW_BIAS = 0x84
_ULAW_CLIP = 32635


def pcm16_to_float(data: bytes) -> np.ndarray:
    """Little-endian PCM16 bytes -> float32 in [-1, 1]."""
    if len(data) % 2:
        data = data[:-1]
    return (np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0)


def float_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    return (clipped * 32767).astype("<i2").tobytes()


def ulaw_decode(data: bytes) -> np.ndarray:
    """G.711 mu-law bytes -> float32 in [-1, 1]."""
    u = ~np.frombuffer(data, dtype=np.uint8).astype(np.int32) & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    magnitude = (((mantissa << 3) + _ULAW_BIAS) << exponent) - _ULAW_BIAS
    samples = np.where(sign != 0, -magnitude, magnitude).astype(np.float32)
    return samples / 32768.0


def _authorised(params: dict) -> bool:
    """Reject callers that do not present the configured token (if one is set)."""
    token = config.ACCESS_TOKEN
    return not token or hmac.compare_digest(params.get("token") or "", token)


def ulaw_encode(samples: np.ndarray) -> bytes:
    """float32 in [-1, 1] -> G.711 mu-law bytes."""
    x = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0
    sign = np.where(x < 0, 0x80, 0).astype(np.int32)
    magnitude = np.minimum(np.abs(x).astype(np.int32), _ULAW_CLIP) + _ULAW_BIAS
    exponent = np.clip(np.floor(np.log2(np.maximum(magnitude, 1))).astype(np.int32) - 7, 0, 7)
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return ((~(sign | (exponent << 4) | mantissa)) & 0xFF).astype(np.uint8).tobytes()


def resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Polyphase resampling (8k <-> 16k <-> 48k)."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if src_rate == dst_rate or audio.size == 0:
        return audio
    divisor = math.gcd(int(src_rate), int(dst_rate))
    return signal.resample_poly(audio, dst_rate // divisor, src_rate // divisor).astype(np.float32)


def frame_audio(audio: np.ndarray, frame_samples: int) -> list[np.ndarray]:
    """Split ``audio`` into fixed-size frames (last one zero-padded)."""
    frames = []
    for start in range(0, len(audio), frame_samples):
        chunk = audio[start:start + frame_samples]
        if len(chunk) < frame_samples:
            chunk = np.pad(chunk, (0, frame_samples - len(chunk)))
        frames.append(chunk)
    return frames


# --------------------------------------------------------------------------- #
# WebSocket audio sink (drop-in replacement for AudioPlayer)
# --------------------------------------------------------------------------- #


class AudioSink:
    """Collects TTS audio and hands it to the socket without blocking playback.

    Same surface as :class:`src.tts_engine.AudioPlayer` so the TTS engine does
    not know or care that it is talking to a phone or a browser.
    """

    def __init__(self, emit, target_rate: int = SAMPLE_RATE, on_flush=None):
        self.target_rate = target_rate
        self.device_rate = target_rate
        self.device = None
        self._emit = emit
        self._on_flush = on_flush
        self._lock = threading.Lock()
        self._until = 0.0

    def push(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
        if samples is None or len(samples) == 0:
            return
        audio = resample(np.asarray(samples, dtype=np.float32), sample_rate, self.target_rate)
        with self._lock:
            self._emit(audio)                      # thread-safe send
            duration = audio.size / float(self.target_rate)
            self._until = max(self._until, time.monotonic() + duration)

    @property
    def is_speaking(self) -> bool:
        return time.monotonic() < self._until

    def wait_until_done(self, timeout: float | None = None, poll: float = 0.02) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.is_speaking:
            if deadline is not None and time.monotonic() > deadline:
                return False
            time.sleep(poll)
        return True

    def cancel(self) -> None:
        with self._lock:
            self._until = 0.0
            if self._on_flush is not None:
                self._on_flush()

    def close(self) -> None:
        self.cancel()


# --------------------------------------------------------------------------- #
# Call session
# --------------------------------------------------------------------------- #


class CallSession:
    """One live call: frames in, VAD, STT, LLM, streamed TTS frames out."""

    def __init__(
        self,
        websocket,
        loop: asyncio.AbstractEventLoop,
        mode: str = "browser",
        lang: str = "hi",
        stt_lang: str | None = None,
        echo_gate_db: float = -32.0,
        barge_in_seconds: float = 0.45,
        llm_factory=None,
        backchannel: bool = True,
        min_silence: float | None = None,
        llm_backend: str | None = None,
        llm_model: str | None = None,
        streaming: bool = True,
    ):
        self.ws = websocket
        self.loop = loop
        self.mode = mode
        self.echo_gate_db = echo_gate_db
        self.barge_in_seconds = barge_in_seconds
        self.out: queue.Queue = queue.Queue()
        self.closed = False
        self.streaming = streaming
        #: pre-onset audio so the streaming recogniser never misses the first word
        self._ring: deque = deque(maxlen=16)   # ~0.5 s at 32 ms per VAD window
        self._streaming_active = False

        self.sink = AudioSink(
            emit=self._emit_audio,
            target_rate=SAMPLE_RATE,
            on_flush=lambda: self._send_event({"type": "flush"}),
        )
        cfg = AgentConfig(
            lang=resolve_lang(lang),
            stt_lang=resolve_lang(stt_lang or lang),
            auto_lang=True,
            backchannel=backchannel,
            humanize=True,
            min_silence=min_silence or config.endpoint_for(lang),
            llm_backend=llm_backend,
            llm_model=llm_model,
        )
        self.streamer = StreamingSTT(
            on_partial=self._on_partial, endpoint_silence=cfg.min_silence
        )
        llm = llm_factory() if llm_factory else None
        self.agent = VoiceAgent(cfg, llm=llm, player=self.sink)
        # first-turn latency: open the LLM socket while the caller is still talking
        threading.Thread(
            target=getattr(self.agent.llm, "warm", lambda: None), daemon=True
        ).start()
        self.vad = self.agent._build_vad()          # noqa: SLF001 - same package
        self._speech_frames = 0
        self._inbuf = np.zeros(0, dtype=np.float32)
        #: set when a transcript is being answered, so the first audio chunk
        #: can report end-of-speech -> first-audio latency
        self._turn: dict | None = None
        #: bumped on every inbound frame / outbound audio, used by the idle watchdog
        self.last_activity = time.perf_counter()

    # -- outbound ----------------------------------------------------------- #

    def _emit_audio(self, audio: np.ndarray) -> None:
        if self.closed or audio.size == 0:
            return
        self.last_activity = time.perf_counter()
        turn, self._turn = self._turn, None
        if turn is not None:
            marks = dict(getattr(self.agent, "marks", {}) or {})
            now = time.perf_counter()
            llm_first = marks.get("llm_first")
            tts_start = marks.get("tts_start")
            self._send_event({
                "type": "latency",
                "asr_ms": round(turn["asr_ms"], 1),
                "llm_ms": round((llm_first - turn["t_speech_end"]) * 1000.0, 1) if llm_first else None,
                "tts_ms": round((now - tts_start) * 1000.0, 1) if tts_start else None,
                "first_audio_ms": round((now - turn["t_speech_end"]) * 1000.0, 1),
            })
        if self.mode == "telephony":
            audio = resample(audio, SAMPLE_RATE, TELEPHONY_RATE)
            payload = base64.b64encode(ulaw_encode(audio)).decode("ascii")
            self.out.put({"event": "media", "media": {"payload": payload}})
        else:
            self.out.put(float_to_pcm16(audio))

    def _send_event(self, event: dict) -> None:
        if not self.closed:
            self.out.put(event)

    def _on_partial(self, text: str) -> None:
        if self._streaming_active:
            self._send_event({"type": "partial_transcript", "text": text})

    async def sender(self) -> None:
        """Drain queued audio/events to the socket as fast as the client accepts."""
        while not self.closed:
            try:
                item = await asyncio.get_running_loop().run_in_executor(None, self._get_item, 0.2)
            except Exception:
                continue
            if item is None:
                continue
            try:
                if isinstance(item, dict):
                    if "media" in item:
                        for frame in self._telephony_frames(item["media"]["payload"]):
                            await self.ws.send_text(json.dumps(frame))
                    else:
                        await self.ws.send_text(json.dumps(item))
                else:
                    await self.ws.send_bytes(item)
            except Exception:
                self.closed = True
                return

    def _get_item(self, timeout: float):
        try:
            return self.out.get(timeout=timeout)
        except queue.Empty:
            return None

    @staticmethod
    def _telephony_frames(payload_b64: str, frame_ms: int = 20):
        """Split a mu-law payload into 20 ms frames (160 samples at 8 kHz)."""
        raw = base64.b64decode(payload_b64)
        step = TELEPHONY_RATE * frame_ms // 1000
        for start in range(0, len(raw), step):
            chunk = raw[start:start + step]
            if len(chunk) < step:
                chunk = chunk + b"\xff" * (step - len(chunk))
            yield {"event": "media", "media": {"payload": base64.b64encode(chunk).decode("ascii")}}

    # -- inbound ------------------------------------------------------------ #

    def _gate(self, frame: np.ndarray) -> np.ndarray:
        """Speaker-bleed gate: silence the mic while we talk unless it is loud."""
        if not self.agent.player.is_speaking or len(frame) == 0:
            return frame
        rms = float(np.sqrt(np.mean(np.square(frame)) + 1e-12))
        dbfs = 20.0 * math.log10(max(rms, 1e-9))
        if dbfs < self.echo_gate_db:
            return np.zeros_like(frame)
        return frame

    async def feed(self, samples16k: np.ndarray) -> None:
        """Buffer arbitrary client frames into exact VAD windows, then process."""
        chunk = np.asarray(samples16k, dtype=np.float32).reshape(-1)
        if chunk.size == 0:
            return
        self.last_activity = time.perf_counter()
        self._inbuf = np.concatenate([self._inbuf, chunk]) if self._inbuf.size else chunk
        while self._inbuf.size >= VAD_WINDOW:
            frame = self._inbuf[:VAD_WINDOW]
            self._inbuf = self._inbuf[VAD_WINDOW:]
            await self._process_frame(frame)

    async def _process_frame(self, frame: np.ndarray) -> None:
        """One 512-sample window: barge-in detection + VAD + transcription."""
        frame = self._gate(np.asarray(frame, dtype=np.float32).reshape(-1))
        if frame.size < VAD_WINDOW:
            return

        if self.agent.player.is_speaking and self.vad.is_speech_detected():
            self._speech_frames += 1
        else:
            self._speech_frames = 0
        if self._speech_frames * VAD_WINDOW_SECONDS >= self.barge_in_seconds:
            self._speech_frames = 0
            self.agent.cancel.set()
            self.agent.player.cancel()
            self._send_event({"type": "state", "value": "interrupted"})

        self.vad.accept_waveform(frame)
        if self.streaming:
            self._ring.append(frame)
            if not self._streaming_active and self.vad.is_speech_detected():
                self._streaming_active = True
                self.streamer.start(self.agent.stt, seed=np.concatenate(self._ring))
            elif self._streaming_active:
                # keep feeding through trailing silence: the last word's tail
                # can land in frames the VAD already classifies as silence
                self.streamer.accept(frame)
        while not self.vad.empty():
            segment = self.vad.front
            audio = np.asarray(segment.samples, dtype=np.float32).copy()
            self.vad.pop()
            if audio.size < int(0.3 * SAMPLE_RATE):
                if self._streaming_active:
                    self.streamer.cancel()
                    self._streaming_active = False
                continue
            speech_end = time.perf_counter()
            # decode off the event loop: STT takes 0.15-0.8 s on CPU
            asr_info = None
            try:
                if self._streaming_active:
                    recognised, asr_info = await self.loop.run_in_executor(
                        None, self.streamer.finalize
                    )
                else:
                    recognised = await self.loop.run_in_executor(
                        None, self.agent.stt.transcribe, audio
                    )
            except Exception as exc:                      # noqa: BLE001
                # a cloud-ASR timeout or decode error must not drop the call
                self._send_event({"type": "error", "stage": "asr",
                                  "message": str(exc)[:200]})
                continue
            finally:
                self._streaming_active = False
            text = _clean_transcript(recognised)
            if not text:
                continue
            asr_ms = (time.perf_counter() - speech_end) * 1000.0
            self._turn = {"t_speech_end": speech_end, "asr_ms": asr_ms}
            event = {"type": "transcript", "text": text, "asr_ms": round(asr_ms, 1)}
            if asr_info is not None:
                event["asr_mode"] = "streaming"
                event["asr_strategy"] = asr_info["strategy"]
            self._send_event(event)
            reply_lang = self.agent.maybe_switch_language(text)
            self._send_event({"type": "state", "value": "thinking", "lang": reply_lang})
            self.agent.start_response(
                text,
                reply_lang=reply_lang,
                # captions: the browser (and tests) can show what is being spoken
                on_sentence=lambda s: self._send_event(
                    {"type": "reply", "text": s, "lang": reply_lang, "partial": True}
                ),
            )

    def close(self) -> None:
        self.closed = True
        self.agent.cancel.set()
        self.streamer.close()
        try:
            self.agent.player.cancel()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# HTML client (browser call page)
# --------------------------------------------------------------------------- #

_INDEX_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>IndicVoice call</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#0f1116;color:#e8ecf3;
      display:flex;min-height:100vh;align-items:center;justify-content:center}
 main{width:min(680px,92vw)}
 h1{font-size:20px;font-weight:600;margin:0 0 4px}
 p{color:#93a1b5;font-size:14px;margin:6px 0 18px}
 button{background:#2f6df6;border:0;color:#fff;padding:12px 20px;border-radius:10px;
        font-size:15px;cursor:pointer}
 button.stop{background:#b03a3a}
 #log{background:#161a22;border-radius:10px;padding:14px;height:240px;overflow:auto;
      font-size:14px;line-height:1.5;margin-top:16px;white-space:pre-wrap}
 .you{color:#7fd1a6}.ai{color:#8fb8ff}.sys{color:#8b96a8}
</style></head><body><main>
<h1>IndicVoice — live call</h1>
<p>Speak any of the 12 supported languages. The assistant answers in the same language.</p>
<select id="lang" style="background:#161a22;color:#e8ecf3;border:1px solid #2a3240;border-radius:8px;padding:10px;font-size:14px;margin-right:8px">
 <option value="hi" selected>हिन्दी Hindi</option><option value="gu">ગુજરાતી Gujarati</option>
 <option value="mr">मराठी Marathi</option><option value="bn">বাংলা Bengali</option>
 <option value="ta">தமிழ் Tamil</option><option value="te">తెలుగు Telugu</option>
 <option value="kn">ಕನ್ನಡ Kannada</option><option value="ml">മലയാളം Malayalam</option>
 <option value="pa">ਪੰਜਾਬੀ Punjabi</option><option value="or">ଓଡ଼ିଆ Odia</option>
 <option value="as">অসমীয়া Assamese</option><option value="en">English</option>
</select>
<button id="go">Start call</button>
<div id="log"></div>
<script>
const log = (msg, cls="sys") => {
  const el = document.getElementById("log");
  const div = document.createElement("div");
  div.className = cls;
  div.textContent = msg;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
};
let ws, ctx, stream, node, playAt = 0, running = false;

async function start() {
  if (running) return stop();
  running = true;
  document.getElementById("go").textContent = "End call";
  document.getElementById("go").className = "stop";

  ctx = new AudioContext({sampleRate: 16000});
  stream = await navigator.mediaDevices.getUserMedia({audio: {
    echoCancellation: true, noiseSuppression: true, autoGainControl: true}});
  const src = ctx.createMediaStreamSource(stream);
  // AudioWorklet replaces the deprecated ScriptProcessorNode. The processor
  // batches 1024 samples on the audio thread, so the main thread only wakes
  // ~47 times a second instead of once per 128-sample block.
  const workletCode = `class MicProcessor extends AudioWorkletProcessor {
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
  const workletUrl = URL.createObjectURL(new Blob([workletCode], {type: "application/javascript"}));
  await ctx.audioWorklet.addModule(workletUrl);
  node = new AudioWorkletNode(ctx, "mic-processor");
  node.port.onmessage = (ev) => {
    if (!ws || ws.readyState !== 1) return;
    const src = ev.data;
    // Firefox and some Safari versions ignore the 16 kHz AudioContext request.
    // Sending 44.1/48 kHz audio as if it were 16 kHz makes every word unrecognisable,
    // so resample here whenever the context did not honour the rate.
    let f32 = src;
    if (Math.abs(ctx.sampleRate - 16000) > 1) {
      const n = Math.max(1, Math.round(src.length * 16000 / ctx.sampleRate));
      f32 = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const pos = i * ctx.sampleRate / 16000;
        const a = Math.floor(pos), b = Math.min(a + 1, src.length - 1);
        f32[i] = src[a] + (src[b] - src[a]) * (pos - a);
      }
    }
    const i16 = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) i16[i] = Math.max(-1, Math.min(1, f32[i])) * 32767;
    ws.send(i16.buffer);
  };
  const mute = ctx.createGain();
  mute.gain.value = 0;              // keep the graph alive without echoing the mic
  src.connect(node); node.connect(mute); mute.connect(ctx.destination);

  const lang = document.getElementById("lang").value;
  document.getElementById("lang").disabled = true;
  const token = new URLSearchParams(location.search).get("token") || "";
  const auth = token ? `&token=${encodeURIComponent(token)}` : "";
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/voice?lang=${lang}${auth}`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => log(`Call connected at ${ctx.sampleRate} Hz. Say something.`, "sys");
  ws.onclose = () => { log("Call ended.", "sys"); stop(); };
  ws.onmessage = (ev) => {
    if (typeof ev.data === "string") {
      const msg = JSON.parse(ev.data);
      if (msg.type === "transcript") log("you: " + msg.text, "you");
      else if (msg.type === "reply") log("ai: " + msg.text, "ai");
      else if (msg.type === "state") log("· " + msg.value, "sys");
      else if (msg.type === "flush") { playAt = ctx.currentTime; }
      return;
    }
    const i16 = new Int16Array(ev.data);
    const buf = ctx.createBuffer(1, i16.length, 16000);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 32768;
    const srcNode = ctx.createBufferSource();
    srcNode.buffer = buf; srcNode.connect(ctx.destination);
    playAt = Math.max(playAt, ctx.currentTime);
    srcNode.start(playAt);
    playAt += buf.duration;
  };
}
function stop() {
  running = false;
  document.getElementById("go").textContent = "Start call";
  document.getElementById("go").className = "";
  if (ws) { ws.close(); ws = null; }
  if (node) { node.disconnect(); node = null; }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  if (ctx) { ctx.close(); ctx = null; }
}
document.getElementById("go").onclick = start;
</script></main></body></html>"""


# --------------------------------------------------------------------------- #
# FastAPI app
# --------------------------------------------------------------------------- #


def create_app(
    agent_factory=None,
    default_endpoint: float | None = None,
    llm_backend: str | None = None,
    llm_model: str | None = None,
    streaming: bool = True,
):
    """Build the FastAPI app. ``agent_factory`` lets tests inject a stub LLM.

    Note: ``FastAPI``/``WebSocket`` must stay imported at module level. With
    ``from __future__ import annotations`` the handler annotations are resolved
    against module globals, and a function-local import makes FastAPI treat
    ``ws`` as a required query parameter (rejecting every handshake with 403).
    """
    app = FastAPI(title="IndicVoice call server")

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if (web_dir / "index.html").exists():
        app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/health")
    async def health():
        voices = {}
        for code in config.LANG_NAMES:
            backend = config.tts_backend(code)
            if backend == "tiny":
                ready = config.tiny_available(code)
            elif backend == "supertonic":
                ready = config.supertonic_available()
            else:
                ready = (config.tts_model_dir(code) / "model.onnx").exists()
            voices[code] = {
                "backend": backend,
                "ready": ready,
                "asr": config.has_indic_asr(code) or code == "en",
            }
        try:
            from .sts_pipeline import LLMClient

            probe = LLMClient()
            llm = {"backend": probe.backend, "model": probe.model, "ready": True}
        except Exception as exc:                          # noqa: BLE001 - report it
            llm = {"ready": False, "error": str(exc)[:200]}
        return JSONResponse({
            "ok": all(v["ready"] for v in voices.values()),
            "voices": voices,
            "supertonic": config.supertonic_available(),
            "llm": llm,
        })

    @app.get("/")
    async def index():
        page = web_dir / "index.html"
        if page.exists():
            return FileResponse(page, media_type="text/html")
        return HTMLResponse(_INDEX_HTML)

    def _endpoint(params: dict) -> float | None:
        """``?endpoint=0.3`` overrides the end-of-turn silence for one call."""
        raw = params.get("endpoint")
        try:
            value = float(raw) if raw is not None else None
        except ValueError:
            return None
        return value if value and 0.1 <= value <= 2.0 else None

    def _make_session(ws, mode: str, lang: str, stt_lang: str | None,
                      backchannel: bool = True,
                      min_silence: float | None = None,
                      streaming: bool = True) -> CallSession:
        loop = asyncio.get_running_loop()
        session = CallSession(
            ws, loop, mode=mode, lang=lang, stt_lang=stt_lang,
            llm_factory=agent_factory, backchannel=backchannel,
            min_silence=min_silence or default_endpoint,
            llm_backend=llm_backend, llm_model=llm_model,
            streaming=streaming,
        )
        asyncio.create_task(session.sender())

        async def watchdog() -> None:
            """Close sessions whose socket went quiet, so buffers are not held forever."""
            while not session.closed:
                await asyncio.sleep(5)
                if time.perf_counter() - session.last_activity > config.SESSION_IDLE_SECONDS:
                    session.close()
                    try:
                        await ws.close(code=4408)
                    except Exception:
                        pass
                    return

        asyncio.create_task(watchdog())
        return session

    @app.websocket("/ws/voice")
    async def voice(ws: WebSocket):
        await ws.accept()
        params = dict(ws.query_params)
        if not _authorised(params):
            await ws.close(code=4401)
            return
        session = _make_session(
            ws, "browser", params.get("lang", "hi"), params.get("stt_lang"),
            backchannel=params.get("backchannel", "1") != "0",
            min_silence=_endpoint(params),
            streaming=streaming and params.get("streaming", "1") != "0",
        )
        try:
            while True:
                message = await ws.receive()
                if message.get("bytes") is None:
                    if message.get("type") == "websocket.disconnect":
                        break
                    continue
                await session.feed(pcm16_to_float(message["bytes"]))
        except WebSocketDisconnect:
            pass
        finally:
            session.close()

    @app.websocket("/ws/telephony")
    async def telephony(ws: WebSocket):
        await ws.accept()
        params = dict(ws.query_params)
        if not _authorised(params):
            await ws.close(code=4401)
            return
        session = _make_session(
            ws, "telephony", params.get("lang", "hi"), params.get("stt_lang"),
            backchannel=params.get("backchannel", "1") != "0",
            min_silence=_endpoint(params),
            streaming=streaming and params.get("streaming", "1") != "0",
        )
        await ws.send_text(json.dumps({"event": "connected"}))
        try:
            while True:
                raw = await ws.receive_text()
                event = json.loads(raw)
                if event.get("event") in {"stop", "disconnect"}:
                    break
                payload = (event.get("media") or {}).get("payload")
                if not payload:
                    continue
                audio8k = ulaw_decode(base64.b64decode(payload))
                await session.feed(resample(audio8k, TELEPHONY_RATE, SAMPLE_RATE))
        except WebSocketDisconnect:
            pass
        finally:
            session.close()

    return app


app = create_app()


def warm_up(langs: tuple[str, ...] = ("hi", "en")) -> list[str]:
    """Load models before the first call so it does not pay startup cost.

    Voices and recognisers live in process-wide caches, so this is a one-off
    cost (~2-3 s) instead of a per-call delay. Filler clips are synthesised too,
    otherwise the first "हाँ जी..." would render on the critical path.
    """
    from .sts_pipeline import shared_stt
    from .tts_engine import TTSEngine

    warmed: list[str] = []
    for lang in dict.fromkeys(resolve_lang(l) for l in langs):
        try:
            if config.has_indic_asr(lang) or lang == "en":
                shared_stt("auto", lang, config.DEFAULT_STT_MODEL)
            engine = TTSEngine(lang)
            engine.humanizer.filler(lang)
            warmed.append(lang)
        except Exception as exc:                      # noqa: BLE001 - report, keep going
            print(f"[warm] {lang}: {exc}")
    if warmed:
        print(f"[warm] models ready: {', '.join(warmed)}")
    return warmed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Real-time IndicVoice call server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--lang", default="hi", help="default language for new calls")
    parser.add_argument("--llm-backend", default=None, choices=["ollama", "groq", "openai"],
                        help="default: groq when GROQ_API_KEY is set in .env, otherwise ollama")
    parser.add_argument("--llm-model", default=None,
                        help="e.g. llama-3.3-70b-versatile (groq) or llama3.2:3b (ollama)")
    parser.add_argument("--tls", action="store_true",
                        help="serve HTTPS with a local certificate; phones need this for microphone access")
    parser.add_argument("--cert", default=None, help="certificate PEM path (implies --tls)")
    parser.add_argument("--key", default=None, help="private key PEM path")
    parser.add_argument("--endpoint", type=float, default=config.ENDPOINT_SILENCE,
                        help="silence in seconds that ends a turn (default: %(default)s)")
    parser.add_argument("--warm", nargs="*", default=["hi", "en"],
                        help="languages to preload at startup (default: hi en)")
    parser.add_argument("--no-warm", action="store_true", help="skip startup warm-up")
    parser.add_argument("--no-streaming", action="store_true",
                        help="decode only after the caller stops speaking (block ASR)")
    args = parser.parse_args(argv)

    missing = [
        str(p) for p in (config.VAD_PATH, config.tts_model_dir(args.lang) / "model.onnx")
        if not Path(p).exists()
    ]
    if missing:
        print("Missing model files:", *missing, sep="\n  - ")
        print("Run:  python -m src.download_models --langs hi gu --vad")
        return 1

    import uvicorn

    app = create_app(
        default_endpoint=args.endpoint,
        llm_backend=args.llm_backend,
        llm_model=args.llm_model,
        streaming=not args.no_streaming,
    )

    try:
        from .sts_pipeline import LLMClient

        probe = LLMClient()
        print(f"[llm] {probe.backend} / {probe.model}")
    except Exception as exc:                              # noqa: BLE001 - report it
        print(f"[llm] not configured: {exc}")

    if not config._ORT_READY:                      # noqa: SLF001 - same package
        print(
            "[warn] onnxruntime is missing, so the natural 'tiny' voices are off.\n"
            "       Start the server with the Python 3.13 venv for best quality:\n"
            ".venv313\\Scripts\\python.exe -m src.call_server --port 8000"
        )
    if not args.no_warm:
        warm_up(tuple(args.warm or ()))

    ssl_args: dict = {}
    if args.tls or args.cert:
        if args.cert and args.key:
            cert_path, key_path = Path(args.cert), Path(args.key)
        else:
            from .tls_cert import ensure_certificate

            cert_path, key_path = ensure_certificate()
        ssl_args = {"ssl_certfile": str(cert_path), "ssl_keyfile": str(key_path)}

    scheme = "https" if ssl_args else "http"
    print(f"IndicVoice call server on {scheme}://{args.host}:{args.port}  (Ctrl+C to stop)")
    if config.ACCESS_TOKEN:
        print(f"  token required: open {scheme}://{args.host}:{args.port}/?token=<your-token>")
    elif args.host not in {"127.0.0.1", "localhost"}:
        print("  [warn] listening beyond localhost with no INDICVOICE_TOKEN - anyone on the")
        print("         network can use your LLM key. Set INDICVOICE_TOKEN in .env.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", **ssl_args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
