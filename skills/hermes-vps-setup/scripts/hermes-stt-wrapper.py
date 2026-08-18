#!/usr/local/lib/hermes-agent/venv/bin/python
"""STT wrapper for Hermes: Groq primary (with chunking for >25MB), faster-whisper fallback.

Hermes calls this via stt.provider=local_command + HERMES_LOCAL_STT_COMMAND template:
  hermes-stt-wrapper.py <input> --output_dir <dir> --language <lang> --model <model>
Writes transcript to <output_dir>/transcript.txt and exits 0.

Env:
  STT_GROQ_API_KEY / GROQ_API_KEY  - Groq key (required for cloud path)
  STT_GROQ_MODEL                   - default whisper-large-v3-turbo
  STT_LOCAL_FALLBACK_MODEL         - faster-whisper model, default "base"
  STT_GROQ_TIMEOUT                 - seconds, default 60
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

GROQ_LIMIT = 25 * 1024 * 1024
TARGET_CHUNK_BYTES = 23 * 1024 * 1024
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_API_KEY = os.getenv("STT_GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("STT_GROQ_MODEL", "whisper-large-v3-turbo")
LOCAL_MODEL = os.getenv("STT_LOCAL_FALLBACK_MODEL", "base")
GROQ_TIMEOUT = int(os.getenv("STT_GROQ_TIMEOUT", "60"))


def log(*args):
    print("[hermes-stt]", *args, file=sys.stderr)


def ffprobe_duration_sec(path: str) -> int:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        text=True,
    ).strip()
    return max(0, int(float(out))) if out else 0


def groq_transcribe_one(file_path: str, model: str, language: str) -> str:
    url = f"{GROQ_BASE_URL}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    with open(file_path, "rb") as fh:
        files = {"file": (os.path.basename(file_path), fh, "application/octet-stream")}
        data = {"model": model}
        if language:
            data["language"] = language
        r = requests.post(url, headers=headers, files=files, data=data, timeout=GROQ_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Groq HTTP {r.status_code}: {r.text[:300]}")
    return (r.json().get("text") or "").strip()


def groq_transcribe(input_path: str, language: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    size = os.path.getsize(input_path)
    if size <= GROQ_LIMIT:
        log(f"Groq direct ({size//1024//1024}MB)")
        return groq_transcribe_one(input_path, GROQ_MODEL, language)

    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise RuntimeError("ffmpeg/ffprobe required for >25MB chunking")
    duration = ffprobe_duration_sec(input_path)
    if duration <= 0:
        raise RuntimeError("Cannot determine duration for chunking")
    bytes_per_sec = max(1, size // duration)
    chunk_secs = max(60, TARGET_CHUNK_BYTES // bytes_per_sec)
    chunks = math.ceil(duration / chunk_secs)
    log(f"Groq chunking: {duration}s / {chunk_secs}s = {chunks} chunks")

    parts = []
    with tempfile.TemporaryDirectory(prefix="groq-stt-") as td:
        for i in range(chunks):
            chunk_path = os.path.join(td, f"chunk_{i:03d}.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-i", input_path,
                 "-ss", str(i * chunk_secs), "-t", str(chunk_secs),
                 "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", chunk_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            )
            txt = groq_transcribe_one(chunk_path, GROQ_MODEL, language)
            if txt:
                parts.append(txt)
            log(f"  chunk {i+1}/{chunks} done")
    return " ".join(parts).strip()


def local_transcribe(input_path: str, language: str) -> str:
    log(f"Fallback: faster-whisper ({LOCAL_MODEL})")
    from faster_whisper import WhisperModel
    model = WhisperModel(LOCAL_MODEL, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(input_path, language=language or None, beam_size=1)
    return " ".join(seg.text.strip() for seg in segments).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--language", default="")
    ap.add_argument("--model", default="")
    args, _ = ap.parse_known_args()

    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        log("Input not found:", input_path)
        return 1

    text = ""
    try:
        text = groq_transcribe(input_path, args.language)
    except Exception as e:
        log(f"Groq failed: {e}")
        try:
            text = local_transcribe(input_path, args.language)
        except Exception as e2:
            log(f"Local fallback also failed: {e2}")
            return 1

    if not text:
        log("Empty transcript from both providers")
        return 1

    os.makedirs(args.output_dir, exist_ok=True)
    Path(args.output_dir, "transcript.txt").write_text(text, encoding="utf-8")
    log(f"OK: {len(text)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
