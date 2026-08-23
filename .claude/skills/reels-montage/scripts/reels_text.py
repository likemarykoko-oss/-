#!/usr/bin/env python3
"""
Накладывает текст на готовое видео и приводит его к вертикали 9:16 под Reels.

Стили и шрифты лежат в styles.json рядом — правь его, скрипт трогать не нужно.

  python3 reels_text.py in.mp4 out.mp4 --hook "Я делала это полгода неправильно"
  python3 reels_text.py in.mp4 out.mp4 --hook "текст" --style plate --font Onest
  python3 reels_text.py in.mp4 out.mp4 --json blocks.json
  python3 reels_text.py --list-fonts        # какие шрифты доступны
  python3 reels_text.py --add-font ~/Downloads/MyFont.woff2   # добавить свой

blocks.json:
[{"t":0,"d":3,"text":"Первая надпись","style":"hook","pos":"center"},
 {"t":3,"d":2.5,"text":"вторая","style":"plate","pos":"bottom"}]
"""
import argparse, json, subprocess, tempfile, os, sys, shutil
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
STYLE_FILE = os.path.join(HERE, "styles.json")
W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = int(H * 0.10), int(H * 0.18)   # верх — ник, низ — интерфейс Reels

SYSTEM_FONT_DIRS = ["/System/Library/Fonts/Supplemental", "/Library/Fonts",
                    os.path.expanduser("~/Library/Fonts"),
                    "/usr/share/fonts", "/usr/local/share/fonts"]


# ── шрифты ───────────────────────────────────────────────────────────────────
def font_path(name):
    """Ищем шрифт по имени: сначала свои в fonts/, потом системные."""
    if os.path.isfile(name):
        return name
    for ext in (".ttf", ".otf", ".ttc"):
        p = os.path.join(FONT_DIR, name + ext)
        if os.path.isfile(p):
            return p
    low = name.lower()
    for d in SYSTEM_FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().startswith(low) and f.lower().endswith((".ttf", ".otf", ".ttc")):
                return os.path.join(d, f)
    sys.exit(f"шрифт «{name}» не найден. Посмотри список: python3 reels_text.py --list-fonts")


def add_font(src):
    """Кладём свой шрифт в fonts/. woff2 и woff конвертируем автоматически."""
    os.makedirs(FONT_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0]
    if src.lower().endswith((".woff2", ".woff")):
        from fontTools.ttLib import TTFont
        f = TTFont(src); f.flavor = None
        dst = os.path.join(FONT_DIR, base + ".ttf"); f.save(dst)
    else:
        dst = os.path.join(FONT_DIR, os.path.basename(src)); shutil.copy(src, dst)
    ok = has_cyrillic(dst)
    print(f"добавлен: {os.path.basename(dst)} · кириллица: {'да' if ok else 'НЕТ — русский текст сломается'}")
    return dst


def has_cyrillic(path):
    try:
        from fontTools.ttLib import TTFont
        cmap = TTFont(path, fontNumber=0).getBestCmap()
        return all(ord(c) in cmap for c in "АБВЁЖЩЫЭЮЯабвёжщыэюя")
    except Exception:
        return None


def list_fonts():
    print("Свои (папка fonts/) — их и используем по умолчанию:")
    for f in sorted(os.listdir(FONT_DIR)) if os.path.isdir(FONT_DIR) else []:
        if f.lower().endswith((".ttf", ".otf")):
            cyr = has_cyrillic(os.path.join(FONT_DIR, f))
            mark = {True: "кириллица есть", False: "БЕЗ кириллицы", None: "?"}[cyr]
            print(f"  {os.path.splitext(f)[0]:28} {mark}")
    print("\nСистемные (работают, но выглядят как у всех):")
    seen = set()
    for d in SYSTEM_FONT_DIRS:
        if os.path.isdir(d):
            for f in sorted(os.listdir(d))[:400]:
                n = os.path.splitext(f)[0]
                if f.lower().endswith((".ttf", ".otf")) and n not in seen:
                    seen.add(n)
    print("  " + ", ".join(sorted(seen)[:25]) + " …")
    print("\nДобавить свой:  python3 reels_text.py --add-font путь/к/шрифту.woff2")


# ── стили ────────────────────────────────────────────────────────────────────
def load_styles():
    data = json.load(open(STYLE_FILE, encoding="utf-8"))
    return data["presets"]


def render_layer(text, st):
    fp = font_path(st.get("font", "Unbounded"))
    font = ImageFont.truetype(fp, int(st["size"]))
    if st.get("case") == "upper":
        text = text.upper()
    elif st.get("case") == "lower":
        text = text.lower()

    measure = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    max_w = int(W * float(st.get("width", 84)) / 100)

    def wrap(para):
        out, cur = [], ""
        for word in para.split():
            test = (cur + " " + word).strip()
            if measure.textlength(test, font=font) <= max_w or not cur:
                cur = test
            else:
                out.append(cur); cur = word
        if cur:
            out.append(cur)
        return out or [""]

    lines = []
    for para in text.split("\n"):
        lines.extend(wrap(para))

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lh = int(int(st["size"]) * float(st.get("line_gap", 1.2)))
    total = lh * len(lines)
    return img, d, font, st, lines, lh, total


def draw_layer(text, st, pos):
    img, d, font, st, lines, lh, total = render_layer(text, st)
    if pos == "center":
        y = (H - total) // 2
    elif pos == "top":
        y = SAFE_TOP + 60
    else:
        y = H - SAFE_BOTTOM - total - 40

    sw = int(st.get("stroke_w", 0))
    for ln in lines:
        bbox = d.textbbox((0, 0), ln, font=font, stroke_width=sw)
        x = (W - (bbox[2] - bbox[0])) // 2
        if st.get("box"):
            pad = 20
            d.rounded_rectangle([x - pad, y - pad // 2,
                                 x + (bbox[2] - bbox[0]) + pad, y + lh - pad // 3],
                                radius=16, fill=st["box"])
        d.text((x, y), ln, font=font, fill=st.get("fill", "#FFFFFF"),
               stroke_width=sw, stroke_fill=st.get("stroke") or st.get("fill", "#FFFFFF"))
        y += lh
    return img


# ── сборка ───────────────────────────────────────────────────────────────────
def build(src, dst, blocks, font_override=None, crf=22):
    presets = load_styles()
    tmp = tempfile.mkdtemp(prefix="reels_")
    inputs, filters = [], []
    filters.append(f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                   f"crop={W}:{H},setsar=1[base]")
    last = "[base]"

    for i, b in enumerate(blocks, start=1):
        st = dict(presets.get(b.get("style", "hook"), presets["hook"]))
        if font_override:
            st["font"] = font_override
        st.update({k: v for k, v in b.items()
                   if k in ("size", "fill", "stroke", "stroke_w", "box", "font", "case", "width")})
        png = os.path.join(tmp, f"layer{i}.png")
        draw_layer(b["text"], st, b.get("pos", "center")).save(png)
        inputs += ["-i", png]
        t, d = float(b["t"]), float(b.get("d", 3))
        out = f"[v{i}]"
        filters.append(f"{last}[{i}:v]overlay=0:0:enable='between(t,{t},{t + d})'{out}")
        last = out

    cmd = (["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src] + inputs +
           ["-filter_complex", ";".join(filters), "-map", last, "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", dst])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr[-2500:]); sys.exit(1)
    return dst


if __name__ == "__main__":
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("src", nargs="?"); ap.add_argument("dst", nargs="?")
    ap.add_argument("--hook"); ap.add_argument("--hook-seconds", type=float, default=3.0)
    ap.add_argument("--json"); ap.add_argument("--style", default="hook")
    ap.add_argument("--font", help="шрифт для всех надписей, перебивает styles.json")
    ap.add_argument("--pos", default="center", choices=["center", "top", "bottom"])
    ap.add_argument("--crf", type=int, default=22, help="качество: меньше = лучше и тяжелее")
    ap.add_argument("--list-fonts", action="store_true")
    ap.add_argument("--add-font")
    a = ap.parse_args()

    if a.list_fonts:
        list_fonts(); sys.exit()
    if a.add_font:
        add_font(os.path.expanduser(a.add_font)); sys.exit()
    if not a.src or not a.dst:
        sys.exit("нужно: вход.mp4 выход.mp4 --hook «текст»")

    if a.json:
        blocks = json.load(open(a.json, encoding="utf-8"))
    elif a.hook:
        blocks = [{"t": 0, "d": a.hook_seconds, "text": a.hook,
                   "style": a.style, "pos": a.pos}]
    else:
        sys.exit("нужен --hook или --json")

    print("готово:", build(a.src, a.dst, blocks, font_override=a.font, crf=a.crf))
