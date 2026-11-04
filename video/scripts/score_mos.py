"""Objective TTS-naturalness scoring (no human listener required).

Predicts a 1-5 MOS for each audio file using UTMOS (UTokyo-SaruLab, the VoiceMOS Challenge 2022
winning naturalness predictor) via torch.hub `tarepan/SpeechMOS` 'utmos22_strong'. This is the gate
we loop our voice-config tuning against: keep tuning until the narration crosses a human-grade MOS.

Rough scale (UTMOS): real human speech ~3.9-4.3 · top TTS ~3.8-4.2 · noticeably robotic ~3.0-3.5.

Usage:
  python score_mos.py audio1.mp3 audio2.wav ...        # print MOS per file
  python score_mos.py --json audio1.mp3 ...            # JSON {file: mos}
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf
import torch

_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = torch.hub.load("tarepan/SpeechMOS", "utmos22_strong", trust_repo=True)
        _MODEL.eval()
    return _MODEL


def _to_wav16k(src: pathlib.Path) -> pathlib.Path:
    out = pathlib.Path(tempfile.gettempdir()) / f"_mos_{src.stem}_16k.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return out


def score(src: pathlib.Path) -> float:
    wav, _sr = sf.read(str(_to_wav16k(src)))
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    tensor = torch.from_numpy(wav.astype(np.float32)).unsqueeze(0)
    with torch.no_grad():
        mos = model()(tensor, 16000)
    return float(mos.item())


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv
    results: dict[str, float] = {}
    for f in args:
        p = pathlib.Path(f)
        try:
            results[p.name] = round(score(p), 3)
        except Exception as e:  # noqa: BLE001 - report and continue
            results[p.name] = None  # type: ignore[assignment]
            if not as_json:
                sys.stderr.write(f"ERR {p.name}: {e}\n")
    if as_json:
        print(json.dumps(results))
    else:
        for name, mos in sorted(results.items(), key=lambda kv: (kv[1] is None, -(kv[1] or 0))):
            print(f"{mos if mos is not None else 'ERR':>6}  {name}")
