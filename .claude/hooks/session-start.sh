#!/bin/bash
# Готовит окружение для навыка монтажа: ffmpeg, библиотеки и модель распознавания речи.
# Состояние контейнера кэшируется после выполнения хука, поэтому тяжёлая модель
# скачивается один раз, а в следующих сессиях этот скрипт просто ничего не делает.
set -uo pipefail

# На своём компьютере кэш и так никуда не девается — там хватает setup.sh.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SKILL="${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/skills/reels-montage"
MODEL="${REELS_MODEL:-medium}"

# Фиксируем, где лежат модели, чтобы хук и сессия смотрели в одно место.
export HF_HOME="${HF_HOME:-/root/.cache/huggingface}"
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export HF_HOME=\"$HF_HOME\"" >> "$CLAUDE_ENV_FILE"
  echo "export REELS_MODEL=\"$MODEL\"" >> "$CLAUDE_ENV_FILE"
fi

[ -d "$SKILL" ] || exit 0

# ── ffmpeg ───────────────────────────────────────────────────────────────────
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "монтаж: ставлю ffmpeg"
  apt-get update -qq >/dev/null 2>&1
  apt-get install -y -qq ffmpeg >/dev/null 2>&1 || echo "монтаж: ffmpeg поставить не вышло"
fi

# ── питоновские библиотеки ───────────────────────────────────────────────────
if ! python3 -c "import PIL, fontTools, faster_whisper" >/dev/null 2>&1; then
  echo "монтаж: ставлю библиотеки"
  python3 -m pip install --user --quiet pillow fonttools brotli faster-whisper >/dev/null 2>&1 \
    || echo "монтаж: библиотеки поставить не вышло"
fi

# ── модель распознавания речи ────────────────────────────────────────────────
# Качаем только если её ещё нет: попадёт в кэш контейнера и переживёт сессию.
python3 - "$MODEL" <<'PYEOF'
import sys, os
model = sys.argv[1]
home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
marker = os.path.join(home, "hub", f"models--Systran--faster-whisper-{model}", "snapshots")
if os.path.isdir(marker) and os.listdir(marker):
    print(f"монтаж: модель {model} уже на месте")
    sys.exit(0)
try:
    from faster_whisper import WhisperModel
    print(f"монтаж: качаю модель {model} — один раз, дальше она останется в контейнере")
    WhisperModel(model, device="cpu", compute_type="int8")
    print(f"монтаж: модель {model} готова")
except Exception as e:
    print(f"монтаж: модель не скачалась ({e}); скачается при первом монтаже")
PYEOF

exit 0
