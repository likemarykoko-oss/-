# Hermes на VPS — рабочий хендофф

Живой документ. Обновляется по ходу фаз, чтобы новая сессия Claude Code
поднимала контекст отсюда, а не из перегруженного чата.

## Что и где

Hermes Agent (Nous Research), open-source AI-агент. Установлен под root, FHS-layout.

| | |
|---|---|
| Сервер | `216.57.111.124`, хостнейм `hermes`, Timeweb Cloud |
| ОС | Ubuntu 26.04 LTS (ядро 7.0.0-30), 1 CPU / 2 ГБ RAM + 2 ГБ swap, Europe/Moscow |
| Код + venv | `/usr/local/lib/hermes-agent` |
| Бинарь | `/usr/local/bin/hermes` (обёртка к venv python) |
| Данные/конфиг | `/root/.hermes/` — `config.yaml`, `.env` (600), `SOUL.md`, `sessions/`, `logs/`, `cron/`, `memories/`, `skills/` |
| Gateway | systemd-сервис `hermes-gateway`, автозапуск |
| Доступ | SSH только по ключу `hermes-vps` (Ed25519, `SHA256:Deo5GyiIBw+qjlk+aw0RDxYbJ5UJK+J0UdpdaBExqLQ`); пароль для SSH отключён, жив только в веб-консоли Timeweb |

**Способ работы:** управление из Termius на iPad. У сессии Claude Code нет SSH
(облачная песочница режет non-TLS через прокси), поэтому команды выдаются
пользователю текстом для копипаста, результат разбирается по скриншотам.

## Статус фаз

| Фаза | Что | Статус |
|---|---|---|
| 0 | SSH-ключ вместо пароля | ✅ |
| 1 | Базовая настройка (upgrade, hostname, timezone, swap) | ✅ |
| 2 | Безопасность: sshd-харденинг, UFW, fail2ban, автообновления | ✅ |
| 3 | Установка Hermes | ✅ |
| 4 | Мозг: LLM-провайдеры + fallback-цепочка | ✅ |
| 5 | Telegram-бот | ✅ |
| 6 | Голос: STT (Groq Whisper) + TTS (edge-tts) | ✅ |
| 7 | Веб-поиск и парсинг | ✅ |
| 8 | SOUL.md, домашний канал, первый крон | частично (`/sethome` сделан) |
| 9 | Финальная проверка, бэкап, отчёт | ⏳ (промежуточный бэкап был один раз) |

## Сделано в фазах 1–6

### Фазы 1–2, безопасность
- Бэкапы: `/etc/hosts.bak-*`, `/etc/fstab.bak-*`, `/root/.ssh/authorized_keys.bak-*`, `/etc/ssh/sshd_config.d/50-cloud-init.conf.bak-*`
- `/etc/ssh/sshd_config.d/01-hermes.conf`: `PasswordAuthentication no`, `PermitRootLogin prohibit-password`, `MaxAuthTries 4`.
  Имя `01-`, не `99-`: cloud-init'овский `50-cloud-init.conf` с `PasswordAuthentication yes` иначе побеждает по алфавиту.
- UFW: `default deny incoming`, открыт только `22/tcp` (порт 10050 zabbix закрыт снаружи по решению пользователя)
- `/etc/fail2ban/jail.local`: jail `sshd`, `backend=systemd`, maxretry 5/10 min, bantime 1h, `ignoreip` включает IP пользователя `185.21.10.190`
- swap: `/swapfile` 2G, прописан в `/etc/fstab`

### Фаза 3, установка
`curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`.
Первый `git clone --depth 1` упал на `invalid index-pack output` (сетевой сбой, не память) — ручной повтор прошёл (245 МБ).
Затем messaging-экстра: `venv/bin/python -m pip install -e '.[messaging]'`.

### Фаза 4, мозг
Четырёхуровневая fallback-цепочка, все звенья подтверждены живыми PONG-смоуками:

| Уровень | Провайдер | Модель |
|---|---|---|
| Primary | `openai-codex` (OAuth, подписка ChatGPT Plus) | `gpt-5.6-sol` |
| Fallback 1 | OpenRouter | `nvidia/nemotron-3-super-120b-a12b:free` |
| Fallback 2 | custom `gonkarouter` | `MiniMaxAI/MiniMax-M2.7` |
| Fallback 3 | Nous Portal | `tencent/hy3:free` |

OAuth: `/root/.hermes/auth.json`, `/root/.codex/auth.json` (без ключей).
Gonka в `config.yaml` → `providers.gonkarouter`: `base_url: https://api.gonkarouter.io/v1`,
`api_mode: chat_completions`, `key_env: GONKAROUTER_API_KEY`, `discover_models: true`.
Собрано через `hermes fallback add` (интерактивный пикер) ×3, проверено `hermes fallback list`.

Утилита `/root/add-key.sh <ИМЯ_ПЕРЕМЕННОЙ> [url-проверки]` — принимает ключ через `read -rs`,
проверяет живым запросом ДО записи в `.env`, детектит удвоение при вставке (баг Termius/буфера, ловили дважды).

### Фаза 5, Telegram
Бот `@hermes_marykokobot`. `hermes gateway install --system --run-as-user root`.
Проверено: `/status` и живой диалог отвечают, домашний канал установлен через `/sethome`.

### Фаза 6, голос
`/usr/local/bin/hermes-stt-wrapper.py` — Groq Whisper primary + локальный faster-whisper fallback,
chunking >25 МБ. Положен через `cat > файл <<'PYEOF'` (не scp — SSH недоступен).
`faster-whisper` + `requests` в venv, модель `base` прогрета заранее.
Конфиг: `stt.enabled=true`, `stt.provider=local_command`, `stt.local.language=ru`,
`tts.provider=edge`, `tts.edge.voice=ru-RU-DmitryNeural`.
Оба направления проверены живьём в Telegram.

## Переменные в `/root/.hermes/.env` (только имена)

`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GONKAROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_ALLOWED_USERS=454202893`, `HERMES_TELEGRAM_DISABLE_FALLBACK_IPS=true`,
`STT_GROQ_TIMEOUT=60`, `STT_LOCAL_FALLBACK_MODEL=base`,
`HERMES_LOCAL_STT_COMMAND=/usr/local/bin/hermes-stt-wrapper.py {input_path} --output_dir {output_dir} --language {language} --model {model}`.

Значения ключей никогда не выводятся в чат.

## Версии

Hermes 0.20.4 · Ubuntu 26.04 LTS · Codex CLI 0.149.0 · node v26.7.0 / npm 11.19.0 ·
python-telegram-bot 22.8 · tmux 3.6 · faster-whisper 1.2.1

## Грабли, на которые уже наступили — не повторять

- sshd drop-in обязан идти по алфавиту раньше `50-cloud-init.conf`.
- fail2ban банит сразу после установки пакета, ещё до нашей конфигурации — свой IP в `ignoreip` вносить ДО отладки SSH.
- Termius Export-key диалог задваивал ввод — не использовать, только обычное подключение с Key.
- Ключи проверяются живым запросом ДО записи в `.env` (`/root/add-key.sh`), никогда не echo'атся.
- `HERMES_TELEGRAM_DISABLE_FALLBACK_IPS`, `HERMES_LOCAL_STT_COMMAND` — только прямой правкой `.env`, `hermes config set` их не подхватывает (адаптеры читают через `os.getenv`).
- В venv Hermes нет отдельного `pip`, только `python -m pip`.
- Файлы на сервер — через `cat > file <<'EOF'`, не scp.
- Groq не годится как основной LLM: free-тариф 8000 токенов/мин, системный промпт Hermes крупнее → `413 Request payload too large`. Для STT годится.
- `discover_models: true` у custom-провайдеров — не хардкодить ID моделей.

## План фаз 7–9

### Фаза 7 — веб-поиск и парсинг ✅ ЗАВЕРШЕНО

Оказалось, что `web search` и `web extract` уже работали из коробки — это встроенный
в сам Hermes npm-пакет (`web` workspace), не Python-зависимость, поэтому в venv его не видно
через `pip list`. Подтверждено `hermes doctor`: `✓ web search (parallel)`, `✓ web extract (parallel)`.
**Brave и Firecrawl регистрировать не понадобилось** — ключи `BRAVE_SEARCH_API_KEY` /
`FIRECRAWL_API_KEY` не заводились и не нужны.

Живой смоук пройден: `hermes -z 'Найди в вебе последнюю LTS-версию Ubuntu и назови её'`
→ корректный ответ с реальным источником (releases.ubuntu.com).

**Известное ограничение (не блокер, чинить отдельно при желании):**
`browser` и `browser-cdp` (Playwright/agent-browser для JS-тяжёлых страниц) помечены
в `hermes doctor` как `system dependency not met`. Причина: Playwright 1.58.2 официально
ещё не поддерживает Ubuntu 26.04 и отказывается сам ставить зависимости
(`Cannot install dependencies for ubuntu26.04-x64 with Playwright 1.58.2!`).
Решено не чинить руками (риск сломать систему на 1 CPU/2 ГБ ради необязательной фичи —
обычные `web search`/`web extract` её не используют). Вернуться к этому, когда Playwright
добавит поддержку Ubuntu 26.04.

Также замечено (не срочно): `web workspace has 4 npm vulnerabilities`, `ui-tui workspace has 3` —
по словам `hermes doctor` это build-tool advisory, не runtime, чинится бампом lockfile.

### Фаза 8 — личность, дом, крон (`SKILL.md`)

1. Спросить пользователя: имя агента, тон, язык, характер, о чём напоминать → переписать `/root/.hermes/SOUL.md` → restart gateway.
2. Домашний канал — уже сделан (`/sethome`).
3. Первый крон — пользователь просит бота обычной фразой («Каждое утро в 9:00 присылай план на день и погоду»),
   бот сам создаёт через свой cronjob-тулсет. Рассказать про память: «запомни это на будущее».
   Проверка: `hermes cron list` + `hermes cron status`.
   ⚠ Не гонять `hermes cron run` вслепую — она только ставит на ближайший тик, не запускает мгновенно.

### Фаза 9 — финальная проверка и отчёт (`SKILL.md`)

1. `hermes doctor && hermes config check && hermes status` — без ошибок.
2. `systemctl restart hermes-gateway && sleep 5 && systemctl is-active hermes-gateway` → `active`.
3. Финальные смоуки с пользователем: текст → ответ; голосовое → ответ; «найди в интернете…» → ответ с поиском.
4. `hermes backup` + скачать zip к себе (scp). Бэкап только на сервере бесполезен при смерти диска.
   Правило на будущее: перед каждым `hermes update` — сначала `hermes backup`.
5. Итоговый отчёт: IP, способ входа, что закрыто фаерволом; провайдеры/модели; имена переменных в `.env` (НЕ значения);
   команды управления; что осталось.
6. Рассказать про опциональные расширения (Google Workspace, image-gen, CloakBrowser/yt-dlp/NotebookLM) —
   по желанию, не ставить без явного запроса.

## Блокеры

Активных нет. Системное ограничение: у сессии Claude Code нет прямого SSH к серверу —
работа идёт через пользователя в Termius. При смене сессии ограничение сохраняется, если новая сессия тоже облачная.
