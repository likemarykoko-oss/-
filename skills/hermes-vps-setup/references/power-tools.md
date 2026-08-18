# Продвинутые инструменты (опционально): антидетект-браузер, YouTube, NotebookLM

Три сильных, но необязательных апгрейда. Ставь по запросу пользователя — для базового
бота они не нужны, но резко расширяют, что агент умеет: парсить защищённые сайты,
скачивать с YouTube, работать с NotebookLM. Каждый ставится независимо.

---

## 1. CloakBrowser — стелс-браузер для парсинга

Антидетект-Chromium с патчами фингерпринта на уровне исходников: проходит бот-проверки
(Cloudflare, «докажи, что не робот»), где обычный headless-браузер и Firecrawl упираются
в блок. Drop-in замена Playwright; Hermes цепляется к нему по CDP.

```bash
ssh hermes-vps 'set -e
# ⚠ НЕ python3 -m venv: на чистом Ubuntu у системного python нет ensurepip →
# venv получается без pip (проверено вживую на Linode). Делай venv через uv:
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; }
export PATH="$HOME/.local/bin:$PATH"
uv venv /root/.venvs/cloakbrowser
uv pip install --python /root/.venvs/cloakbrowser/bin/python -U cloakbrowser
/root/.venvs/cloakbrowser/bin/cloakbrowser install     # качает стелс-Chromium (~v146, free)
/root/.venvs/cloakbrowser/bin/cloakbrowser info'        # Launch: ✓, playwright: ok
```

Free-бинарь запускается без ключа (1 одновременная сессия — для парсинга обычно хватает);
за бóльшим — `cloakbrowser login` / cloakbrowser.dev.

**Подключение к Hermes.** CloakBrowser — drop-in замена Playwright. Связать его с
браузерным тулсетом Hermes можно через CDP: подними стелс-Chromium как постоянный
CDP-сервер на loopback (порт выбираешь сам, например 9242) и укажи адрес Hermes:

```bash
ssh hermes-vps "hermes config set browser.cdp_url http://127.0.0.1:<порт> && systemctl restart hermes-gateway"
```

⚠ Значения по умолчанию у `browser.cdp_url` нет (пусто) — адрес задаёшь только ты.
⚠ **Не трогай `browser.engine`** ради этого: он принимает лишь `auto | lightpanda | chrome`,
значения `cdp` там нет — `config set` запишет мусор молча и сломает движок.

⚠ Установку бинаря я проверил вживую (качается и стартует: `Launch: ✓`, `playwright: ok`).
А вот запуск как постоянного CDP-сервиса и мост к Hermes зависят от версии CloakBrowser —
сверься с его актуальной докой (`cloakbrowser --help`, cloakbrowser.dev) и не выдумывай
флаги. Порт CDP держи строго на `127.0.0.1` — это полный доступ к браузеру, наружу нельзя.

---

## 2. yt-dlp — скачивание с YouTube (и не только)

Скачивает видео/аудио/субтитры с YouTube и сотен сайтов. Одна тонкость: YouTube всё
чаще требует «докажи, что не бот» (PO-token) — лечится POT-провайдером bgutil.

```bash
ssh hermes-vps 'set -e
# бинарь yt-dlp (обновляемый)
curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
chmod +x /usr/local/bin/yt-dlp
# ffmpeg нужен для склейки видео+аудио (ставится инсталлером Hermes; на всякий:)
command -v ffmpeg >/dev/null || apt-get install -y ffmpeg
yt-dlp --version'
```

**POT-провайдер (bgutil) — против «Sign in to confirm you're not a bot».** Две части
(рецепт проверен вживую на Linode): Docker-контейнер = POT-сервер, плагин-zip = клиент,
который учит yt-dlp ходить в этот сервер по HTTP.

```bash
ssh hermes-vps 'set -e
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
# 1) POT-сервер контейнером (loopback!)
docker ps -a --format "{{.Names}}" | grep -q "^bgutil-provider$" || \
  docker run -d --name bgutil-provider --restart unless-stopped \
    -p 127.0.0.1:4416:4416 brainicism/bgutil-ytdlp-pot-provider
# 2) плагин-клиент: официальный zip в каталог плагинов yt-dlp
#    (для standalone-бинаря yt-dlp именно zip, НЕ pip — бинарь pip-плагины не видит)
PLUGDIR=/root/.config/yt-dlp/plugins; mkdir -p "$PLUGDIR"
URL=$(curl -s https://api.github.com/repos/Brainicism/bgutil-ytdlp-pot-provider/releases/latest \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(next(a[\"browser_download_url\"] for a in d[\"assets\"] if a[\"name\"].endswith(\".zip\")))")
curl -fsSL "$URL" -o "$PLUGDIR/bgutil-pot.zip"'
```

⚠ Порт 4416 — только `127.0.0.1`. Провайдер — вспомогательный сервис, публичным быть
не должен.

**Проверка:** `yt-dlp -v --simulate "https://www.youtube.com/watch?v=<id>" 2>&1 | grep pot`
показывает `PO Token Providers: bgutil:http-... (external)` — значит плагин виден и
подключён к контейнеру. Ошибки «script-node/script-deno unavailable» игнорируй: это
альтернативные локальные варианты, нам нужен именно `http`. Агент качает через
terminal-тулсет: `yt-dlp -x --audio-format mp3 -o "/root/downloads/%(title)s.%(ext)s" "<url>"`.

---

## 3. NotebookLM CLI — работа с Google NotebookLM из терминала

CLI к NotebookLM: создавать блокноты, загружать источники, задавать вопросы по своим
материалам — всё из командной строки, значит и руками агента.

```bash
ssh hermes-vps 'set -e
# uv — быстрый установщик Python-тулов (если нет)
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv tool install notebooklm-py
~/.local/bin/notebooklm --version'   # проверено вживую: v0.7.3
```

⚠ `uv tool install` кладёт бинарь в `~/.local/bin`, которого может не быть в PATH
(uv об этом предупредит). Вызывай полным путём `~/.local/bin/notebooklm` либо один раз
`~/.local/bin/uv tool update-shell` и перелогинься.

**Авторизация — через браузер, аккуратно на headless-сервере.** `notebooklm login`
открывает браузер для входа в Google. На сервере без экрана варианты:
- Авторизоваться на своей машине (где есть браузер) и перенести сессию: файл
  `storage_state.json` (по умолчанию `~/.notebooklm/storage_state.json`) скопировать
  на сервер тем же путём (`scp`), права `chmod 600`.
- Либо прокинуть браузер по SSH X-forwarding/VNC — сложнее, обычно не нужно.

**Проверка:** `notebooklm list` показывает блокноты пользователя. Дальше агент:
`notebooklm ask "вопрос по загруженным материалам"`. Токены/сессия — секрет, в чат и
логи не выводить.

---

⚠ Общее правило для всех трёх: это мощные инструменты с доступом к браузеру/сети/чужим
аккаунтам. Ставь только по явной просьбе пользователя, сервисы (CloakBrowser CDP,
bgutil) держи на `127.0.0.1`, сессии/токены не логируй.
