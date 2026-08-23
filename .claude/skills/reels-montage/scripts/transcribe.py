#!/usr/bin/env python3
"""
Расшифровка видео в текст с таймкодами по словам. Это вход для всего сложного монтажа:
по нему агент выбирает сильные куски, из него же делаются субтитры.

Работает локально, без ключей и без интернета — модель скачивается один раз
при первом запуске и дальше лежит в кэше.

  python3 transcribe.py video.mp4 > words.json
  python3 transcribe.py video.mp4 --model large-v3      # точнее, но медленнее
  python3 transcribe.py video.mp4 --groq                # через API, если есть GROQ_API_KEY

Модели: tiny, base, small, medium (по умолчанию), large-v3.
medium — золотая середина: русский разбирает хорошо, минута речи считается около минуты.
"""
import sys, os, json, subprocess, tempfile, urllib.request, uuid, argparse

MODEL_DEFAULT = "medium"


def log(msg):
    """Всё служебное — в stderr, чтобы stdout остался чистым JSON."""
    print(msg, file=sys.stderr, flush=True)


def extract_audio(src, fmt="wav"):
    out = os.path.join(tempfile.mkdtemp(), "a." + fmt)
    codec = ["-c:a", "pcm_s16le"] if fmt == "wav" else ["-c:a", "aac", "-b:a", "64k"]
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", src, "-vn", "-ac", "1", "-ar", "16000"] + codec + [out], check=True)
    return out


def ensure(module, package):
    """Ставим недостающую библиотеку сами — человеку не нужно ничего делать руками."""
    try:
        __import__(module)
        return True
    except ImportError:
        log(f"ставлю {package} — это один раз, займёт минуту")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", package])
        if r.returncode:
            return False
        try:
            __import__(module)
            return True
        except ImportError:
            return False


# ── локально ─────────────────────────────────────────────────────────────────
def local_whisper(path, model_name, language):
    if not ensure("faster_whisper", "faster-whisper"):
        sys.exit("не удалось поставить faster-whisper — попробуй: pip3 install --user faster-whisper")
    from faster_whisper import WhisperModel

    log(f"модель {model_name}: загружаю (в первый раз ещё и скачиваю)")
    model = WhisperModel(model_name, device="cpu", compute_type="int8",
                         cpu_threads=os.cpu_count() or 4)

    log("слушаю речь")
    segments, info = model.transcribe(
        path, language=language, word_timestamps=True,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
        beam_size=5, condition_on_previous_text=False)

    words, chunks = [], []
    for seg in segments:
        chunks.append(seg.text)
        for w in (seg.words or []):
            words.append({"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)})
        log(f"  {seg.end:6.1f}с  {seg.text.strip()[:60]}")
    return {"text": "".join(chunks).strip(), "words": words,
            "language": info.language, "source": f"local:{model_name}"}


# ── через API (быстрее, если есть ключ) ──────────────────────────────────────
def groq_whisper(path, key, language):
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    boundary = uuid.uuid4().hex
    fields = {"model": "whisper-large-v3", "response_format": "verbose_json",
              "timestamp_granularities[]": "word"}
    if language:
        fields["language"] = language
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
             f"filename=\"audio.m4a\"\r\nContent-Type: audio/m4a\r\n\r\n").encode()
    body += open(path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "smm-tools/1.0"})     # без User-Agent Cloudflare отдаёт 1010
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    words = [{"w": w["word"].strip(), "s": round(w["start"], 2), "e": round(w["end"], 2)}
             for w in data.get("words", [])]
    return {"text": data.get("text", "").strip(), "words": words,
            "language": language or "?", "source": "groq:whisper-large-v3"}


def transcribe(src, model=MODEL_DEFAULT, language="ru", use_groq=False):
    """Точка входа и для командной строки, и для subtitles.py."""
    key = os.environ.get("GROQ_API_KEY")
    if use_groq:
        if not key:
            sys.exit("нет GROQ_API_KEY — убери --groq, и всё посчитается локально")
        log("распознаю через Groq")
        return groq_whisper(extract_audio(src, "m4a"), key, language)
    return local_whisper(extract_audio(src, "wav"), model, language)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--model", default=MODEL_DEFAULT,
                    help="tiny, base, small, medium (по умолчанию), large-v3")
    ap.add_argument("--language", default="ru", help="язык речи; auto — определить самой")
    ap.add_argument("--groq", action="store_true", help="считать через API вместо своего компьютера")
    ap.add_argument("--out", help="файл вместо вывода на экран")
    a = ap.parse_args()

    lang = None if a.language == "auto" else a.language
    res = transcribe(a.src, a.model, lang, a.groq)
    log(f"слов распознано: {len(res['words'])}")

    text = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
        log(f"готово: {a.out}")
    else:
        print(text)
