# Speak-check evidence bundle

Open `report.md` first. `audio/` holds every rendered clip (24 kHz mono PCM16 wav),
named `<lang>_<NN>_r<take>.wav`; `results.json` is the machine-readable report.

What this is: a local, CPU-only measurement of whether the production voice renders
audible, intelligible speech in each of the 12 languages, using the same
`render_sentence` path the live server plays, with several takes per sentence
because synthesis is non-deterministic.

What this is NOT: real-caller evidence, a MOS study, or a production-readiness claim.
The audio is synthesised by the engine under test, so the ASR round-trip flatters the
result. Human listening has not been performed, and objective hiss detection is not
claimed.

To listen: play the wavs in `audio/`. Each sentence has multiple takes; compare them.
The report's CER/WER columns only say whether a local recogniser recovered the
reference words, not whether the voice sounds natural.

Reproduce: `.venv313/Scripts/python.exe eval/speak_check.py` (writes a new run dir).
