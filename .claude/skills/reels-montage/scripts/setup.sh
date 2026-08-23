#!/usr/bin/env bash
# Ставит всё, что нужно навыку монтажа. Запускать один раз:
#   bash ~/.claude/skills/reels-montage/scripts/setup.sh
set -u

say() { printf '%s\n' "$*"; }

say "Проверяю, что уже стоит."

# ── ffmpeg — режет и собирает видео ──────────────────────────────────────────
if command -v ffmpeg >/dev/null 2>&1; then
  say "  ffmpeg — есть"
else
  say "  ffmpeg — ставлю"
  if command -v brew >/dev/null 2>&1; then
    brew install ffmpeg
  elif command -v apt-get >/dev/null 2>&1; then
    SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    $SUDO apt-get update -qq && $SUDO apt-get install -y ffmpeg
  else
    say "  не смогла поставить сама. Поставь ffmpeg вручную: https://ffmpeg.org/download.html"
  fi
fi

# ── питоновские библиотеки ───────────────────────────────────────────────────
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  say "Нет Python 3. Поставь его с python.org и запусти этот файл снова."
  exit 1
fi

say "  библиотеки для текста и шрифтов"
"$PY" -m pip install --user --quiet --upgrade pillow fonttools brotli 2>&1 | grep -v "^WARNING: Running pip" || true

say "  распознавание речи (faster-whisper)"
"$PY" -m pip install --user --quiet --upgrade faster-whisper 2>&1 | grep -v "^WARNING: Running pip" || true

# ── модель распознавания: качаем заранее, чтобы первый монтаж не ждал ────────
MODEL="${1:-medium}"
say ""
say "Скачиваю модель распознавания «$MODEL» — это около полутора гигабайт и только один раз."
"$PY" - "$MODEL" <<'PYEOF'
import sys
try:
    from faster_whisper import WhisperModel
    WhisperModel(sys.argv[1], device="cpu", compute_type="int8")
    print("  модель готова")
except Exception as e:
    print(f"  модель не скачалась ({e}). Скачается сама при первом монтаже.")
PYEOF

# ── итог ─────────────────────────────────────────────────────────────────────
say ""
"$PY" - <<'PYEOF'
import shutil, importlib
rows = [("ffmpeg", bool(shutil.which("ffmpeg")))]
for mod, name in [("PIL", "текст на видео"), ("fontTools", "свои шрифты"),
                  ("faster_whisper", "распознавание речи")]:
    try:
        importlib.import_module(mod); rows.append((name, True))
    except ImportError:
        rows.append((name, False))
print("Что получилось:")
for name, ok in rows:
    print(f"  {'✓' if ok else '✗'} {name}")
print("\nВсё готово." if all(ok for _, ok in rows)
      else "\nЧего-то не хватает — скажи Claude, он доставит.")
PYEOF
