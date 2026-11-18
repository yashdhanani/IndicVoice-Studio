# 07 — Conversation Quality

## LLM

- Model: Groq `openai/gpt-oss-20b`, reasoning effort low (halves TTFT: 715→362 ms measured).
- Hard cap: MAX_REPLY_SENTENCES = 2 (phone replies).
- System prompt pinned to turn language + script rule + voice gender (VOICE_GENDER, default female).
- Keep-alive socket reused; fallback model list empty by default.

## Tested

- LLM script consistency check: 12/12 languages (benchmarks/run_llm_script_check) — reported in prior docs.
- Context retention / follow-ups / corrections: exercised by tests/test_ws_server with stub LLM (intent logic not deeply tested with real LLM).
- Language match of spoken response: enforced via prompt; not measured with human rubric.

## Not tested

- Intent understanding quality, hallucinations, factual correctness: NOT TESTED (no rubric).
- Gender agreement in Hindi/Marathi/Punjabi: implemented via prompt rule; not verified with human listening.
- Code-switching responses: NOT TESTED on real conversations.
- Multi-turn stability >20 turns: NOT TESTED.
- Conversation endings, clarifications: NOT TESTED with real users.

## Conclusion

Conversation plumbing (context, streaming, sentence splitting, language pinning) is implemented and unit/WS-tested with stubs. Semantic quality of real LLM responses is not human-verified. No claim of conversational intelligence beyond implementation.