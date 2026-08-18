# Runbook: Hindsight — улучшенная память (локально, self-hosted)

Hindsight — нативный memory-провайдер Hermes: строит knowledge-graph из разговоров и
умеет retain / recall / reflect (семантический + BM25 + графовый + временной поиск с
переранжированием). Встроенные `MEMORY.md`/`USER.md` при этом продолжают работать.

Здесь — **локальный режим**: всё крутится на своём сервере (встроенный PostgreSQL,
локальные эмбеддинги), наружу уходят только запросы к LLM для извлечения фактов.
Весь рецепт целиком прогнан вживую на чистом Ubuntu 24.04 — включая грабли ниже.

## Прежде чем ставить — трезвая оценка ресурсов (проверено)

| Ресурс | Факт с боевого прогона |
|---|---|
| Диск | venv Hermes разрастается до **~6 ГБ** (тянется ML-стек), плюс ~350 МБ данных |
| RAM | демон в покое держит **~1.3 ГБ** RSS |
| Время | установка `hindsight-all` — единицы минут, первый старт демона ещё ~1–2 мин |

⚠ На VPS с 1–2 ГБ RAM или диском 25 ГБ **не ставь локальный режим** — не влезет либо
задушит Hermes. Для маленьких боксов бери облачный режим (ключ с ui.hindsight.vectorize.io,
`hermes memory setup hindsight` → Cloud) или оставь встроенную память.

## Шаг 1. Отдельный пользователь (обязательно)

⚠ **Встроенный PostgreSQL Hindsight отказывается запускаться под root**
(`initdb: cannot be run as root`), а Hermes у нас стоит под root. Поэтому демон живёт
под отдельным непривилегированным пользователем, а Hermes ходит к нему по HTTP на loopback.

```bash
ssh hermes-vps "id hindsight >/dev/null 2>&1 || useradd -m -s /bin/bash hindsight"
```

## Шаг 2. Установка движка

```bash
ssh hermes-vps "/usr/local/lib/hermes-agent/venv/bin/pip install hindsight-all"
```
Ставится в venv Hermes; появляются `hindsight-embed`, `hindsight-api`, `hindsight-worker`.
Это долго — запускай так, чтобы не оборвалось по таймауту сессии.

## Шаг 3. Профиль и LLM-ключ для самого Hindsight

Демону нужен LLM — но **не для общения, а для записи**: он читает текст диалога и
вытаскивает из него факты, сущности и связи для графа. Поиск (recall) моделью не пользуется:
это локальные эмбеддинги + BM25 + обход графа + реранкер, всё на сервере.

**Какой LLM брать.** Это фоновая массовая работа: много больших запросов, интеллекта
уровня «вытащи факты из текста». Значит нужен **дешёвый провайдер с щедрым лимитом
токенов в минуту (TPM)**, а не самая умная модель. Умный дорогой «мозг» из Фазы 4 сюда
ставить расточительно.

**Лучший выбор — Gonka** (GonkaRouter / GonkaGate из `providers.md` §6): цена уровня
$0.0004 за 1M токенов, у GonkaRouter новым пользователям $20 кредитов — при таких
объёмах памяти этого хватает надолго. Подходит любая из их открытых моделей
(живой каталог сейчас — MiniMax и Kimi; сверяйся с `/v1/models` шлюза). **Проверено вживую:** на GonkaRouter с `MiniMaxAI/MiniMax-M2.7`
извлечение фактов отработало без ошибок, одна фраза → 4 новых факта в графе, расход
~3.6k токенов на retain (то есть доли цента).

```bash
ssh hermes-vps 'VBIN=/usr/local/lib/hermes-agent/venv/bin
cd /home/hindsight
sudo -u hindsight env "PATH=$VBIN:/usr/bin:/bin" HOME=/home/hindsight bash -c "
  hindsight-embed profile create hermes --port 8100
  hindsight-embed profile set-env hermes HINDSIGHT_API_LLM_PROVIDER openai
  hindsight-embed profile set-env hermes HINDSIGHT_API_LLM_BASE_URL https://api.gonkarouter.io/v1
  hindsight-embed profile set-env hermes HINDSIGHT_API_LLM_API_KEY <GONKAROUTER_КЛЮЧ>
  hindsight-embed profile set-env hermes HINDSIGHT_API_LLM_MODEL MiniMaxAI/MiniMax-M2.7
"'
```
⚠ У GonkaGate ID моделей пишутся иначе (`minimaxai/minimax-m2.7` вместо
`MiniMaxAI/MiniMax-M2.7`) — сверяйся с каталогом того шлюза, который берёшь.

Годится и любой другой OpenAI-совместимый эндпоинт: OpenRouter (проверен вживую,
`https://openrouter.ai/api/v1` + бесплатная модель), CLIProxy, Nous, aiand — просто
подставь `BASE_URL`, ключ и модель. Есть и родные провайдеры вместо `openai`:
`groq`, `gemini`, `anthropic`, `deepseek`, `minimax`, `zai`, `ollama`.

⚠ **Требование к TPM жёсткое:** при извлечении фактов Hindsight шлёт запросы до ~67 000
токенов за раз (замерено). Провайдер с узким лимитом будет молча заваливать сохранение
диалогов — растёт `failed_operations`, а память остаётся пустой.

Профиль и env лягут в `/home/hindsight/.hindsight/profiles/hermes.env`.
Эмбеддинги и реранкер по умолчанию локальные (скачаются сами), БД — встроенная pg0.

⚠ **НЕ бери сюда бесплатный Groq**, хотя ключ от него у пользователя уже есть (мы выдаём
его в Фазе 6 для голоса — соблазн велик). Проверено на живом прогоне, ловится две беды:
1. Hindsight по умолчанию шлёт `service_tier: auto`, а free-тариф его не поддерживает →
   retain падает с `400 ... service_tier auto is not available for this org`. Лечится
   `hindsight-embed profile set-env hermes HINDSIGHT_API_LLM_GROQ_SERVICE_TIER on_demand`.
2. Но и после этого упирается в **лимит 8000 токенов/мин**: одиночный ручной retain
   проходит, а сохранение реальных диалогов валится с `HTTP 413 ... rate_limit_exceeded`,
   и в статистике молча растёт `failed_operations`. Для голоса Groq отличный, для
   Hindsight — нет.

**Хочется, чтобы наружу вообще ничего не уходило?** Тогда `HINDSIGHT_API_LLM_PROVIDER=ollama`
+ `HINDSIGHT_API_LLM_BASE_URL=http://localhost:11434/v1` + модель уровня `gemma3:12b`.
Честно: этот путь я не прогонял, и он требует другого железа — поверх ~1.3 ГБ, которые
занимает сам Hindsight, локальной модели нужно ещё несколько ГБ RAM, так что реалистично
это бокс от 8–16 ГБ. На типовом VPS 2 ядра / 4 ГБ извлечение фактов будет мучительно
медленным, а качество фактов у маленькой модели заметно хуже. Хранение и поиск при этом
локальны в любом случае — наружу уходит только извлечение фактов.

## Шаг 4. Запуск демона как сервиса (переживает ребут)

⚠ Сам по себе `hindsight-embed daemon start` **не создаёт systemd-юнит** — после
перезагрузки память просто не поднимется. Юнит ниже проверен вживую (`daemon start`
уходит в фон сам, поэтому `Type=oneshot` + `RemainAfterExit`, а не `simple`):

```bash
ssh hermes-vps 'cat > /etc/systemd/system/hindsight.service <<EOF
[Unit]
Description=Hindsight memory daemon (local, for Hermes)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=hindsight
Group=hindsight
WorkingDirectory=/home/hindsight
Environment=HOME=/home/hindsight
Environment=PATH=/usr/local/lib/hermes-agent/venv/bin:/usr/bin:/bin
ExecStart=/usr/local/lib/hermes-agent/venv/bin/hindsight-embed -p hermes daemon start
ExecStop=/usr/local/lib/hermes-agent/venv/bin/hindsight-embed -p hermes daemon stop
TimeoutStartSec=900

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now hindsight'
```

⚠ **Вторая грабля запуска:** демон обязан стартовать из директории, которую читает
пользователь `hindsight` (в юните это `WorkingDirectory=/home/hindsight`). Если запустить
из `/root`, библиотека настроек пытается прочитать `.env` из текущей директории и падает
с `PermissionError: [Errno 13] Permission denied: '.env'`.

**Проверка:**
```bash
ssh hermes-vps "systemctl is-active hindsight && curl -s http://127.0.0.1:8100/health"
```
Ожидаем `active` и `{"status":"healthy","database":"connected"}`.

## Шаг 5. Подключить Hermes к локальному инстансу

```bash
ssh hermes-vps 'mkdir -p /root/.hermes/hindsight && cat > /root/.hermes/hindsight/config.json <<EOF
{
  "mode": "local_external",
  "api_url": "http://127.0.0.1:8100",
  "bank_id": "hermes",
  "recall_budget": "mid",
  "memory_mode": "hybrid",
  "auto_retain": true,
  "auto_recall": true
}
EOF
hermes config set memory.provider hindsight
systemctl restart hermes-gateway'
```
`mode: local_external` = «подключись к уже поднятому инстансу» (наш демон).
Альтернатива в мастере — `hermes memory setup hindsight`, но он интерактивный и по
умолчанию предлагает cloud; конфиг выше делает то же самое без диалога.

**Проверка связки:**
```bash
ssh hermes-vps "hermes memory status"
```
Ожидаем `Provider: hindsight`, `Plugin: installed ✓`, `Status: available ✓`.

## Шаг 6. Живая проверка памяти (обязательно)

Не верь статусам — проверь реальный round-trip. Сохранить факт напрямую в банк:
```bash
ssh hermes-vps 'curl -s -X POST http://127.0.0.1:8100/v1/default/banks/hermes/memories \
 -H "Content-Type: application/json" \
 -d "{\"items\":[{\"content\":\"Любимый цвет владельца — зелёный.\"}],\"async\":false}"'
```
Ожидаем `"success":true`. Затем спроси агента то, чего нет ни в промпте, ни в `MEMORY.md`:
```bash
ssh hermes-vps "hermes -z 'Какой у меня любимый цвет? Ответь по памяти.'"
```
Агент должен ответить по факту из Hindsight. (На боевом прогоне обычная фраза давала 3–4 факта и связи в графе, а агент
корректно отвечал, собрав их из памяти.)

Затем проверь **автосохранение диалогов** — оно ломается чаще всего (упирается в лимиты
LLM). Поговори с ботом парой реплик, подожди ~1–2 минуты и посмотри статистику:
```bash
ssh hermes-vps 'curl -s http://127.0.0.1:8100/v1/default/banks/hermes/stats \
 | python3 -c "import json,sys;d=json.load(sys.stdin);print(\"фактов:\",d[\"total_nodes\"],\"документов:\",d[\"total_documents\"],\"ошибок:\",d[\"failed_operations\"])"'
```
Растут `total_documents`/`total_nodes` → автосохранение живое. Растёт `failed_operations`
→ смотри лог: почти всегда это лимиты LLM-провайдера (см. ⚠ про TPM выше), а не Hindsight.

Полезное для диагностики:
```bash
curl -s http://127.0.0.1:8100/v1/default/banks/hermes/stats     # сколько фактов/связей
sudo -u hindsight tail -f /home/hindsight/.hindsight/profiles/hermes.log
```

## Как это работает в бою

- `auto_recall` — перед ответом Hermes фоново запрашивает банк и подмешивает найденное
  в контекст блоком «Hindsight Memory (persistent cross-session context)».
- `auto_retain` — реплики разговора уходят в банк, откуда LLM извлекает факты и строит граф.
  Извлечение стоит токенов LLM Hindsight'а: на маленькой модели дёшево, но не бесплатно.
- `recall_budget`: `low` / `mid` / `high` — глубина поиска против скорости и токенов.
- Данные переживают рестарт демона (проверено). ⚠ Бэкапить надо **всю домашнюю директорию
  пользователя `/home/hindsight/`** (~350 МБ): сама база лежит в `/home/hindsight/.pg0/`
  (встроенный PostgreSQL), кэш моделей эмбеддингов/реранкера — в `/home/hindsight/.cache/`,
  а в `/home/hindsight/.hindsight/` только профиль и логи (~200 КБ). Бэкап одной лишь
  `.hindsight/` = потеря всей памяти.

## Откат

```bash
ssh hermes-vps "hermes memory off && systemctl restart hermes-gateway"   # вернуться на встроенную память
ssh hermes-vps "systemctl disable --now hindsight"                       # остановить демон
```
Встроенные `MEMORY.md`/`USER.md` никуда не деваются и продолжают работать.
