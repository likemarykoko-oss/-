# Google Workspace для бота (gog) — опционально

`gog` — CLI для Gmail, Calendar, Drive, Contacts, Sheets, Docs, Tasks
(https://gogcli.sh). В Hermes он не входит — это отдельный бинарь, но после
установки агент пользуется им через terminal-тулсет: «проверь почту», «что у меня
в календаре завтра», «создай встречу», «найди файл на диске».

Настройка состоит из двух частей: приложение в Google Cloud (делает пользователь в
браузере под твою диктовку) и авторизация на сервере. Самое важное здесь — статус
**In production** у OAuth-приложения, иначе всё отвалится через неделю (см. ⚠ ниже).

## 1. Установка gog на сервер

Одиночный бинарь с GitHub releases:

```bash
ssh hermes-vps 'set -e
ARCH=$(dpkg --print-architecture)   # amd64 или arm64
VER=$(curl -s https://api.github.com/repos/openclaw/gogcli/releases/latest | jq -r .tag_name)
curl -fsSL -o /tmp/gog.tar.gz "https://github.com/openclaw/gogcli/releases/download/${VER}/gogcli_${VER#v}_linux_${ARCH}.tar.gz"
tar -xzf /tmp/gog.tar.gz -C /tmp && install -m 755 /tmp/gog /usr/local/bin/gog
gog --version'
```

Если имя ассета не совпало (формат может меняться) — посмотри список файлов релиза
через `curl -s .../releases/latest | jq -r '.assets[].name'` и подставь актуальное.

## 2. Приложение в Google Cloud (делает пользователь в браузере)

Проведи пользователя по шагам (console.cloud.google.com):

1. **Создать проект** (любое имя, например `hermes-bot`).
2. **Включить API** (APIs & Services → Library) — только те сервисы, что нужны
   пользователю: Gmail API, Google Calendar API, Google Drive API, People API
   (контакты), Google Sheets API, Google Docs API, Tasks API.
3. **OAuth consent screen** (Google Auth Platform):
   - User type: **External**; заполнить имя приложения и свой email.
   - Scopes на этом этапе добавлять не обязательно — gog запросит нужные сам.
   - В Test users можно добавить свой email (нужно, пока приложение в Testing).
   - ⚠ **Перевести приложение в Production**: Audience / Publishing status →
     **Publish app**. Это критично: в статусе **Testing** Google отзывает
     refresh-токены через ~7 дней — бот проработает неделю и «внезапно» потеряет
     доступ к почте и календарю. Verification (проверку Google) проходить НЕ нужно:
     приложение останется «unverified», для личного использования это нормально —
     при авторизации Google покажет предупреждение, пользователь нажимает
     «Advanced» → «Go to <app> (unsafe)». Это его собственное приложение, риска нет.
4. **Создать OAuth client** (APIs & Services → Credentials → Create Credentials →
   OAuth client ID): тип **Desktop app**. Скачать JSON (`client_secret_….json`).

## 3. Авторизация на сервере

1. Пользователь передаёт файл `client_secret.json` (не вставлять содержимое в чат —
   переслать файлом). Положи на сервер:
   ```bash
   scp client_secret.json hermes-vps:/root/client_secret.json
   ssh hermes-vps "chmod 600 /root/client_secret.json && gog auth credentials /root/client_secret.json"
   ```
2. Авторизуй аккаунт (интерактивно, `-t` обязателен):
   ```bash
   ssh -t hermes-vps "gog auth add <email@gmail.com> --services gmail,calendar,drive,contacts,sheets,docs"
   ```
   gog напечатает URL для авторизации. Сервер headless, поэтому: пользователь
   открывает URL на своей машине; если redirect ведёт на `localhost:<порт>` —
   пробрось порт второй сессией `ssh -L <порт>:127.0.0.1:<порт> hermes-vps` и
   тогда redirect в браузере пользователя долетит до сервера.
3. Проверка:
   ```bash
   ssh hermes-vps "gog auth list && gog calendar events primary --max 1 --json --no-input"
   ```

После авторизации `/root/client_secret.json` можно удалить — креды уже в хранилище gog.

## 4. Правила безопасности для агента

- Перед отправкой писем и созданием/изменением событий — подтверждение у пользователя.
  Если пользователю почта нужна только на чтение — можно жёстко заблокировать
  отправку runtime-флагом `--gmail-no-send` в вызовах gog или ограничить
  сервисы при `gog auth add` (не включать gmail).
- Никогда не выводить токены, содержимое client_secret.json и ключи в чат/логи.
- Если через время gog «внезапно» просит re-auth — почти наверняка приложение
  осталось в Testing (см. ⚠ выше): сначала перевести в Production, потом один раз
  `gog auth add` заново. Не лечить многократным удалением локальных токенов.
