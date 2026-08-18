---
name: hermes-vps-setup
description: >
  Пошаговая настройка свежего Ubuntu VPS «под ключ» для Hermes Agent: базовая безопасность
  (SSH-ключ вместо пароля, UFW, fail2ban, автообновления), установка Hermes, Telegram-бот,
  голос (распознавание Groq/локальный Whisper + TTS-ответы без ключа), веб-поиск и парсинг,
  подключение LLM-провайдеров (Nous Portal, OpenRouter, Codex/ChatGPT, Groq, Gonka, любой
  OpenAI-совместимый), личность бота и кроны, а также опционально: генерация изображений,
  Google Workspace, CloakBrowser, yt-dlp, NotebookLM.
  Используй этот скилл всегда, когда пользователь даёт IP/адрес сервера и просит настроить
  Hermes: «подними Hermes на сервере», «настрой мне бота на VPS», «установи Hermes на
  1.2.3.4», «настрой сервер под агента» — даже если названа только часть задач (только
  безопасность, только телеграм, только голос).
---

# Hermes VPS Setup — настройка сервера под ключ

Ты настраиваешь свежий VPS (Ubuntu 22.04/24.04) под Hermes Agent — от первого входа до
работающего Telegram-бота с голосом, веб-поиском и парсингом. Скилл написан по мотивам
реальных боевых установок: все грабли, отмеченные «⚠», встречались вживую — не пропускай их.

## Принципы работы (важно, прочитай до начала)

1. **Фаза за фазой, с проверкой.** После каждого шага выполняй проверку из раздела
   «Проверка». Не переходи к следующей фазе, пока текущая не подтверждена.
2. **Никаких молчаливых fallback'ов.** Если шаг не получился — остановись, сообщи
   пользователю что именно сломалось, предложи варианты. Не подсовывай молча урезанную
   замену («не встал X, поставил вместо него Y») — это ломает доверие к результату.
3. **Секреты.** API-ключи и токены запрашивай у пользователя по фазам. Записывай их сразу
   в `.env` на сервере (chmod 600). **Никогда не выводи значение ключа в чат, логи или
   команды с echo.** Передавай ключи на сервер через stdin/here-doc, а не через аргументы
   командной строки (аргументы видны в `ps` и истории shell).
4. **Пароль от сервера НЕ трогаешь.** Если вход пока по паролю — команду с вводом пароля
   выполняет сам пользователь в своём терминале (см. Фазу 0). Ты работаешь только по ключу.
5. **Бэкапы перед правкой.** Перед изменением любого конфига: `cp <file> <file>.bak-<тема>-$(date +%Y%m%d)`.
6. **После правок `.env` или `config.yaml` — рестарт гейтвея**, иначе изменения не подхватятся:
   `systemctl restart hermes-gateway`.

## Что понадобится от пользователя (покажи этот список в начале)

Сообщи пользователю сразу, что по ходу настройки понадобятся (можно готовить параллельно):

| Что | Где взять | Фаза |
|---|---|---|
| IP сервера + доступ (root-пароль или ключ уже добавлен) | панель хостера | 0 |
| Telegram bot token | @BotFather → /newbot | 5 |
| Свой Telegram user id (число) | @userinfobot | 5 |
| Groq API key (бесплатно) — голос | console.groq.com → API Keys | 6 |
| Brave Search API key (Free plan, 2000 req/мес) | brave.com/search/api | 7 |
| Firecrawl API key (есть free tier) | firecrawl.dev | 7 |
| «Мозг» — минимум один: Nous Portal / OpenRouter / Codex / Gonka / другой | см. Фазу 4 | 4 |
| (опц.) Google Workspace: client_secret.json OAuth-клиента | console.cloud.google.com | Расшир. A |

Обязательный минимум для работающего бота: доступ к серверу, bot token, user id и один
LLM-провайдер. Остальное можно добавить позже — спроси пользователя, что настраиваем сейчас.

---

## Фаза 0 — Доступ по SSH-ключу

Цель: попасть на сервер по ключу, не по паролю.

1. Спроси у пользователя IP сервера и как сейчас устроен вход (root-пароль от хостера /
   ключ уже добавлен при создании VPS).
2. Если подходящего ключа на машине пользователя нет — создай:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/hermes_vps -N "" -C "hermes-vps"
   ```
3. Доставь публичный ключ на сервер:
   - **Ключ уже добавлен хостером** → ничего не нужно, проверь вход.
   - **Только пароль** → попроси пользователя выполнить в своём терминале самому
     (он введёт пароль, ты пароль не видишь и не обрабатываешь):
     ```bash
     ssh-copy-id -i ~/.ssh/hermes_vps.pub root@<IP>
     ```
4. Добавь блок в `~/.ssh/config` пользователя (если его нет):
   ```
   Host hermes-vps
       HostName <IP>
       User root
       IdentityFile ~/.ssh/hermes_vps
   ```

**Проверка:** `ssh -o BatchMode=yes hermes-vps "echo OK"` возвращает `OK` без запроса пароля.
Дальше все команды выполняй как `ssh hermes-vps "..."`.

## Фаза 1 — Базовая настройка сервера

```bash
ssh hermes-vps "export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get -y upgrade && apt-get -y install curl git jq ufw fail2ban unattended-upgrades"
```

- Hostname (спроси или предложи `hermes`): `hostnamectl set-hostname hermes`
- Часовой пояс (спроси у пользователя): `timedatectl set-timezone Europe/Moscow` (или его вариант)
- Если RAM < 4 ГБ (`free -m`) и swap отсутствует — создай 2 ГБ swap:
  ```bash
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
  ```

**Проверка:** `apt-get -y upgrade` завершился без ошибок; `free -m` показывает swap (если делали).
Если ядро обновилось и хостер рекомендует ребут — согласуй ребут с пользователем сейчас,
пока ничего не настроено (потом будет дороже).

## Фаза 2 — Безопасность

Подробные конфиги и объяснения: **читай `references/security.md`**. Краткий порядок
(нарушение порядка = риск потерять доступ к серверу):

1. **Сначала** убедись, что вход по ключу работает (Фаза 0 подтверждена).
2. Харденинг sshd через drop-in `/etc/ssh/sshd_config.d/99-hermes.conf`: отключить
   вход по паролю, root только по ключу. Проверить `sshd -t`, перезапустить `ssh`,
   **проверить вход по ключу новой сессией, не закрывая текущую.**
3. UFW: `default deny incoming`, `default allow outgoing`, `allow 22/tcp`, затем enable.
   ⚠ Именно **`allow`, а НЕ `ufw limit`**: боевой инцидент — `limit` (6 конн/30с) начал
   резать SSH-соединения самого агента при активной работе. Защита от брутфорса — задача
   fail2ban, не rate-limit'а.
4. fail2ban: jail `sshd`, `backend = systemd`, maxretry 5, bantime 1h.
5. unattended-upgrades: включить автоматические security-обновления.

**Проверка:** новая SSH-сессия по ключу работает; `ssh -o PubkeyAuthentication=no ...`
получает отказ (Permission denied) без запроса пароля; `ufw status verbose` — deny incoming,
22/tcp ALLOW; `fail2ban-client status sshd` — jail активен.

## Фаза 3 — Установка Hermes

```bash
ssh hermes-vps "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
```

Под root установка ложится в FHS-layout: код и venv — `/usr/local/lib/hermes-agent`,
бинарь — `/usr/local/bin/hermes`, домашняя директория агента — `/root/.hermes`
(`config.yaml` + `.env`). Интерактивный setup-wizard при `curl | bash` пропускается
(нет TTY) — это нормально, всё настроим через `hermes config set` и `.env`.

После установки:
```bash
ssh hermes-vps "hermes --version && hermes doctor"
```
Если doctor жалуется на симлинки — `hermes doctor --fix`.

⚠ Telegram-адаптер живёт в extra `messaging` и может не входить в базовую установку. Проверь:
```bash
ssh hermes-vps "/usr/local/lib/hermes-agent/venv/bin/python -c 'import telegram' 2>&1"
```
Если `ModuleNotFoundError` — доставь:
```bash
ssh hermes-vps "cd /usr/local/lib/hermes-agent && venv/bin/pip install -e '.[messaging]'"
```
(путь venv может отличаться — `/usr/local/bin/hermes` — bash-обёртка, путь смотри внутри: `cat /usr/local/bin/hermes`).

**Проверка:** `hermes --version` печатает версию; `import telegram` проходит; файл
`/root/.hermes/.env` существует (создай пустой с chmod 600, если нет).

## Фаза 4 — «Мозг»: LLM-провайдер

Подробности по каждому провайдеру: **читай `references/providers.md`**.

Спроси пользователя, что у него есть, и настрой минимум один (рекомендации по порядку):

1. **Nous Portal** (родной для Hermes, бесплатные модели/токены) — `hermes portal` в
   интерактивной SSH-сессии, OAuth по ссылке.
2. **OpenRouter** (ключ, много бесплатных `:free` моделей).
3. **Codex / ChatGPT Plus** — вход по коду устройства (`codex login --device-auth`),
   даёт провайдер `openai-codex` на квоте подписки. ⚠ Сначала включи device-авторизацию
   в ChatGPT (Settings → Security), иначе код не примут — детали в providers.md §3.
4. **Groq** (тот же ключ, что для голоса — быстрые бесплатные модели).
5. **Gonka: GonkaRouter / GonkaGate** — дешёвый inference открытых моделей
   (MiniMax, Kimi, Qwen) на децентрализованной сети; у GonkaRouter новым
   пользователям $20 кредитов на старт.
6. **CLIProxyAPI** (продвинутое) — локальный Docker-прокси, объединяющий OAuth-подписки
   (Codex/Gemini/Qwen) и ключи Google AI Studio в один эндпоинт с ротацией. Ставь по
   запросу; для одного провайдера проще native-варианты выше.
7. **Любой OpenAI-совместимый шлюз** — секция `providers.<id>` в config.yaml.

Обязательно настрой **fallback-цепочку** из 1–3 бесплатных моделей (`hermes fallback add`),
чтобы бот переживал исчерпание квоты основной модели.

**Проверка:**
```bash
ssh hermes-vps "hermes -z 'Ответь ровно одним словом: PONG'"
```
Ответ содержит PONG. Если нет — разбирайся с провайдером, не иди дальше: без мозга
остальные фазы не проверить.

## Фаза 4½ — Улучшенная память Hindsight (опционально, локально на своём сервере)

По умолчанию Hermes помнит через встроенные `MEMORY.md`/`USER.md` (они всегда активны).
**Hindsight** — нативный memory-провайдер Hermes: строит knowledge-graph из разговоров и
ищет по нему сразу четырьмя стратегиями (смысл, ключевые слова, граф связей, время).
Ставим **локально**: база и эмбеддинги живут на своём сервере, наружу уходят только
запросы к LLM для извлечения фактов.

Полный рецепт со всеми граблями: **читай `references/hindsight-memory.md`** — там же
проверенный systemd-юнит и диагностика. Не пиши команды по памяти, следуй ранбуку.

**Сначала проверь, потянет ли сервер** (иначе не ставь — задушишь Hermes):
```bash
ssh hermes-vps "free -m | awk '/Mem:/{print \$2\" MB RAM\"}'; df -h / | awk 'NR==2{print \$4\" свободно\"}'"
```
Локальный Hindsight требует **~1.3 ГБ RAM** под демон и **~6 ГБ диска** (ML-стек в venv).
Мало ресурсов → предложи облачный режим (ключ с ui.hindsight.vectorize.io,
`hermes memory setup hindsight` → Cloud) либо пропусти фазу: встроенная память работает
и без этого. Спроси пользователя, что выбираем.

Порядок локальной установки (детали — в ранбуке): отдельный пользователь `hindsight`
(под root встроенный Postgres не стартует) → `pip install hindsight-all` в venv Hermes →
профиль демона → systemd-юнит на `127.0.0.1:8100` → `config.json` с `mode: local_external`
→ `hermes config set memory.provider hindsight`.

Хранение и поиск целиком локальные. LLM нужен только чтобы превращать текст диалога в
факты для графа — это массовая фоновая работа, поэтому бери **дешёвого провайдера с
большим лимитом токенов в минуту, а не самую умную модель**. Идеально — **Gonka**
(GonkaRouter/GonkaGate: ~$0.0004 за 1M токенов, $20 кредитов новым; проверено вживую);
годится и любой другой уже настроенный OpenAI-совместимый провайдер. ⚠ Не подсовывай
сюда бесплатный Groq (хоть его ключ и появится в Фазе 6 для голоса): лимит 8000
токенов/мин, а Hindsight шлёт запросы в разы больше — запись будет молча падать.

**Проверка:**
```bash
ssh hermes-vps "systemctl is-active hindsight && curl -s http://127.0.0.1:8100/health && hermes memory status"
```
Ждём `active`, `{"status":"healthy","database":"connected"}` и `Provider: hindsight`,
`Status: available ✓`. Затем живой смоук: сохрани факт в банк (curl из ранбука) и спроси
агента то, чего нет ни в промпте, ни в `MEMORY.md` — он должен ответить по памяти.
После настройки — `systemctl restart hermes-gateway`.

## Фаза 5 — Telegram-бот

1. Попроси пользователя: создать бота у @BotFather (`/newbot`) и прислать **token**;
   узнать свой числовой **user id** у @userinfobot.
2. Запиши в `/root/.hermes/.env`:
   ```
   TELEGRAM_BOT_TOKEN=<токен>
   TELEGRAM_ALLOWED_USERS=<user_id>
   ```
   ⚠ Вайтлист обязателен: Hermes fail-closed — но без `TELEGRAM_ALLOWED_USERS` бот будет
   отвечать отказом всем, включая владельца. Несколько id — через запятую.
3. Установи гейтвей как systemd-сервис (под root нужен явный `--run-as-user`):
   ```bash
   ssh hermes-vps "hermes gateway install --system --run-as-user root"
   ```
4. Проверь: `systemctl status hermes-gateway` — active (running).

⚠ **Грабли «бот молчит»:** из коробки Telegram-адаптер строит fallback-транспорт через
DoH-discovery запасных IP и на некоторых VPS **виснет навечно** на
«Connecting to Telegram (attempt 1/8)…», хотя прямой доступ к api.telegram.org работает. Фикс:
```bash
ssh hermes-vps "grep -q '^HERMES_TELEGRAM_DISABLE_FALLBACK_IPS=' /root/.hermes/.env || echo 'HERMES_TELEGRAM_DISABLE_FALLBACK_IPS=true' >> /root/.hermes/.env; systemctl restart hermes-gateway"
```
⚠⚠ Именно в `.env`, а **не** `hermes config set`: адаптер читает эту настройку только как
переменную окружения (`os.getenv`), моста «конфиг → env» в Hermes нет. `config set` молча
запишет ключ в `config.yaml`, и он не подействует — легко потерять час на ложный фикс.

⚠ Логи гейтвея в journalctl — только WARNING, «успех» там не виден. Поллинг проверяй по
соединениям: `ss -tnp | grep "$(systemctl show -p MainPID --value hermes-gateway)"` —
должны быть ESTABLISHED к api.telegram.org:443. **Не дёргай `getUpdates` вручную** при
живом гейтвее — украдёшь апдейты у бота (гонка, ошибка 409).

Доступ для других людей (коллега, семья) — через **DM-pairing**, а не ручное добавление
id: новый человек пишет боту и получает одноразовый код, владелец подтверждает на сервере
`hermes pairing approve <код>` (`hermes pairing list` — кто в ожидании, `revoke` —
отозвать). Это официально рекомендуемый способ командного доступа.

**Проверка:** пользователь пишет боту `/status` и получает ответ. Это единственный
настоящий смоук — попроси пользователя написать боту и подтвердить.

## Фаза 6 — Голос: распознавание (STT) и голосовые ответы (TTS)

Схема: голосовые из Telegram транскрибирует **Groq Whisper** (`whisper-large-v3-turbo`,
быстро и бесплатно), при недоступности Groq — **локальный faster-whisper** на CPU.
Обёртка `scripts/hermes-stt-wrapper.py` (в комплекте скилла) делает ровно это, плюс
чанкует файлы >25 МБ для Groq.

1. Попроси у пользователя Groq API key (console.groq.com, бесплатно).
2. Скопируй скрипт на сервер и подготовь:
   ```bash
   scp scripts/hermes-stt-wrapper.py hermes-vps:/usr/local/bin/hermes-stt-wrapper.py
   ssh hermes-vps "chmod +x /usr/local/bin/hermes-stt-wrapper.py && /usr/local/lib/hermes-agent/venv/bin/pip install faster-whisper requests"
   ```
   Shebang скрипта — `/usr/local/lib/hermes-agent/venv/bin/python`; если venv лежит
   иначе — поправь первую строку.
3. Прогрей локальную модель (скачает ~150 МБ, чтобы первый fallback не тормозил):
   ```bash
   ssh hermes-vps "/usr/local/lib/hermes-agent/venv/bin/python -c \"from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')\""
   ```
4. В `/root/.hermes/.env` добавь (ключ — не через echo!):
   ```
   STT_GROQ_API_KEY=<ключ>
   STT_GROQ_TIMEOUT=60
   STT_LOCAL_FALLBACK_MODEL=base
   HERMES_LOCAL_STT_COMMAND='/usr/local/bin/hermes-stt-wrapper.py {input_path} --output_dir {output_dir} --language {language} --model {model}'
   ```
5. Конфиг (язык спроси у пользователя; пусто = автоопределение):
   ```bash
   ssh hermes-vps "hermes config set stt.enabled true && hermes config set stt.provider local_command && hermes config set stt.local.language ru && systemctl restart hermes-gateway"
   ```

Упрощённый вариант (без локального fallback): `stt.provider groq` + тот же ключ — тогда
скрипт и faster-whisper не нужны.

**Голосовые ответы (TTS) — бесплатно, без ключей.** Провайдер `edge` (Microsoft Edge TTS,
пакет edge-tts) идёт в комплекте Hermes и не требует регистрации:
```bash
ssh hermes-vps "hermes config set tts.provider edge && hermes config set tts.edge.voice ru-RU-DmitryNeural && systemctl restart hermes-gateway"
```
Голос подбери под язык и вкус пользователя (`edge-tts --list-voices | grep ru-RU`;
женский — `ru-RU-SvetlanaNeural`). `voice.auto_tts` оставь выключенным (по умолчанию):
бот отвечает голосом, когда его попросят («ответь голосом»), а не на каждое сообщение.

**Проверка:** пользователь отправляет боту голосовое — бот отвечает по содержанию;
пользователь просит «ответь голосом» — приходит голосовое сообщение.

## Фаза 7 — Веб-поиск и парсинг

Подробности и конфиги: **читай `references/web-tools.md`**.

- **Brave Search** (поиск, основной): ключ Free plan → в `.env` `BRAVE_SEARCH_API_KEY=...`,
  затем `hermes config set web.search_backend brave-free`.
- **Без ключа** (если Brave-ключа пока нет): `hermes config set web.search_backend ddgs` —
  DuckDuckGo, регистрации не требует. Если бэкенд недоступен — доставь пакет:
  `/usr/local/lib/hermes-agent/venv/bin/pip install ddgs`. На Brave можно переключиться
  позже одной командой.
- **Firecrawl** (извлечение контента страниц): ключ → `FIRECRAWL_API_KEY=...` в `.env`,
  `hermes config set web.extract_backend firecrawl`.

После правок — `systemctl restart hermes-gateway`.

**Проверка:** `ssh hermes-vps "hermes -z 'Найди в вебе, какая сегодня стабильная версия Python, и назови её'"` —
в ответе видно, что поиск реально выполнялся; пользователь просит бота открыть конкретную
статью по URL — извлечение работает.

## Фаза 8 — Оживление: личность, дом и первый крон

Три маленьких шага, которые превращают «отвечалку» в собственного агента. Не пропускай —
это самая эмоционально ценная часть настройки, делай её вместе с пользователем.

1. **Личность (SOUL.md).** Спроси пользователя, каким должен быть его агент: имя, тон,
   язык, характер, о чём напоминать. Перепиши `/root/.hermes/SOUL.md` под это описание
   (это системная «душа» бота, читается каждую сессию — держи её короткой) и перезапусти
   гейтвей.
2. **Домашний канал.** Пользователь отправляет боту команду `/sethome` в том чате, куда
   бот должен писать по своей инициативе (кроны, уведомления).
3. **Первый крон — голосом или текстом.** Пользователь просто просит бота: «Каждое утро
   в 9:00 присылай мне план на день и погоду». Бот сам создаст задание через свой
   cronjob-тулсет. Заодно расскажи пользователю про память: фраза «запомни это на
   будущее» сохраняет факт навсегда (появится в контексте со следующей сессии).

**Проверка:** `ssh hermes-vps "hermes cron list"` — задание видно, плюс `hermes cron status`
(планировщик жив). Дождись срабатывания по расписанию или попроси пользователя сдвинуть
время на ближайшие минуты. ⚠ Не пытайся «прогнать вручную» вслепую: `hermes cron run`
требует id джобы и лишь ставит её на ближайший тик планировщика — мгновенного запуска
он не даёт.

## Фаза 9 — Финальная проверка и отчёт

1. `ssh hermes-vps "hermes doctor && hermes config check && hermes status"` — без ошибок.
2. `ssh hermes-vps "systemctl restart hermes-gateway && sleep 5 && systemctl is-active hermes-gateway"` → `active`.
3. Финальные смоуки с пользователем: текст боту → ответ; голосовое → ответ; «найди в
   интернете …» → ответ с поиском.
4. Сделай `hermes backup` (zip домашней директории) и скачай его на машину пользователя
   (`scp`) — бэкап, лежащий только на самом сервере, бесполезен при смерти диска.
   Расскажи правило на будущее: перед каждым `hermes update` — сначала `hermes backup`.
5. Выдай пользователю итоговый отчёт:
   - IP, способ входа (только ключ `~/.ssh/hermes_vps`), что закрыто фаерволом;
   - какие провайдеры/модели настроены (primary + fallback);
   - какие ключи лежат в `/root/.hermes/.env` (имена переменных, НЕ значения);
   - как управлять: `systemctl {status,restart} hermes-gateway`,
     `journalctl -u hermes-gateway -e`, `hermes model` (смена модели), `hermes status`;
   - что осталось ненастроенным (если пользователь что-то отложил).
6. Расскажи про **опциональные расширения ниже** — их можно добавить прямо сейчас или
   когда угодно позже, база уже полностью работает без них.

---

# Опциональные расширения (по желанию, можно позже)

База (Фазы 0–9) даёт полноценного бота. Ниже — необязательные апгрейды: предложи их
пользователю, но ставь только то, что он выбрал. Каждый ставится независимо и в любой
момент, не ломая базовую установку.

## Расширение A — Google Workspace: почта, календарь, диск

Подключить боту Gmail/Calendar/Drive/Sheets/Docs через CLI `gog` — тогда бот сможет
читать почту, управлять календарём и работать с документами.

Полная инструкция: **читай `references/google-workspace.md`**. Коротко: бинарь `gog`
с GitHub releases → пользователь создаёт OAuth-приложение в Google Cloud (Desktop app)
→ ⚠ обязательно переводит его в статус **In production** (в Testing refresh-токены
протухают через ~7 дней — бот потеряет доступ через неделю, и это выглядит как
загадочная поломка) → `gog auth credentials` + `gog auth add` на сервере.

**Проверка:** `gog auth list` показывает аккаунт; пользователь спрашивает бота
«что у меня в календаре на этой неделе?» — ответ по реальному календарю.

## Расширение B — Генерация изображений

В Hermes картинки — отдельный бэкенд (`image_gen.provider`), выбирается независимо от
текстовой модели. Предложи пользователю один провайдер по тому, что у него есть.
Полная инструкция: **читай `references/image-gen.md`**. Коротко — выбор из двух:

- **Есть Codex (настроен в Фазе 4):** нативный бэкенд `openai-codex` забандлен в Hermes,
  работает из коробки — две строки конфига (`image_gen.provider openai-codex`).
- **Есть Google Gemini Pro:** через официальный CLI `agy` (Google Antigravity) — ставится
  напрямую от Google, агент вызывает его в терминале для генерации (плагин не нужен).
  Полный runbook: `references/antigravity-cli.md`.

⚠ ID моделей генерации меняются — не хардкодь, сверяйся с актуальными (`agy models` /
текущая image-модель Codex).

**Проверка:** «нарисуй рыжего кота в шляпе» → приходит картинка.

## Расширение C — Продвинутые инструменты (парсинг и медиа)

Мощные апгрейды для парсинга защищённых сайтов и работы с медиа. Полные рецепты:
**читай `references/power-tools.md`**. Коротко:

- **CloakBrowser** — антидетект-Chromium для парсинга сайтов, где Firecrawl и обычный
  браузер упираются в капчу/Cloudflare. Ставится в venv (через `uv`), подключается к
  Hermes по CDP (`browser.cdp_url` — адрес loopback задаёшь сам, дефолта нет).
- **yt-dlp** — скачивание с YouTube и сотен сайтов; вместе с POT-провайдером bgutil
  (Docker, `127.0.0.1:4416`) обходит «докажи, что не бот».
- **NotebookLM CLI** (`notebooklm-py` через uv) — блокноты NotebookLM из терминала;
  авторизация переносом `storage_state.json` с машины пользователя.

⚠ Все три дают агенту доступ к браузеру/сети/чужим аккаунтам — ставь только по явной
просьбе, вспомогательные сервисы держи на `127.0.0.1`, сессии не логируй.

## Если что-то пошло не так

- Бот не отвечает → Фаза 5, грабли fallback-IP; затем `journalctl -u hermes-gateway -e --no-pager | tail -50`.
- Ответы «отказано» владельцу → `TELEGRAM_ALLOWED_USERS` не задан или не тот id.
- Голос не распознаётся → запусти обёртку руками на тестовом файле; смотри stderr (`[hermes-stt]`).
- Модель не отвечает → `hermes -z` смоук + проверь провайдера raw-запросом
  (см. references/providers.md §Диагностика). ⚠ Смоук через Hermes с fallback-цепочкой
  НЕнадёжен для диагностики конкретного провайдера: при отказе primary он молча уйдёт в
  fallback и вернёт OK. Проверяй провайдера прямым HTTP-запросом.
- Потерял SSH-доступ → консоль восстановления в панели хостера (VNC/rescue), там откати
  `/etc/ssh/sshd_config.d/99-hermes.conf` или `ufw disable`.
