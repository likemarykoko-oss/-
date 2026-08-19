# Hermes VPS Setup

Комплект скиллов для настройки Hermes Agent на Ubuntu VPS.

## Содержимое

- `skills/hermes-vps-setup/` — основной скилл: пошаговая настройка сервера
  (Фазы 0–9: SSH-ключ, безопасность, установка Hermes, LLM-провайдер, Telegram-бот,
  голос STT/TTS, веб-поиск, личность и кроны, финальная проверка) плюс опциональные
  расширения (Google Workspace, генерация изображений, CloakBrowser/yt-dlp/NotebookLM).
- `skills/hermes-vps-setup/references/` — детальные ранбуки по каждой теме.
- `skills/hermes-vps-setup/scripts/hermes-stt-wrapper.py` — обёртка распознавания речи
  (Groq Whisper с fallback на локальный faster-whisper).
- `skills/hermes-kilocode-opencode/` — скилл для Kilocode/OpenCode.
- `skills/hermes-seminar-presentation.html` — презентация семинара.

## Как запускать настройку

Скилл выполняет все шаги через `ssh hermes-vps "..."`, поэтому его нужно запускать
из среды, у которой есть исходящий доступ на 22-й порт сервера.
из среды, у которой есть исходящий доступ на 22-й порт сервера.

**Claude Code на web (облачная песочница) для этого не подходит** — исходящий трафик
там разрешён только на 80/443 и проходит через HTTP-прокси с TLS-инспекцией, который
не пропускает SSH-поток. Подробности проверки — в `docs/environment-blocker.md`.

Запускай локально:

```bash
# на своей машине, где работает ssh
git clone <этот репозиторий>
cd <репозиторий>
claude
```

Затем попроси агента настроить Hermes, указав IP сервера — скилл подхватится из
`skills/hermes-vps-setup/`.

## Ручной путь (без локального Claude Code)

Если запускать локально пока негде — есть адаптированный ранбук под ручной запуск
через веб-консоль хостера: `scripts/RUNBOOK.md`. Фазы 1–3 автоматизированы
скриптами, дальше пошагово.

| Скрипт | Фаза | Что делает |
|---|---|---|
| `scripts/00-check.sh` | 0 | Инвентаризация сервера, ничего не меняет |
| `scripts/10-base.sh` | 1 | Обновления, пакеты, hostname, таймзона, swap |
| `scripts/20-security.sh` | 2 | sshd-харденинг, UFW, fail2ban, автообновления |
| `scripts/30-hermes.sh` | 3 | Установка Hermes, Telegram-адаптер, `.env` |
| `scripts/set-env.sh` | 4+ | Безопасная запись секретов в `.env` (значение со stdin) |
