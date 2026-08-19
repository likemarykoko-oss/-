# Ручной ранбук: Hermes на 216.57.111.124

Адаптация скилла `hermes-vps-setup` под ручной запуск — когда агент не может
ходить по SSH сам (см. `docs/environment-blocker.md`). Команды из скилла вида
`ssh hermes-vps "..."` здесь выполняются **прямо на сервере**: через веб-консоль
хостера или из своего терминала.

Правило то же, что в скилле: **фаза за фазой, с проверкой**. Не переходи к
следующей, пока текущая не подтверждена. После каждой фазы присылай агенту вывод —
он проверит и даст следующий шаг.

---

## Как доставить скрипты на сервер

На сервере (веб-консоль хостера или SSH):

```bash
apt-get update && apt-get -y install git
git clone https://github.com/likemarykoko-oss/- /opt/hermes-setup
cd /opt/hermes-setup && git checkout claude/hermes-server-setup-ycayqd
cd scripts
```

Если репозиторий приватный и git с сервера не пускает — открой нужный скрипт на
GitHub, скопируй содержимое и вставь на сервере через `cat > 10-base.sh <<'EOF' ... EOF`.

---

## Фаза 0 — доступ по SSH-ключу

**Шаг 0.1 — на СВОЕЙ машине** (не на сервере), создай ключ:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/hermes_vps -N "" -C "hermes-vps"
```

**Шаг 0.2 — на СВОЕЙ машине**, доставь публичный ключ (спросит пароль root —
вводишь его сам, агент пароль не видит и не обрабатывает):

```bash
ssh-copy-id -i ~/.ssh/hermes_vps.pub root@216.57.111.124
```

**Шаг 0.3 — на СВОЕЙ машине**, добавь в `~/.ssh/config`:

```
Host hermes-vps
    HostName 216.57.111.124
    User root
    IdentityFile ~/.ssh/hermes_vps
```

**Проверка Фазы 0:**

```bash
ssh -o BatchMode=yes hermes-vps "echo OK"
```

Должно вернуть `OK` без запроса пароля. Дальше можно работать через `ssh hermes-vps`,
а не через веб-консоль.

**Инвентаризация сервера** (пришли вывод агенту — он подберёт параметры):

```bash
bash 00-check.sh
```

---

## Фаза 1 — базовая настройка

```bash
HERMES_HOSTNAME=hermes HERMES_TZ=Europe/Moscow bash 10-base.sh
```

Подставь свой часовой пояс. Скрипт: обновление системы, базовые пакеты, hostname,
таймзона, swap 2G если RAM < 4GB.

Если в конце написано, что требуется перезагрузка — ребутни **сейчас**, пока ничего
не настроено (`reboot`), потом это будет дороже.

---

## Фаза 2 — безопасность

⚠ Отключает вход по паролю. Запускать **только** после подтверждённой Фазы 0 —
иначе потеряешь доступ к серверу. Скрипт сам откажется работать, если в
`authorized_keys` нет ключей.

```bash
bash 20-security.sh
```

**Проверка Фазы 2 — НЕ закрывая текущую сессию**, открой новую и проверь:

```bash
ssh -o BatchMode=yes hermes-vps "echo OK"                                    # -> OK
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password root@216.57.111.124
# -> Permission denied БЕЗ запроса пароля
```

Если что-то пошло не так — консоль восстановления хостера, там
`rm /etc/ssh/sshd_config.d/99-hermes.conf && systemctl restart ssh` или `ufw disable`.

---

## Фаза 3 — установка Hermes

```bash
bash 30-hermes.sh
```

Ставит Hermes, определяет путь venv, доставляет Telegram-адаптер (extra `messaging`),
создаёт `.env` с chmod 600, гоняет `hermes doctor`.

---

## Фаза 4 — «мозг» (LLM-провайдер)

### Как выбрать за минуту

Ответь себе по порядку — первый подходящий вариант и бери:

1. **Ничего платного нет / не хочу возиться с ключами** → **Nous Portal**.
   Родной для Hermes, вход по ссылке, без API-ключей, есть бесплатные модели.
   Это дефолт — начинай с него.
2. **Есть подписка ChatGPT Plus/Pro** → **Codex**. Работает на квоте подписки,
   отдельно платить не надо. Но требует подготовки (см. ниже).
3. **Готов завести ключ ради выбора моделей** → **OpenRouter**. Много моделей
   с суффиксом `:free`, удобно набирать fallback-цепочку.

Их можно комбинировать: один primary + остальные в fallback.

---

**Вариант 1 — Nous Portal** (рекомендуемый старт):

```bash
hermes portal
```

Команда напечатает URL — открой его на своей машине, залогинься, подтверди.
Дальше мастер предложит выбрать модель и назначить Nous провайдером.

⚠ В пикере будет 300+ моделей, но **без списания кредитов работают только модели
с тегом `:free`** — выбирай строго их. Проверка авторизации: `hermes portal info`.

**Вариант 2 — OpenRouter** (ключ с openrouter.ai → Keys):

```bash
bash set-env.sh OPENROUTER_API_KEY
# посмотреть живой список бесплатных моделей:
curl -s https://openrouter.ai/api/v1/models | jq -r '.data[] | select(.pricing.prompt=="0") | .id' | head -20
hermes config set model.provider openrouter
hermes config set model.default <модель-из-списка-выше>
```

⚠ Не бери ID моделей из головы и из старых инструкций — каталоги меняются каждый
месяц, смотри живой список.

**Вариант 3 — Codex / ChatGPT Plus:**

⚠ **Сначала** включи device-авторизацию: chatgpt.com → Settings → Security →
device code authorization. Без этого шага логин с сервера будет отбит — это
первая причина «код не принимается».

```bash
npm i -g @openai/codex     # если npm нет: apt-get install -y nodejs npm
codex login --device-auth  # напечатает код и URL, открой URL на своей машине
hermes model               # выбери провайдера openai-codex и модель
```

⚠ Refresh-токены одноразовые: один аккаунт = один клиент. Не логинь тот же
аккаунт в Codex CLI на другой машине — сервер разлогинится.

---

### Fallback-цепочка (не пропускай)

Чтобы бот пережил исчерпание квоты primary-модели, добавь 1–3 бесплатных:

```bash
hermes fallback add
hermes fallback list
```

### Проверка Фазы 4

```bash
hermes -z 'Ответь ровно одним словом: PONG'
```

Ответ должен содержать PONG. Без этого дальше не иди — без мозга остальные фазы
не проверить.

⚠ Для диагностики **конкретного** провайдера этот смоук не годится: при отказе
primary Hermes молча уйдёт в fallback и вернёт OK. Проверяй провайдера прямым
HTTP-запросом (см. `references/providers.md` §Диагностика).

---

## Фаза 5 — Telegram-бот

1. @BotFather → `/newbot` → получи **token**
2. @userinfobot → узнай свой числовой **user id**

```bash
bash set-env.sh TELEGRAM_BOT_TOKEN TELEGRAM_ALLOWED_USERS
```

⚠ Вайтлист обязателен: без `TELEGRAM_ALLOWED_USERS` бот отвечает отказом всем,
включая владельца. Несколько id — через запятую.

Фикс граблей «бот молчит» (DoH-discovery запасных IP виснет на некоторых VPS) —
именно в `.env`, а не через `hermes config set`, адаптер читает это только как
переменную окружения:

```bash
grep -q '^HERMES_TELEGRAM_DISABLE_FALLBACK_IPS=' /root/.hermes/.env || \
  echo 'HERMES_TELEGRAM_DISABLE_FALLBACK_IPS=true' >> /root/.hermes/.env
```

Установка гейтвея как systemd-сервиса (под root нужен явный `--run-as-user`):

```bash
hermes gateway install --system --run-as-user root
systemctl status hermes-gateway
```

Проверка поллинга (в journalctl «успеха» не видно, только WARNING):
```bash
ss -tnp | grep "$(systemctl show -p MainPID --value hermes-gateway)"
```
Должны быть ESTABLISHED к api.telegram.org:443.
⚠ Не дёргай `getUpdates` вручную при живом гейтвее — украдёшь апдейты (ошибка 409).

**Проверка Фазы 5:** напиши боту `/status` в Telegram и получи ответ.

---

## Фазы 6–9

Голос (STT/TTS), веб-поиск, личность и кроны, финальная проверка — по скиллу
`skills/hermes-vps-setup/SKILL.md`. Присылай агенту вывод после Фазы 5, он
подготовит следующие шаги так же.

---

## Шпаргалка

```bash
systemctl status hermes-gateway      # состояние
systemctl restart hermes-gateway     # после ЛЮБОЙ правки .env или config.yaml
journalctl -u hermes-gateway -e      # логи (только WARNING+)
hermes status                        # общее состояние
hermes model                         # сменить модель
hermes backup                        # перед каждым hermes update
```
