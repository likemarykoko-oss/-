#!/usr/bin/env python3
"""
Вжигает субтитры по расшифровке — фразами по 3–4 слова, как в залетающих рилсах.
Стиль один на все ролики: это часть узнаваемости, а не украшение.

  python3 transcribe.py in.mp4 > words.json
  python3 subtitles.py in.mp4 out.mp4 --words words.json
"""
import argparse, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reels_text import build

def group(words, max_words=4, max_gap=0.7):
    """Слова в фразы: по паузе или по длине. Пауза важнее — она совпадает с дыханием речи."""
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["s"] - cur[-1]["e"] > max_gap):
            out.append(cur); cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [{"t": g[0]["s"], "d": max(0.6, g[-1]["e"] - g[0]["s"]),
             "text": " ".join(x["w"].strip() for x in g).upper(),
             "style": "sub", "pos": "bottom"} for g in out]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--words", required=True)
    ap.add_argument("--hook", help="крупный текст-хук поверх первых секунд")
    ap.add_argument("--hook-seconds", type=float, default=3.0)
    a = ap.parse_args()

    data = json.load(open(a.words, encoding="utf-8"))
    blocks = group(data["words"])
    if a.hook:
        blocks.insert(0, {"t": 0, "d": a.hook_seconds, "text": a.hook,
                          "style": "hook", "pos": "center"})
    print("фраз:", len(blocks))
    build(a.src, a.dst, blocks)
    print("готово:", a.dst)
