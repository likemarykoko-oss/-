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
