# IndicVoice — Latency Budget & Optimization Analysis (Real-World Validation V2, Phase F)

**Bottom line (honest):** On the reference laptop (i7-8565U, 4C/8T, 15 W) with the
synthetic starter corpus, **speculative streaming ASR is not a reliable perceived
end-to-end latency win.** Measured overlap savings are *negative at the median*:
streaming made calls slower more often than faster. The structural latency floor is
dominated by **LLM time-to-first-token and endpoint silence**, not by ASR decode time
— so hiding ASR work cannot, by itself, deliver large E2E gains. No production code
was changed in this phase; this is measurement + analysis only.

Status vocabulary: PASS (automated) / PASS — manually verified / PARTIAL / FAIL /
NOT TESTED / NOT APPLICABLE.

Evidence: `benchmarks/results/realworld_v2/latency_budget_v2.json` (full matrix),
`network_floor_v2.json` (Groq transport floor). Runner: `benchmarks/run_latency_budget.py`.

---

## 1. Method

Six conditions, 8 turns per language (hi, en), real server (real local ASR + Groq
LLM `openai/gpt-oss-20b` + real local TTS), real-time audio pacing:

| Condition | CPU spinners | Sessions | Streaming |
|---|---|---|---|
| idle1s | 0 | 1 | yes |
| idle1b | 0 | 1 | no (block) |
| mod1s | 2 | 1 | yes |
| high1s | 4 | 1 | yes |
| idle3s | 0 | 3 | yes |
| idle3b | 0 | 3 | no (block) |

8 s cooldown between conditions (thermal safety). Server RSS peak **1000 MB**.

**Metric definitions (stages OVERLAP — never summed):**
- `e2e_client_ms` — last speech frame sent → first audio byte at client. What the
  caller experiences after they stop talking. Includes the endpoint-silence wait.
- `first_audio_ms` — server: end-of-speech → first audio emitted.
- `asr_ms` — endpoint → final transcript. `llm_ms` — speech_end → first LLM token
  (includes ASR). `tts_ms` — TTS start → first audio.
- Endpoint silence: **260 ms hi-family / 450 ms en** (`config.endpoint_for`).

**Three honesty caveats:**
1. **Corpus** is TTS-synthesized starter clips, not real human recordings. Results
   describe pipeline latency on this machine, not real-world acoustic robustness.
2. **Percentiles are not additive.** p50 of `e2e` ≠ p50(endpoint) + p50(asr) +
   p50(llm) + p50(tts); each percentile is computed independently across turns.
3. **CPU-load conditions starve the measurement client too.** The spinner threads
   run in the benchmark driver process, so under mod/high load `e2e_client_ms`
   reflects whole-machine scheduling contention (client + server), not isolated
   server degradation. Server-side `first_audio_ms` is the cleaner signal there.

## 2. Results (p50 / p95, ms)

| Condition | Lang | e2e p50 | e2e p95 | asr p50 | llm p50 | tts p50 | first_audio p50 | ASR strategy | failed |
|---|---|---|---|---|---|---|---|---|---|
| idle1s | hi | 1567.4 | 3104.5 | 393.6 | 1002.8 | 203.9 | 1236.0 | full×5, spec×3 | 0 |
| idle1b | hi | 1109.3 | 2083.8 | 130.1 | 549.9 | 199.6 | 802.2 | block×8 | 0 |
| idle1s | en | 1310.1 | 1484.6 | 537.8 | 1094.8 | 84.8 | 1185.5 | cloud×8 | 0 |
| idle1b | en | 1237.3 | 1430.8 | 525.6 | 1001.1 | 61.9 | 1069.8 | block×8 | 0 |
| mod1s | hi | 1758.7 | 2530.0 | 0.4 | 429.1 | 192.6 | 611.9 | spec×8 | 0 |
| mod1s | en | 1540.7 | 1827.3 | 514.8 | 1017.6 | 54.4 | 1090.7 | cloud×8 | 0 |
| high1s | hi | 2901.4 | 5880.7 | 0.5 | 503.7 | 155.2 | 698.4 | spec×8 | 0 |
| high1s | en | 2096.3 | 2858.3 | 485.3 | 1026.4 | 107.7 | 1164.3 | cloud×8 | 0 |
| idle3s | hi | 1775.3 | 2745.7 | 305.1 | 1213.4 | 224.2 | 1469.4 | full×4, spec×4 | 0 |
| idle3b | hi | 1300.0 | 2156.5 | 197.3 | 636.8 | 334.1 | 946.7 | block×8 | 0 |
| idle3s | en | 1562.2 | 2776.4 | 481.6 | 1054.3 | 124.4 | 1438.4 | cloud×8 | 0 |
| idle3b | en | 1188.2 | 2112.2 | 467.8 | 887.1 | 101.6 | 988.3 | block×8 | 0 |

Zero failed turns in every condition. All 12 language routes preserved; hi/en measured.

## 3. Overlap savings — the central finding

`asr_time_hidden` = block.asr_ms − stream.asr_ms (decode work overlapped with silence).
`perceived_e2e_saved` = block.e2e − stream.e2e (what the caller actually gains).
Paired by (lang, clip), n=16 per session count.

| Sessions | asr_hidden p50 | asr_hidden mean | perceived_saved p50 | perceived_saved mean | perceived p90 | perceived p95 |
|---|---|---|---|---|---|---|
| 1 | **−112.3** | −226.6 | **−171.9** | −233.4 | +287.5 | +326.6 |
| 3 | +21.3 | −195.0 | **−530.3** | −519.0 | +962.9 | +1142.9 |

**Interpretation:** at the median, streaming *added* latency (negative savings). The
positive p90/p95 tails show it *can* help substantially on individual turns — but the
distribution is high-variance and net-negative overall on this machine/corpus. Even
`asr_time_hidden` is negative at p50 for 1 session: on "full"-strategy turns a wasted
speculative/partial decode ran *and* a fresh authoritative decode was still needed.

This directly confirms the V1 assessment caution: **lower ASR time ≠ equal E2E
improvement.** The gap between hidden ASR work and perceived gain is LLM TTFT + TTS
first-clause, which speculative ASR cannot reduce.

## 4. Why streaming underperforms here

1. **Speculative hit rate is the dominant factor.** idle1s hi hit only 3/8
   (5 "full" misses) → asr p50 393.6 ms and e2e *worse* than block. When the
   speculative decode does not finish inside the silence window, the turn pays for
   both the wasted decode and a fresh one.
2. **Partial-decode lock contention.** Background partials hold the single engine
   lock; on short utterances they can queue ahead of the authoritative decode.
3. **CPU starvation.** Under 2/4 spinners, hi speculative hits 8/8 and server-side
   asr→~0.5 ms, first_audio stays ~610–700 ms, yet client e2e balloons to 1758/2901 ms
   — the residual is scheduling delay on the saturated 4-core machine (client included).
4. **en cloud path gets no speculation.** Groq Whisper (`cloud` strategy) cannot be
   hidden during silence; streaming only adds finalize overhead (idle en 1310 vs block 1237).

## 5. Structural floor decomposition

Even with *perfect* ASR hiding (asr→0), the irreducible floor is:
`endpoint_silence + LLM_TTFT + TTS_first_clause + transport`.

| Lang | Endpoint | LLM TTFT (idle block p50) | TTS first clause | ASR hideable? | Approx floor |
|---|---|---|---|---|---|
| hi | 260 | ~550 | ~200 | yes (local) | **~1.0 s** |
| en | 450 | ~1000 | ~60–120 | **no** (cloud, ~500 ms round trip) | **~1.2–1.3 s** |

- **hi:** local ASR is hideable, but LLM TTFT (~550 ms) + TTS (~200 ms) + endpoint
  (260 ms) remain. Block idle hi first_audio p50 802 ms ≈ this floor.
- **en:** dominated by **two cloud round trips** — Groq ASR (~500 ms) + Groq LLM TTFT
  (~1000 ms). Speculative ASR cannot touch the cloud ASR leg. Network floor to
  api.groq.com measured separately: TCP ~70 ms, TLS ~97 ms median (median TCP+TLS
  ~174.6 ms; one 1253 ms cold outlier) — see `network_floor_v2.json`.

**Conclusion:** the biggest levers are LLM TTFT and (for en) the cloud ASR round trip,
not ASR decode optimization. Endpoint silence is a fixed UX/accuracy trade-off.

## 6. Optimization alternatives (analysis only — NOT applied to production)

Each option assessed for latency gain, accuracy impact, CPU, cost, complexity, risk.
**No production change was made.** Endpoint values were **not** lowered for benchmarks.

| # | Alternative | Latency gain | Accuracy / UX impact | CPU | Cost | Complexity | Risk |
|---|---|---|---|---|---|---|---|
| 1 | Shorter endpoint silence (e.g. hi 260→180) | −80 ms floor | Cuts off slow speakers / mid-utterance pauses → truncation | none | none | low | **high** (accuracy/UX); do not lower just for benchmarks |
| 2 | Semantic EOT prediction (model-based endpointing) | −100…200 ms when confident | False endpoints truncate; needs tuning per language | +model | none | high | medium-high |
| 3 | Faster / smaller LLM or lower reasoning effort | TTFT is dominant (~550–1000 ms); −200…500 ms possible | Quality regression risk; reasoning already `low` | varies | paid providers need authorization | medium | medium |
| 4 | Local ASR for en (replace Groq Whisper) | removes ~500 ms cloud ASR leg **and** enables en speculation | Local en accuracy must be validated; +CPU | +local decode | none (free model) | medium | medium |
| 5 | Gate/disable partials on short utterances | improves speculative hit rate → fewer "full" misses | none (final always full-buffer decode) | −wasted decodes | none | low-medium | low |
| 6 | Persistent / reused Groq connection (HTTP keep-alive) | saves per-turn TLS (~97 ms median) on cloud legs | none | none | none | medium | low |
| 7 | Earlier TTS first clause (finer sentence split) | tts ~200 ms hi; marginal first-clause gain | Prosody/clause-boundary artifacts | none | none | medium | low-medium |
| 8 | Client playback buffering / jitter reduction | reduces perceived stutter under load | adds playback delay if over-buffered | none | none | medium | low |
| 9 | Reduce CPU contention (fewer concurrent decodes) | large under load (residual ~900–1900 ms) | none | −peak | none | medium | low |

**Most promising, lowest-risk next investigations (still no production change):**
#5 (partial gating to raise speculative hit rate), #4 (local en ASR to remove a cloud
leg and unlock en speculation), #6 (connection reuse). #1 is explicitly discouraged
as a benchmark-driven shortcut.

## 7. Comparison to V1 reported baseline

| Metric | V1 reported (streaming, idle) | V2 idle1s | Note |
|---|---|---|---|
| hi e2e p50 | 1130.1 | 1567.4 | V2 worse; speculative hit 3/8 this run |
| hi e2e p95 | 2766.2 | 3104.5 | high run-to-run variance |
| en e2e p50 | 1264.2 | 1310.1 | comparable |
| en e2e p95 | 2886.6 | 1484.6 | V2 tighter this run |

Run-to-run variance on this 15 W laptop is large (thermal/scheduling). The V1
baseline was **not exactly reproduced**; V2 numbers are an independent measurement,
not a confirmation. The V1 claim of near-zero perceived ASR latency holds only when
the speculative decode hits — which is not the median case here.

## 8. Acceptance gate (performance)

**PARTIAL** — full latency budget measured under controlled idle/moderate/high CPU,
1 and 3 sessions, warm server, streaming and block; overlap savings and structural
floor quantified honestly. Cold-start and higher concurrency are covered in Phase G.
The gate is not PASS because (a) corpus is synthetic, (b) streaming shows no reliable
median E2E gain on this hardware, and (c) real-recording latency is NOT TESTED.