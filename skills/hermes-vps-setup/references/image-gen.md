# Генерация изображений

В Hermes картинки — отдельный бэкенд (`image_gen.provider`), не связанный с текстовой
моделью. Для семинара — **один провайдер по выбору**, без цепочек-фоллбеков (у нас на
сервере стоит fallback через плагин `image-router`, но участникам это пока не нужно).

Спроси пользователя, что у него есть, и настрой один из двух:

| Есть у пользователя | Путь | Что ставить |
|---|---|---|
| Подписка ChatGPT (Codex настроен в Фазе 4) | Hermes-бэкенд `openai-codex` | ничего — плагин в комплекте, 2 строки конфига |
| Google Gemini Pro / Google AI Pro | внешний CLI `agy` (Google Antigravity) | установить официальный `agy` + вход Google |

Оба пути рабочие. Codex (Вариант 1) — самый быстрый, если он уже настроен: нативный
бэкенд Hermes из коробки. `agy` (Вариант 2) — официальный агентный CLI Google на Gemini;
Hermes-агент вызывает его через терминал, отдельного плагина для этого не нужно.

⚠ Модели генерации (`gpt-image-2-high`, `Gemini 3.5 Flash (High)`) со временем меняются —
не хардкодь вслепую: у Codex смотри актуальную image-модель, у agy — `agy models`.

---

## Вариант 1 — через Codex (проще всего, если Codex уже есть)

Если в Фазе 4 подключён `openai-codex` (вход по коду ChatGPT) — генерация идёт через ту
же подписку, ставить нечего:

```bash
ssh hermes-vps "hermes config set image_gen.provider openai-codex && hermes config set image_gen.model gpt-image-2-high && systemctl restart hermes-gateway"
```

Использует `gpt-image-2` через Codex OAuth; картинки сохраняются в
`$HERMES_HOME/cache/images/`.

---

## Вариант 2 — через внешний CLI `agy` (Google Antigravity, если есть Gemini)

`agy` — официальный агентный CLI Google на Gemini; генерирует изображения на квоте
Google-аккаунта (Gemini Pro / Google AI Pro). Ставится напрямую от Google, Hermes-агент
вызывает его через terminal-тулсет — отдельный плагин не нужен.

**Полная установка, авторизация и использование: читай `references/antigravity-cli.md`.**
Коротко:
1. Установить: `curl -fsSL https://antigravity.google/cli/install.sh | bash` → `~/.local/bin/agy`.
2. Войти в Google (headless device-флоу): `ssh -t hermes-vps "HOME=/root /root/.local/bin/agy"` →
   выбрать Google OAuth, открыть URL на своей машине, ввести код.
3. Пользоваться как внешним CLI: агент зовёт
   `HOME=/root /root/.local/bin/agy --print --dangerously-skip-permissions --print-timeout 10m "<промпт картинки>"` —
   `agy` сохраняет файл и печатает `Generated image is saved at /abs/path.jpg`, агент
   отправляет картинку пользователю. В `SOUL.md`/инструкции агента можно закрепить:
   «для генерации картинок используй `agy --print …`».

Нативным image-бэкендом Hermes (`image_gen.provider antigravity-cli`) это тоже можно
подключить, но тот плагин НЕ входит в стоковый Hermes (нужен отдельный источник) — для
семинара проще терминальный путь выше, результат тот же. Детали — в runbook.

---

**Проверка (любой вариант):** пользователь просит бота «нарисуй рыжего кота в шляпе» —
приходит картинка. Если ошибка — смотри `journalctl -u hermes-gateway -e | tail -30`
и проверь, что бэкенд авторизован (Codex-токен / agy login) и модель актуальна.
