"""Download the ONNX models used by the local engine.

Usage (from the project root, inside the venv)::

    python -m src.download_models --langs hi gu             # voices + ASR
    python -m src.download_models --langs mr ta bn          # add more languages
    python -m src.download_models --all                     # everything (12 languages)
    python -m src.download_models --vad --stt               # VAD + Whisper

Each language is ~110 MB of TTS plus ~130 MB of IndicConformer ASR.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config


def _fetch(repo_id: str, filename: str, dest_dir: Path, name: str | None = None) -> Path:
    """Download one file from the Hub into ``dest_dir`` (flattened)."""
    from huggingface_hub import hf_hub_download

    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / (name or Path(filename).name)
    if target.exists() and target.stat().st_size > 0:
        print(f"  = {target.relative_to(config.PROJECT_ROOT)} (already present)")
        return target

    print(f"  + {target.relative_to(config.PROJECT_ROOT)}")
    downloaded = Path(hf_hub_download(repo_id=repo_id, filename=filename, local_dir=str(dest_dir)))
    if downloaded != target:
        downloaded.replace(target)
        parent = downloaded.parent
        while parent != dest_dir and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    return target


def _patch_onnx_metadata(path: Path, values: dict[str, str], tokens_path: Path | None = None) -> None:
    """Add the NeMo metadata keys sherpa-onnx needs to load a converted model.

    ``vocab_size: "auto"`` means "count the lines in the tokens file", which is
    what per-language IndicConformer exports need.
    """
    try:
        import onnx
    except ImportError:  # pragma: no cover
        print("  ! `onnx` is needed to patch model metadata:  pip install onnx")
        raise

    resolved = dict(values)
    if resolved.get("vocab_size") == "auto":
        if tokens_path is None or not tokens_path.exists():
            raise FileNotFoundError(f"cannot infer vocab_size without {tokens_path}")
        lines = [ln for ln in tokens_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        resolved["vocab_size"] = str(len(lines))
        print(f"  i vocab_size counted from tokens: {resolved['vocab_size']}")

    model = onnx.load(str(path), load_external_data=False)
    present = {p.key for p in model.metadata_props}
    missing = {k: v for k, v in resolved.items() if k not in present}
    complete = not missing and all(
        next((p.value for p in model.metadata_props if p.key == k), None) == v
        for k, v in resolved.items()
    )
    if complete:
        print("  = ONNX metadata already complete")
        return

    for prop in model.metadata_props:
        if prop.key in resolved:
            prop.value = resolved[prop.key]
    for key, value in missing.items():
        entry = model.metadata_props.add()
        entry.key, entry.value = key, value

    tmp = path.with_name(path.name + ".tmp")
    onnx.save(model, str(tmp))
    tmp.replace(path)
    print(f"  ~ patched ONNX metadata: {sorted(resolved)}")


def download_tts(lang: str) -> None:
    spec = config.TTS_MODELS[lang]
    dest = config.tts_model_dir(lang)
    print(f"[TTS:{lang}] {spec['repo']} / {spec['subfolder']}")
    _fetch(spec["repo"], f"{spec['subfolder']}/model.onnx", dest, "model.onnx")
    _fetch(spec["repo"], f"{spec['subfolder']}/tokens.txt", dest, "tokens.txt")


#: Supertonic 3 ships as a single archive on the sherpa-onnx releases page.
SUPERTONIC_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2"
)


def download_supertonic() -> None:
    """Fetch the Supertonic 3 voice (natural Hindi/English, 10 speakers, 139 MB)."""
    if config.supertonic_available():
        print(f"[TTS:supertonic] {config.SUPERTONIC_DIR.name} (already present)")
        return

    import tarfile
    import tempfile
    import urllib.request

    print("[TTS:supertonic] 139 MB archive from the sherpa-onnx releases")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "supertonic.tar.bz2"
        urllib.request.urlretrieve(SUPERTONIC_URL, archive)  # noqa: S310 - fixed https URL
        with tarfile.open(archive, "r:bz2") as tar:
            tar.extractall(config.MODELS_DIR, filter="data")
    print(f"  + {config.SUPERTONIC_DIR.relative_to(config.PROJECT_ROOT)}")


def download_tiny(lang: str) -> None:
    """Fetch the Indic Tiny TTS voice for ``lang`` (ONNX, ~90 MB, 24 kHz)."""
    dest = config.TINY_DIRS[config.resolve_lang(lang)]
    if (dest / "onnx" / "text_encoder.onnx").exists():
        print(f"[tiny:{lang}] {dest.name} (already present)")
        return
    from huggingface_hub import snapshot_download

    repo = config.TINY_REPOS[config.resolve_lang(lang)]
    print(f"[tiny:{lang}] {repo}")
    snapshot_download(repo, ignore_patterns=["*.safetensors", "assets/*"], local_dir=str(dest))


def download_indic_asr(lang: str) -> None:
    if not config.has_indic_asr(lang):
        print(f"[ASR:{lang}] no IndicConformer export, Whisper will be used")
        return
    spec = config.INDIC_ASR[lang]
    dest = config.indic_asr_dir(lang)
    print(f"[ASR:{lang}] {spec['repo']}")
    # Some repos keep one folder per language (``as/model.int8.onnx``) and share a
    # single token file, so the local name and the remote path can differ.
    remote = spec.get("remote") or {}
    for key, filename in spec["files"].items():
        _fetch(spec["repo"], remote.get(key, filename), dest, name=filename)
    patch = spec.get("patch_metadata")
    if patch:
        _patch_onnx_metadata(
            config.indic_asr_model(lang),
            patch,
            tokens_path=config.indic_asr_tokens(lang),
        )


def download_vad() -> None:
    print(f"[VAD] {config.VAD_REPO} / {config.VAD_FILE}")
    _fetch(config.VAD_REPO, config.VAD_FILE, config.MODELS_DIR)


def download_stt(model: str = config.DEFAULT_STT_MODEL) -> None:
    spec = config.STT_MODELS[model]
    print(f"[STT] {spec['repo']} (whisper-{model})")
    for part in ("encoder", "decoder", "tokens"):
        path = config.stt_file(model, part)
        _fetch(spec["repo"], path.name, config.stt_model_dir(model))


def missing(langs: list[str], stt_models: list[str] | None = None) -> list[str]:
    """Report which artefacts are still absent (used by the other modules)."""
    gaps = []
    for lang in langs:
        d = config.tts_model_dir(lang)
        if not (d / "model.onnx").exists() or not (d / "tokens.txt").exists():
            gaps.append(f"TTS {lang}: {d}")
        if config.has_indic_asr(lang) and not config.indic_asr_model(lang).exists():
            gaps.append(f"ASR {lang}: {config.indic_asr_dir(lang)}")
    if not config.VAD_PATH.exists():
        gaps.append(f"VAD: {config.VAD_PATH}")
    for model in stt_models or []:
        if not config.stt_file(model, "encoder").exists():
            gaps.append(f"STT {model}: {config.stt_model_dir(model)}")
    return gaps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download sherpa-onnx models for the Indic voice engine")
    parser.add_argument("--langs", nargs="*", default=None,
                        help="languages to fetch, e.g. --langs hi gu mr ta")
    parser.add_argument("--tts", nargs="*", default=None, help="alias for --langs (voices only)")
    parser.add_argument("--all-tts", action="store_true", help="fetch every TTS voice (12 languages)")
    parser.add_argument("--supertonic", action="store_true",
                        help="fetch the Supertonic 3 voice (natural Hindi/English, 139 MB)")
    parser.add_argument("--tiny", action="store_true",
                        help="fetch the Indic Tiny TTS voices (best quality + speed, ~90 MB per language)")
    parser.add_argument("--vad", action="store_true", help="fetch Silero VAD")
    parser.add_argument("--stt", nargs="?", const="both", default=None,
                        choices=["tiny", "base", "both"], help="fetch Whisper INT8 for STT")
    parser.add_argument("--indic-asr", nargs="*", default=None,
                        help="fetch IndicConformer ASR for these languages only")
    parser.add_argument("--no-asr", action="store_true", help="skip ASR when using --langs")
    parser.add_argument("--all", action="store_true", help="fetch everything")
    args = parser.parse_args(argv)

    langs = list(args.langs or args.tts or [])
    if args.all_tts or args.all:
        langs = list(config.TTS_MODELS)
    stt_models: list[str] = []
    if args.stt:
        stt_models = ["tiny", "base"] if args.stt == "both" else [args.stt]
    if args.all:
        stt_models = [config.DEFAULT_STT_MODEL]

    if not langs and not (args.vad or stt_models or args.all or args.supertonic
                          or args.tiny or args.indic_asr is not None):
        parser.print_help()
        print("\nNothing selected: pass --langs hi gu, or --vad --stt, or --all.")
        return 1

    langs = [config.resolve_lang(l) for l in dict.fromkeys(langs)]
    asr_langs = list(langs)
    if args.indic_asr is not None:
        asr_langs = [config.resolve_lang(l) for l in dict.fromkeys(args.indic_asr)] or list(config.INDIC_ASR)
    if args.no_asr:
        asr_langs = []

    if args.supertonic or args.all:
        download_supertonic()
    if args.tiny or args.all:
        for lang in (langs or list(config.TINY_DIRS)):
            download_tiny(lang)

    for lang in langs:
        download_tts(lang)
    for lang in asr_langs:
        download_indic_asr(lang)
    if args.vad or args.all:
        download_vad()
    for model in stt_models:
        download_stt(model)

    if not config.supertonic_available() and any(l in config.SUPERTONIC_LANGS for l in langs):
        print("\nTip: --supertonic adds the far more natural Hindi/English voice (139 MB).")

    gaps = missing(langs or ["hi"], stt_models)
    if gaps:
        print("\nStill missing:")
        for gap in gaps:
            print("  -", gap)
        return 1
    print("\nModels ready in", config.MODELS_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
