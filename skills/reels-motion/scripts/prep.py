#!/usr/bin/env python3
"""
Подготовка исходника к анимированному монтажу — всё, что нужно до графики.

  python3 prep.py дубль.MOV            # → base.mp4 + speech.srt рядом с исходником

Что делает:
  1. расшифровывает речь (whisper локально, без ключей и интернета);
  2. вырезает паузы — порог считается от реальной громкости записи;
  3. приводит к вертикали 1080×1920;
  4. перекодирует с частыми ключевыми кадрами — иначе видео «замерзает»
     под графикой в рендере HyperFrames.

Дальше на base.mp4 накладываются анимированные карточки, а speech.srt даёт
тайминги, к которым они привязываются.
"""
import argparse, ctypes, os, re, subprocess, sys, tempfile

W, H, AIR = 1080, 1920, 0.10
MODEL = os.path.expanduser("~/.claude/models/ggml-small.bin")


def short_path(p):
    """whisper-cli разбирает argv как ANSI и ломает кириллицу в пути. Подсовываем
    короткий 8.3-путь Windows для директории — сам файл может ещё не существовать.
    Если короткие имена на томе отключены, вернётся исходный путь."""
    if os.name != "nt":
        return p
    d, b = os.path.split(p)
    buf = ctypes.create_unicode_buffer(260)
    n = ctypes.windll.kernel32.GetShortPathNameW(d, buf, 260)
    return os.path.join(buf.value, b) if n else p


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", path]).stdout.strip())


def transcribe(src, out_srt):
    if not os.path.exists(MODEL):
        sys.exit(f"нет модели распознавания: {MODEL}\n"
                 f"скажи Claude «скачай модель small для whisper»")
    wav = os.path.join(tempfile.mkdtemp(), "a.wav")
    run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])
    base = os.path.splitext(out_srt)[0]
    r = run(["whisper-cli", "-m", short_path(MODEL), "-l", "ru",
             "-f", short_path(wav), "-osrt", "-of", short_path(base)])
    if not os.path.exists(out_srt):
        sys.stderr.write(r.stderr[-1500:]); sys.exit("распознавание не удалось")
    return out_srt


def mean_volume(src):
    r = run(["ffmpeg", "-hide_banner", "-i", src, "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else -30.0


def keep_segments(src, dur, min_pause=0.32):
    """Куски со звуком. Порог от громкости записи: в кафе фон громче, чем дома."""
    thr = f"{mean_volume(src) - 5:.1f}dB"
    r = run(["ffmpeg", "-hide_banner", "-i", src, "-af",
             f"silencedetect=n={thr}:d={min_pause}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    segs, cursor = [], 0.0
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else dur
        s2 = min(dur, s + AIR)
        if s2 - cursor > 0.25:
            segs.append((cursor, s2))
        cursor = max(0.0, e - AIR)
    if dur - cursor > 0.25:
        segs.append((cursor, dur))
    return segs or [(0.0, dur)]


def build(src, dst, segs, fps=30, crf=18):
    parts = []
    for i, (s, e) in enumerate(segs):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
    parts.append("".join(f"[v{i}][a{i}]" for i in range(len(segs))) +
                 f"concat=n={len(segs)}:v=1:a=1[vc][ac]")
    parts.append(f"[vc]scale={W}:{H}:force_original_aspect_ratio=increase,"
                 f"crop={W}:{H},setsar=1[vout]")
    r = run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
             "-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[ac]",
             "-c:v", "libx264", "-crf", str(crf), "-g", str(fps), "-keyint_min", str(fps),
             "-r", str(fps), "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             "-c:a", "aac", "-b:a", "128k", dst])
    if r.returncode:
        sys.stderr.write(r.stderr[-2000:]); sys.exit(1)
    return dst


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default=None, help="куда положить base.mp4")
    ap.add_argument("--no-cut", action="store_true", help="не вырезать паузы")
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()

    folder = os.path.dirname(os.path.abspath(a.src))
    out = a.out or os.path.join(folder, "base.mp4")
    srt = os.path.join(folder, "speech.srt")

    print("расшифровываю речь…")
    transcribe(a.src, srt)
    dur = duration(a.src)
    segs = [(0.0, dur)] if a.no_cut else keep_segments(a.src, dur)
    cut = dur - sum(e - s for s, e in segs)
    print(f"вырезано пауз: {cut:.1f} сек из {dur:.1f}")
    build(a.src, out, segs, fps=a.fps)
    print("готово:")
    print("  ", out)
    print("  ", srt, "— вычитай его перед сборкой: whisper путает термины")
