#!/usr/bin/env python3
"""
Вжигает субтитры по речи — фразами по 3–4 слова, как в залетающих рилсах.
Стиль один на все ролики: это часть узнаваемости, а не украшение.

Речь распознаётся сама, ключи и лишние шаги не нужны:

  python3 subtitles.py in.mp4 out.mp4
  python3 subtitles.py in.mp4 out.mp4 --hook "Я делала это полгода неправильно"
  python3 subtitles.py in.mp4 out.mp4 --words words.json    # если расшифровка уже есть

Расшифровка сохраняется рядом с готовым файлом (out.words.json) — второй прогон
с другим текстом или стилем уже мгновенный.

КАПС, цвет и размер живут в styles.json, пресет `sub`. Скрипт трогать не нужно.
"""
import argparse, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reels_text import build
from transcribe import transcribe, MODEL_DEFAULT


def group(words, max_words=4, max_gap=0.7, min_d=0.6):
    """Слова в фразы: по паузе или по длине. Пауза важнее — она совпадает с дыханием речи."""
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["s"] - cur[-1]["e"] > max_gap):
            out.append(cur); cur = []
        cur.append(w)
    if cur:
        out.append(cur)

    blocks = []
    for i, g in enumerate(out):
        start = g[0]["s"]
        end = max(g[-1]["e"], start + min_d)
        # не наезжаем на следующую фразу — иначе две надписи в кадре разом
        if i + 1 < len(out):
            end = min(end, out[i + 1][0]["s"])
        blocks.append({"t": round(start, 2), "d": round(max(0.3, end - start), 2),
                       "text": " ".join(x["w"].strip() for x in g),
                       "style": "sub", "pos": "bottom"})
    return blocks


def trim_under(blocks, until, min_left=0.5):
    """Убираем субтитры из-под хука: что целиком под ним — прячем, что торчит — подрезаем."""
    out = []
    for b in blocks:
        end = b["t"] + b["d"]
        if end <= until:
            continue
        if b["t"] < until:
            if end - until < min_left:
                continue
            b = dict(b, t=round(until, 2), d=round(end - until, 2))
        out.append(b)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--words", help="готовая расшифровка; без неё распознаю сама")
    ap.add_argument("--hook", help="крупный текст-хук поверх первых секунд")
    ap.add_argument("--hook-seconds", type=float, default=3.0)
    ap.add_argument("--max-words", type=int, default=4, help="слов во фразе")
    ap.add_argument("--model", default=MODEL_DEFAULT, help="модель распознавания")
    ap.add_argument("--language", default="ru")
    ap.add_argument("--groq", action="store_true")
    ap.add_argument("--font", help="шрифт для всех надписей, перебивает styles.json")
    ap.add_argument("--crf", type=int, default=22)
    a = ap.parse_args()

    cache = os.path.splitext(a.dst)[0] + ".words.json"
    path = a.words or (cache if os.path.isfile(cache) else None)

    if path:
        print(f"беру готовую расшифровку: {path}", file=sys.stderr)
        data = json.load(open(path, encoding="utf-8"))
    else:
        lang = None if a.language == "auto" else a.language
        data = transcribe(a.src, a.model, lang, a.groq)
        json.dump(data, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"расшифровка сохранена: {cache}", file=sys.stderr)

    if not data.get("words"):
        sys.exit("речь не распознана — в ролике тихо или нет голоса. "
                 "Наложить текст руками: reels_text.py")

    blocks = group(data["words"], max_words=a.max_words)
    if a.hook:
        # пока висит хук, субтитры молчат — иначе в кадре две надписи разом
        blocks = [b for b in trim_under(blocks, a.hook_seconds)]
        blocks.insert(0, {"t": 0, "d": a.hook_seconds, "text": a.hook,
                          "style": "hook", "pos": "center"})

    print(f"фраз: {len(blocks)}", file=sys.stderr)
    build(a.src, a.dst, blocks, font_override=a.font, crf=a.crf)
    print("готово:", a.dst)
