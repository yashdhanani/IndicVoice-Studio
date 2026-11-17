# Live-server smoke test — hi_01.wav, 2026-11-17

Server: `python -m src.call_server --port 8010 --warm hi` (current code, all audit fixes applied)
Client: `python tools/smoke_streaming.py eval_data/hi_01.wav hi http://127.0.0.1:8010`
Real local ASR (IndicConformer hi) + tiny TTS + configured Groq LLM. Same recording both modes.

## streaming

```
partial: ध्यवा
partial: वा
partial: मेरा र्डर नंबर
partial: मेरा ऑर्डर नंबर एक दो
partial: मेरा र्डर नंबर एक दो तीन है
partial: मेरा ऑर्डर नंबर एक दो तीन है
transcript: मेरा ऑर्डर नंबर एक दो तीन है  (asr=353.6ms mode=streaming strategy=full)
reply: ठीक है, मैं आपके ऑर्डर 123 के बारे में जाँच करता हूँ।
latency: asr_ms=353.6 llm_ms=786.4 tts_ms=267.5 first_audio_ms=1073.5
audio back: 267970 bytes
```

## block

```
transcript: मेरा ऑर्डर नंबर एक दो तीन है  (asr=202.8ms mode=block strategy=-)
reply: धन्यवाद, 123 नंबर का ऑर्डर मिला।
latency: asr_ms=202.8 llm_ms=579.6 tts_ms=128.2 first_audio_ms=720.9
audio back: 226668 bytes
```

## Observations

- Final transcripts identical in both modes (accuracy parity holds live, not just in eval).
- Live partials appear during speech; early partials are fragmentary ("ध्यवा") — expected
  for a growing-buffer decode; they are captions only and never feed the final transcript.
- This recording contains a mid-utterance pause: the speculative decode was invalidated
  (visible as partial text restarting), post-miss suppression engaged, and finalize fell
  back to the conservative "full" strategy. On this turn streaming ASR was slower than
  block (353.6 vs 202.8 ms) — the safety mechanisms trade latency for accuracy on
  pause-heavy utterances. The eval A/B (clean utterances) shows hi streaming p50 = 0 ms.
- LLM/TTS latency differs between runs because the LLM produced different replies;
  first_audio_ms is not comparable across different reply lengths.