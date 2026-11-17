"""Wav2Vec2-style CTC recogniser running on onnxruntime (no PyTorch needed).

Feeds the ONNX export produced by ``colab/assamese_asr_export.ipynb``. The
notebook writes ``meta.json`` and ``tokens.json`` next to ``model.onnx``, so this
loader never has to guess at the model's preprocessing or vocabulary layout.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import config


def available(directory: Path | None = None) -> bool:
    """True when a usable CTC export is present on disk."""
    folder = Path(directory or config.ASR_CTC_DIR)
    return all(
        (folder / name).exists() for name in ("model.onnx", "tokens.json", "meta.json")
    )


class CtcRecognizer:
    """Greedy CTC decoding of a wav2vec2 ONNX graph."""

    def __init__(self, directory: Path | None = None, num_threads: int | None = None):
        import onnxruntime as ort

        folder = Path(directory or config.ASR_CTC_DIR)
        if not available(folder):
            raise FileNotFoundError(
                f"no CTC model in {folder}; run colab/assamese_asr_export.ipynb "
                "and extract the zip there"
            )
        self.directory = folder
        self.meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        self.tokens = json.loads((folder / "tokens.json").read_text(encoding="utf-8"))
        self.blank_id = int(self.meta.get("blank_id", 0))
        self.normalize = bool(self.meta.get("normalize", True))
        self.rate = int(self.meta.get("sample_rate", config.SAMPLE_RATE))
        self.delimiter = self.meta.get("word_delimiter", "|")

        options = ort.SessionOptions()
        options.intra_op_num_threads = int(num_threads or config.STT_NUM_THREADS)
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(folder / "model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

    def transcribe(self, samples: np.ndarray, sample_rate: int = config.SAMPLE_RATE) -> str:
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return ""
        if sample_rate != self.rate:
            n = max(1, int(len(audio) * self.rate / sample_rate))
            audio = np.interp(
                np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio
            )
        if self.normalize:
            audio = (audio - audio.mean()) / np.sqrt(audio.var() + 1e-7)

        logits = self.session.run(None, {self.input_name: audio[None, :]})[0]
        ids = logits.argmax(axis=-1)[0]

        pieces: list[str] = []
        previous = -1
        for index in ids:
            index = int(index)
            if index != previous and index != self.blank_id:
                pieces.append(self.tokens[index] if index < len(self.tokens) else "")
            previous = index
        text = "".join(pieces).replace(self.delimiter, " ")
        return " ".join(text.split())
