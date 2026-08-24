#!/usr/bin/env python3
"""
Кладёт анимированный прозрачный слой (из Remotion или HyperFrames) поверх ролика.

  python3 overlay_anim.py база.mp4 готово.mp4 --layer титул.mov --at 0.4
  python3 overlay_anim.py база.mp4 готово.mp4 --layer т1.mov --at 0 --layer т2.mov --at 22

Слой должен быть с прозрачностью: ProRes 4444 (.mov) — его умеет и Remotion,
и HyperFrames. WebM с альфой на этом маке не соберётся: в ffmpeg нет vp9.
"""
import argparse, subprocess, sys

W, H = 1080, 1920


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--layer", action="append", required=True)
    ap.add_argument("--at", action="append", type=float, default=[])
    ap.add_argument("--crf", type=int, default=20)
    a = ap.parse_args()

    ats = a.at + [0.0] * (len(a.layer) - len(a.at))
    inputs, filters = [], [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                           f"crop={W}:{H},setsar=1[base]"]
    last = "[base]"
    for i, (lay, t) in enumerate(zip(a.layer, ats), start=1):
        inputs += ["-i", lay]
        # слой масштабируем в кадр и сдвигаем во времени, альфу сохраняем
        filters.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                       f"format=rgba,setpts=PTS-STARTPTS+{t}/TB[l{i}]")
        out = f"[v{i}]"
        filters.append(f"{last}[l{i}]overlay=(W-w)/2:(H-h)/2:"
                       f"eof_action=pass:shortest=0:format=auto{out}")
        last = out

    cmd = (["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", a.src] + inputs +
           ["-filter_complex", ";".join(filters), "-map", last, "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", a.dst])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr[-3000:]); sys.exit(1)
    print("готово:", a.dst)


if __name__ == "__main__":
    main()
