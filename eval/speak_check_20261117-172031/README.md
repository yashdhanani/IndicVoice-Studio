# Speak-check evidence bundle

Open `report.md` first, then `listen.html` in a browser (it plays the wavs in
`audio/` next to it, grouped by language and sentence, with the reference text,
what the local recogniser heard, and per-take scores). `results.json` is the
machine-readable report.

Clips are named `<lang>_<NN>_r<take>.wav` (24 kHz mono PCM16). Every sentence has
several takes because synthesis is non-deterministic — compare them.

What this is: a local, CPU-only measurement of whether the production voice renders
audible, intelligible speech in each of the 12 languages, using the same
`render_sentence` path the live server plays.

What this is NOT: real-caller evidence, a MOS study, or a production-readiness claim.
The audio is synthesised by the engine under test, so the ASR round-trip flatters the
result. Human listening has not been performed, and objective hiss detection is not
claimed.

To listen: use `listen.html`, or play the wavs directly. The CER/WER columns only say
whether a local recogniser recovered the reference words, not whether the voice
sounds natural.

Reproduce: `.venv313/Scripts/python.exe eval/speak_check.py` (writes a new run dir).
