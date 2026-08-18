# LLM-провайдеры для Hermes

Hermes различает **primary** модель (`model.provider` + `model.default`) и
**fallback-цепочку** (`fallback_providers`) — список моделей, которые пробуются по
порядку, когда primary отвалился (квота, 5xx, таймаут). Для семинарной установки
цель: один надёжный primary + 1–3 бесплатных fallback'а.

Общие правила:
- **Не хардкодь ID моделей из головы** — каталоги меняются каждый месяц. Смотри живой
  список: `hermes model` (интерактивный пикер) или API провайдера (`GET /v1/models`).
- Ключи — только в `/root/.hermes/.env` (chmod 600), в конфиге — имя переменной
  (`key_env`), не значение.
- После смены провайдера/ключей: `systemctl restart hermes-gateway`.

## 1. Nous Portal (родной, рекомендую первым)

Hermes сделан Nous Research; у портала есть бесплатные модели и OAuth-вход без ключей.

```bash
ssh -t hermes-vps "hermes portal"
```

Интерактивная сессия (`-t` обязателен): команда напечатает URL — перешли его
пользователю, он откроет на своей машине, залогинится и подтвердит. После логина
мастер сам предложит выбрать модель и назначить Nous провайдером.

⚠ После логина в пикере видно 300+ моделей, но **без списания кредитов работают только
модели с тегом `:free`** — для бесплатного старта выбирай строго их. По акциям Nous
периодически даёт бесплатно и топ-модели (раздавали, например, Nemotron 3 Ultra) —
актуальный список смотри прямо в пикере `hermes model`.

Проверка: `hermes portal info` — auth OK; `hermes -z 'PONG?'`.

## 2. OpenRouter (много бесплатных моделей)

1. Пользователь берёт ключ на openrouter.ai → Keys.
2. В `.env`: `OPENROUTER_API_KEY=<ключ>`.
3. Бесплатные модели имеют суффикс `:free`. Актуальный список:
   ```bash
   curl -s https://openrouter.ai/api/v1/models | jq -r '.data[] | select(.pricing.prompt=="0") | .id' | head -20
   ```
4. Установи primary (пример — подставь живую модель из списка):
   ```bash
   hermes config set model.provider openrouter
   hermes config set model.default <автор>/<модель>:free
   ```

## 3. Codex / ChatGPT (подписка Plus/Pro)

Если у пользователя есть подписка ChatGPT — Hermes умеет ходить в неё через встроенный
провайдер `openai-codex` (использует OAuth Codex CLI, квота подписки, без API-ключа).

1. **Сначала включи device-авторизацию в аккаунте ChatGPT** (это новый флоу, по умолчанию
   бывает выключен). Пользователь заходит на chatgpt.com → **Settings → Security** и включает
   **device code authorization** (авторизация по коду устройства). Без этого шага логин с
   сервера будет отбит — это первая причина «код не принимается». Сделай это до шага 3.
2. Поставь Codex CLI: `ssh hermes-vps "npm i -g @openai/codex"`
   (node ставится инсталлером Hermes; если npm нет — `apt-get install -y nodejs npm`).
3. Логин device-флоу (без браузера на сервере):
   ```bash
   ssh -t hermes-vps "codex login --device-auth"
   ```
   CLI печатает короткий код и URL. Пользователь открывает URL на своей машине, вводит код,
   подтверждает — токен ляжет в `/root/.codex/auth.json` (access ~10 дней, auto-refresh).
4. Назначь модель: `hermes model` → провайдер `openai-codex`, выбери GPT-модель из списка.

⚠ Грабли OAuth Codex (проверено болью):
- **Refresh-токены одноразовые: один аккаунт = один клиент.** Не логинь этот же аккаунт
  в Codex CLI на других машинах — украдёшь lineage токена, и сервер разлогинится.
- После пере-логина рестартуй гейтвей.
- `hermes status` может показывать auth OK при уже отозванном токене — истина только в
  реальном запросе (`hermes -z` без fallback или raw-запрос).

## 4. Groq как LLM (бонусом к голосу)

Тот же ключ `console.groq.com`. Быстрый бесплатный inference (llama и др.) — хороший
fallback. В `.env`: `GROQ_API_KEY=<ключ>`; дальше `hermes model` → groq, либо custom
provider (см. §5) с `base_url: https://api.groq.com/openai/v1`, если groq не виден
в пикере.

## 5. Любой OpenAI-совместимый шлюз (custom provider)

Секция `providers.<id>` в `/root/.hermes/config.yaml` (keyed-схема, config v33+):

```yaml
providers:
  mygateway:
    name: My Gateway
    base_url: https://api.example.com/v1
    api_mode: chat_completions
    key_env: MYGATEWAY_API_KEY   # значение — в .env
    discover_models: true         # подтянуть /v1/models автоматически
```

Использование: `hermes -z "..." --provider custom:mygateway -m <model>` или назначь
primary через `hermes model`. Так подключаются OpenRouter-подобные агрегаторы,
NVIDIA NIM (`https://integrate.api.nvidia.com/v1`, ключ бесплатный на build.nvidia.com),
самодельные прокси и т.п.

## 5½. CLIProxyAPI — пул OAuth-подписок как один API (продвинутое)

Локальный OpenAI-совместимый прокси, который объединяет **CLI-логины подписок** и
**ключи Google AI Studio** в один эндпоинт с ротацией аккаунтов. Реальные варианты логина
в текущем образе (проверено `--help` бинаря): Codex/ChatGPT, Claude, Antigravity, Kimi,
xAI, импорт Vertex. ⚠ Qwen и Gemini CLI среди них нет — не обещай их пользователю.

Зачем участнику: гонять Hermes через уже оплаченные подписки без пер-токенных
API-плат, а бесплатные Gemini-ключи ротировать, чтобы обходить рейт-лимиты. Опционально и
продвинуто — ставь по запросу; для одного провайдера проще native `hermes portal`/
`openai-codex` (см. выше).

Ставится Docker'ом (проверено на Linode):

```bash
ssh hermes-vps 'set -e
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
mkdir -p /opt/cli-proxy-api/auths /opt/cli-proxy-api/logs
CLIENT_KEY="sk-cliproxy-$(openssl rand -hex 24)"
MGMT_KEY="$(openssl rand -hex 24)"
cat > /opt/cli-proxy-api/config.yaml <<EOF
host: "0.0.0.0"          # внутри контейнера; наружу только 127.0.0.1 через compose
port: 8317
tls: { enable: false }
remote-management:
  allow-remote: false    # панель управления только с localhost (через SSH-туннель)
  secret-key: "$MGMT_KEY"
  disable-control-panel: false
auth-dir: "/root/.cli-proxy-api"
api-keys:
  - "$CLIENT_KEY"        # клиентский Bearer — его же кладём в Hermes .env
debug: false
EOF
cat > /opt/cli-proxy-api/docker-compose.yml <<EOF
services:
  cli-proxy-api:
    image: eceasy/cli-proxy-api:latest
    container_name: cli-proxy-api
    restart: unless-stopped
    ports: ["127.0.0.1:8317:8317"]
    volumes:
      - ./config.yaml:/CLIProxyAPI/config.yaml
      - ./auths:/root/.cli-proxy-api
      - ./logs:/CLIProxyAPI/logs
EOF
echo "$CLIENT_KEY" > /root/.cliproxy_client_key && chmod 600 /root/.cliproxy_client_key
cd /opt/cli-proxy-api && docker compose up -d'
```

⚠ Прокси публикуется только на `127.0.0.1:8317`. Клиентский и management-ключи не
выводить в чат/логи; при пересоздании — генерировать новые (`openssl rand`), не
переиспользовать чужие.

**Добавить бэкенды (без них `/v1/models` пуст — прокси есть, моделей нет):**
- **Google AI Studio (Gemini, бесплатно, проще всего):** пользователь берёт ключи на
  aistudio.google.com, добавляем секцию в config.yaml (несколько ключей = ротация лимитов):
  ```yaml
  gemini-api-key:
    - api-key: "AIza..."
    - api-key: "AIza..."   # второй ключ — для обхода бесплатных лимитов
  ```
  После правки перезапусти контейнер, чтобы изменения гарантированно подхватились:
  `cd /opt/cli-proxy-api && docker compose restart`.
- **OAuth-логины подписок (Codex/ChatGPT, Claude, Kimi, xAI, Antigravity):** device-флоу
  внутри контейнера. ⚠ Бинарь внутри лежит по пути `/CLIProxyAPI/CLIProxyAPI`, а не в
  `$PATH` — короткая форма `docker exec ... cli-proxy-api ...` падает с
  `executable file not found`. Правильно:
  ```bash
  docker exec -it cli-proxy-api /CLIProxyAPI/CLIProxyAPI -codex-device-login
  ```
  Пользователь открывает URL и вводит код (в аккаунте ChatGPT должна быть включена
  device-code авторизация). Другие флаги логина: `-claude-login`, `-kimi-login`,
  `-xai-login`, `-antigravity-login`, `-vertex-import`.
  ⚠ Refresh-токены одноразовые: один аккаунт → один клиент; не логинить его же в других местах.

**Прокинуть в Hermes** (custom-провайдер + клиентский ключ в `.env`):
```yaml
providers:
  cliproxy:
    name: CLIProxy
    base_url: http://127.0.0.1:8317/v1
    key_env: CLIPROXY_API_KEY
    discover_models: true    # список моделей подтянется из прокси
```
```
CLIPROXY_API_KEY=<клиентский ключ из /root/.cliproxy_client_key>
```

**Проверка** (проверено вживую — путь рабочий, при 0 бэкендов вернёт 0 моделей):
```bash
ssh hermes-vps 'K=$(cat /root/.cliproxy_client_key); curl -s http://127.0.0.1:8317/v1/models -H "Authorization: Bearer $K" | python3 -c "import json,sys;print(len(json.load(sys.stdin).get(\"data\",[])), \"models\")"'
```
Число моделей > 0 → есть рабочие бэкенды. Затем изолированный смоук:
`hermes -z 'PONG?' --provider custom:cliproxy -m <id-из-списка>`.

## 6. Gonka: GonkaRouter и GonkaGate (дешёвый inference, $20 на старт)

Два независимых шлюза к децентрализованной сети Gonka (открытые модели уровня
MiniMax M2.7, Kimi K2.6 по очень низким ценам). Оба OpenAI-совместимые,
подключаются как custom-провайдеры. Хороши как дешёвый primary или средние звенья
fallback-цепочки.

- **GonkaRouter** (gonkarouter.io): новым пользователям — **$20 кредитов** на старт.
  Пользователь жмёт «Get API Keys», регистрируется, отдаёт ключ.
- **GonkaGate** (gonkagate.com): prepaid-баланс в USD, без крипто-кошельков.
  «Get API Key» на сайте.

В `.env`:
```
GONKAROUTER_API_KEY=<ключ>
GONKAGATE_API_KEY=<ключ>
```

В `config.yaml` (секция `providers:`):
```yaml
providers:
  gonkarouter:
    name: GonkaRouter
    base_url: https://api.gonkarouter.io/v1
    api_mode: chat_completions
    key_env: GONKAROUTER_API_KEY
    discover_models: false
    models:
      - MiniMaxAI/MiniMax-M2.7
      - moonshotai/Kimi-K2.6
  gonkagate:
    name: GonkaGate
    base_url: https://api.gonkagate.com/v1
    api_mode: chat_completions
    key_env: GONKAGATE_API_KEY
    discover_models: false
    models:
      - minimaxai/minimax-m2.7
      - moonshotai/kimi-k2.6
```

⚠ Обрати внимание: **ID моделей у двух шлюзов различаются регистром и написанием**
(`MiniMaxAI/MiniMax-M2.7` у Router против `minimaxai/minimax-m2.7` у Gate) — не
копируй ID между ними, сверяй со страницей Models конкретного сервиса. Актуальный
каталог можно подтянуть и автоматически: поставь `discover_models: true`, если
`GET /v1/models` у сервиса отвечает.

Смоук после подключения (изолированно, без fallback):
```bash
hermes -z 'Ответь одним словом: PONG' --provider custom:gonkarouter -m MiniMaxAI/MiniMax-M2.7
```

## 7. Fallback-цепочка

```bash
ssh -t hermes-vps "hermes fallback add"
```
Интерактивно добавь 1–3 бесплатных модели из УЖЕ настроенных провайдеров. Порядок =
порядок перебора. Хорошая семинарная цепочка: primary платный/подписочный → free-модель
OpenRouter → free-модель Nous; если подключён Gonka (GonkaRouter/GonkaGate) — вставь
его между ними как дешёвое надёжное звено.

## Диагностика провайдеров

⚠ **Смоук через Hermes не изолирует провайдера**: при отказе primary Hermes молча
уходит в fallback и возвращает успех — ты решишь, что провайдер X жив, а работал Y.
Для проверки конкретного провайдера делай raw-запрос (ключ подставляется из .env на
сервере, не выводи его):

```bash
ssh hermes-vps 'set -a; . /root/.hermes/.env; set +a; curl -s -o /dev/null -w "%{http_code}\n" https://openrouter.ai/api/v1/chat/completions -H "Authorization: Bearer $OPENROUTER_API_KEY" -H "Content-Type: application/json" -d "{\"model\":\"<id>\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":5}"'
```

Какая модель реально отвечала в диалоге: `grep "API call #" /root/.hermes/logs/agent.log`.
