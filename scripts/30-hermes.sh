#!/usr/bin/env bash
# Фаза 3 — установка Hermes. Идемпотентно.
set -euo pipefail

echo "==> Установка Hermes"
if command -v hermes >/dev/null 2>&1; then
  echo "    уже установлен: $(hermes --version 2>&1 | head -1)"
else
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
fi

# Интерактивный setup-wizard при curl|bash пропускается (нет TTY) — это нормально,
# всё настраиваем через hermes config set и .env.

export PATH="/usr/local/bin:$PATH"
hash -r

echo
echo "==> Определяю путь к venv (из bash-обёртки /usr/local/bin/hermes)"
VENV_PY="$(grep -oE '/[^ "]*/venv/bin/python' /usr/local/bin/hermes 2>/dev/null | head -1 || true)"
[ -z "$VENV_PY" ] && VENV_PY="/usr/local/lib/hermes-agent/venv/bin/python"
echo "    venv python: $VENV_PY"
if [ ! -x "$VENV_PY" ]; then
  echo "СТОП: не нашёл python venv Hermes. Покажи вывод: cat /usr/local/bin/hermes"
  exit 1
fi
echo "$VENV_PY" > /root/.hermes-venv-python

echo
echo "==> Telegram-адаптер (extra 'messaging' может не входить в базовую установку)"
if "$VENV_PY" -c 'import telegram' 2>/dev/null; then
  echo "    python-telegram-bot уже есть"
else
  echo "    ModuleNotFoundError -> доставляю extra [messaging]"
  VENV_DIR="$(dirname "$(dirname "$VENV_PY")")"
  PKG_DIR="$(dirname "$VENV_DIR")"
  (cd "$PKG_DIR" && "$VENV_DIR/bin/pip" install -e '.[messaging]')
fi

echo
echo "==> .env с правильными правами"
mkdir -p /root/.hermes
touch /root/.hermes/.env
chmod 600 /root/.hermes/.env

echo
echo "==> hermes doctor"
hermes doctor || {
  echo "    doctor ругается — пробую --fix"
  hermes doctor --fix || true
}

echo
echo "==> ПРОВЕРКА ФАЗЫ 3"
hermes --version
"$VENV_PY" -c 'import telegram; print("import telegram: OK")'
ls -l /root/.hermes/.env
echo "ФАЗА 3 OK"
