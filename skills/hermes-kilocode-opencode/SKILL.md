---
name: hermes-kilocode-opencode
description: >
  Опциональное дополнение к установленному Hermes Agent: подключение провайдеров с дешёвыми
  и бесплатными coding-моделями — Kilocode (вход `kilo auth login`, курированный каталог
  free-моделей kilo-auto/free, deepseek/nemotron/step :free) и OpenCode Zen (ключ с
  opencode.ai). Оба — встроенные в Hermes провайдеры типа api_key; Kilocode дополнительно
  получает keyed-блок с каталогом бесплатных моделей (копия рабочего конфига). Используй,
  когда у пользователя уже стоит Hermes и он просит «добавь kilocode», «подключи opencode
  zen», «настрой бесплатные модели kilo/opencode», «войти в kilocode», «дешёвые coding-модели
  в Hermes».
---

# Kilocode и OpenCode Zen для Hermes

Подключение к уже установленному Hermes двух провайдеров с бесплатными/дешёвыми
coding-моделями. Оба зарегистрированы в Hermes как встроенные провайдеры
(`kilocode`, `opencode-zen`, тип `api_key`, endpoint зашит) — **отдельных плагинов ставить
не нужно**. Ценность конфига: у Kilocode добавляется keyed-блок с готовым каталогом
бесплатных моделей (иначе их пришлось бы искать вручную) — это копия рабочей настройки.

Предусловие: Hermes уже установлен и работает (например, по скиллу `hermes-vps-setup`).
Команды — на сервере через `ssh <хост>`; секреты в `/root/.hermes/.env` (chmod 600),
значения токенов в чат/логи не выводить. После правок — `systemctl restart hermes-gateway`.

Спроси пользователя, что подключаем — Kilocode, OpenCode Zen или оба.

---

## Провайдер A — Kilocode (вход `kilo auth login` + каталог free-моделей)

Токен получаем входом через официальный CLI `kilo`; он же — долгоживущий (у выданного
JWT срок ~годы). Затем прописываем keyed-блок `providers.kilocode` с каталогом бесплатных
моделей — точная копия того, как это сделано на рабочем сервере.

1. **Установка CLI:**
   ```bash
   ssh hermes-vps "npm i -g @kilocode/cli && kilo --version"
   ```
   (Node ставится инсталлером Hermes; если npm нет — `apt-get install -y nodejs npm`.)

2. **Вход** (на headless-сервере — по ссылке):
   ```bash
   ssh -t hermes-vps "kilo auth login"
   ```
   CLI печатает URL — пользователь открывает на своей машине, логинится в Kilocode,
   подтверждает. Токен сохраняется в `~/.config/kilo/kilo.jsonc`; `kilo auth list` — проверка.

3. **Токен в Hermes.** Впиши выданный токен в `.env` как `KILOCODE_API_KEY=...` (значение
   не печатать в чат). Если извлекать из `kilo.jsonc` неудобно/структура иная — попроси
   пользователя взять API-ключ в дашборде kilocode.ai и продиктовать. Токен не выдумывать.

4. **Провайдер-блок с каталогом free-моделей** — впиши в `/root/.hermes/config.yaml`
   секцию `providers.kilocode` (это и есть «как у нас»; каталог — актуальный на момент
   написания, сверь живой список через `kilo` или дашборд и поправь при расхождении):
   ```yaml
   providers:
     kilocode:
       name: Kilocode
       base_url: https://api.kilo.ai/api/gateway
       key_env: KILOCODE_API_KEY
       discover_models: false
       models:
         kilo-auto/free:               { context_length: 256000 }
         deepseek/deepseek-v4-flash:free: { context_length: 1048576 }
         nvidia/nemotron-3-super-120b-a12b:free: { context_length: 1000000 }
         nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free: { context_length: 256000 }
         stepfun/step-3.5-flash:free:  { context_length: 262144 }
         poolside/laguna-m.1:free:     { context_length: 131072 }
         poolside/laguna-xs.2:free:    { context_length: 131072 }
         x-ai/grok-code-fast-1:optimized:free: { context_length: 256000 }
         openrouter/free:              { context_length: 200000 }
   ```
   ⚠ Каталог бесплатных моделей у Kilocode меняется — не считай список вечным, сверяйся.
   ⚠ Имя секции совпадает со встроенным провайдером, и при `--provider kilocode` Hermes
   берёт именно встроенного (base_url тот же, поэтому всё работает). Смысл блока — иметь
   под рукой список бесплатных моделей; если нужен именно свой блок, назови секцию иначе
   и обращайся к ней как `--provider custom:<имя>`.

5. **Выбрать модель / проверить:**
   ```bash
   ssh -t hermes-vps "hermes model"     # провайдер kilocode → бесплатная модель
   ssh hermes-vps "hermes -z 'Ответь одним словом: PONG' --provider kilocode -m kilo-auto/free"
   ```
   Изолированный `--provider kilocode` важен: общий смоук спрячет отказ за fallback.

---

## Провайдер B — OpenCode Zen (ключ с opencode.ai)

OpenCode Zen — pay-as-you-go гейтвей coding-моделей от команды OpenCode (есть бесплатные).
Встроенный провайдер Hermes `opencode-zen` (endpoint `https://opencode.ai/zen/v1` зашит,
тип `api_key`) — отдельный провайдер-блок не нужен, только ключ.

1. **Получить ключ:** пользователь заходит на **opencode.ai/auth**, входит, при желании
   добавляет платёжные данные (для платных моделей; бесплатные доступны и так), копирует
   API-ключ раздела Zen. (Через CLI OpenCode — `opencode auth login` → «OpenCode Zen».)

2. **Подключить в Hermes** (родной setup-флоу сам пропишет ключ):
   ```bash
   ssh -t hermes-vps "hermes model"     # выбрать opencode-zen → вставить ключ → выбрать модель
   ```
   Вручную: `OPENCODE_ZEN_API_KEY=...` в `.env`, затем `hermes config set model.provider opencode-zen`.

3. **Проверка:**
   ```bash
   ssh hermes-vps "hermes -z 'Ответь одним словом: PONG' --provider opencode-zen -m <модель-из-пикера>"
   ```
   ⚠ У OpenCode Zen плоское пространство имён моделей — точный ID бери из `hermes model`
   или /models на opencode.ai, не угадывай.

---

## В fallback-цепочку (рекомендуется)

Бесплатные модели — хорошие запасные звенья:
```bash
ssh -t hermes-vps "hermes fallback add"    # добавить kilocode/kilo-auto/free и/или opencode-zen модель
```
Порядок = порядок перебора; бесплатные — ниже основной модели.

## Безопасность
- Токены (`KILOCODE_API_KEY`, `OPENCODE_ZEN_API_KEY`, `kilo.jsonc`) — секреты: не выводить
  в чат/логи, `.env` в chmod 600.
- После изменений — `systemctl restart hermes-gateway`; провайдера проверять прямым
  `hermes -z --provider <id>`, а не общим смоуком (иначе отказ спрячется за fallback).
