#!/usr/bin/env python3
"""
Расшифровка видео в текст с таймкодами по словам. Это вход для всего сложного монтажа:
по нему агент выбирает сильные куски, из него же делаются субтитры.

Ключ: GROQ_API_KEY (тот же, что у бота Мини на сервере — в /root/.hermes/.env).
  python3 transcribe.py video.mp4 > words.json
"""
import sys, os, json, subprocess, tempfile, urllib.request, mimetypes, uuid

def extract_audio(src):
    out = os.path.join(tempfile.mkdtemp(), "a.m4a")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "aac", "-b:a", "64k", out], check=True)
    return out

def groq_whisper(path, key):
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    boundary = uuid.uuid4().hex
    fields = {"model": "whisper-large-v3", "response_format": "verbose_json",
              "timestamp_granularities[]": "word", "language": "ru"}
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
        return json.load(r)

if __name__ == "__main__":
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        sys.exit("нет GROQ_API_KEY — возьми тот же ключ, что у бота Мини")
    data = groq_whisper(extract_audio(sys.argv[1]), key)
    words = [{"w": w["word"], "s": round(w["start"], 2), "e": round(w["end"], 2)}
             for w in data.get("words", [])]
    print(json.dumps({"text": data.get("text", ""), "words": words},
                     ensure_ascii=False, indent=1))
