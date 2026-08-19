#!/usr/bin/env bash
# Безопасная запись секрета в /root/.hermes/.env — значение читается со stdin,
# не попадает ни в аргументы (видны в ps), ни в историю shell.
#
# Использование:
#   bash set-env.sh TELEGRAM_BOT_TOKEN
#   <вставляешь значение, Enter>
#
# Несколько за раз:
#   bash set-env.sh GROQ_API_KEY BRAVE_SEARCH_API_KEY
set -euo pipefail

ENVFILE=/root/.hermes/.env
mkdir -p /root/.hermes
touch "$ENVFILE"
chmod 600 "$ENVFILE"

[ $# -eq 0 ] && { echo "Укажи имена переменных: bash set-env.sh KEY1 [KEY2 ...]"; exit 1; }

for key in "$@"; do
  printf 'Значение для %s (ввод скрыт): ' "$key" >&2
  IFS= read -rs value
  echo >&2
  [ -z "$value" ] && { echo "  пропущено (пусто)" >&2; continue; }
  # удаляем старую строку, дописываем новую
  if grep -q "^${key}=" "$ENVFILE"; then
    sed -i "/^${key}=/d" "$ENVFILE"
    echo "  ${key}: перезаписан" >&2
  else
    echo "  ${key}: добавлен" >&2
  fi
  printf '%s=%s\n' "$key" "$value" >> "$ENVFILE"
done

chmod 600 "$ENVFILE"
echo >&2
echo "Сейчас в .env заданы (только имена, без значений):" >&2
grep -oE '^[A-Z_][A-Z0-9_]*' "$ENVFILE" | sort >&2
