#!/usr/bin/env python3
"""
Режет длинный дубль на куски по таймкодам и сшивает в один вертикальный ролик.
Таймкоды выбирает агент по расшифровке — он читает смысл, а не громкость звука.

  python3 cut.py source.mp4 out.mp4 --parts '[[12.4,28.9],[95.0,112.3]]'
"""
import argparse, json, subprocess, tempfile, os, sys

W, H = 1080, 1920

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--parts", required=True, help="JSON: [[начало,конец], ...] в секундах")
    ap.add_argument("--fade", type=float, default=0.08, help="микрозатухание звука на склейках")
    a = ap.parse_args()

    parts = json.loads(a.parts)
    tmp = tempfile.mkdtemp(prefix="cut_")
    pieces = []
    for i, (s, e) in enumerate(parts):
        p = os.path.join(tmp, f"p{i}.mp4")
        d = float(e) - float(s)
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(s), "-t", str(d), "-i", a.src,
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1",
            "-af", f"afade=t=in:st=0:d={a.fade},afade=t=out:st={max(0, d - a.fade)}:d={a.fade}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-r", "30", p], check=True)
        pieces.append(p)

    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in pieces))
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", a.dst], check=True)
    print("готово:", a.dst, f"({len(parts)} кусков)")

if __name__ == "__main__":
    main()
