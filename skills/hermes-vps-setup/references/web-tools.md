# Веб-поиск и парсинг страниц

Hermes разделяет два бэкенда: **поиск** (`web.search_backend`) и **извлечение контента
страниц** (`web.extract_backend`). Базовая семинарная связка: Brave (поиск) +
Firecrawl (извлечение). Если у пользователя пока нет ключей — есть бесключевые
варианты, всё переключается одной командой в любой момент.

## Brave Search (поиск, основной)

1. Пользователь регистрируется на brave.com/search/api, тариф **Free** (2000 запросов/мес),
   берёт ключ.
2. В `/root/.hermes/.env`: `BRAVE_SEARCH_API_KEY=<ключ>`.
3. ```bash
   hermes config set web.search_backend brave-free
   systemctl restart hermes-gateway
   ```
   (`brave-free` — имя бэкенда free-tier Brave API; ключ при этом обязателен.)

Проверка: `hermes -z 'Найди в вебе последнюю LTS-версию Ubuntu и назови её'` — в ответе
видно использование поиска.

## DuckDuckGo / ddgs (поиск без ключа)

Запасной вариант, когда Brave-ключа нет: бэкенд `ddgs` ищет через DuckDuckGo, без
регистрации и API-ключей (лимиты мягкие, для старта достаточно).

```bash
/usr/local/lib/hermes-agent/venv/bin/pip install ddgs   # если пакета ещё нет
hermes config set web.search_backend ddgs
systemctl restart hermes-gateway
```

Когда появится Brave-ключ — просто впиши его в `.env` и верни
`web.search_backend brave-free`.

## Firecrawl (извлечение контента страниц)

Превращает URL в чистый markdown для агента (обходит JS-рендеринг, антибот и пр.).

1. Ключ: firecrawl.dev (есть free tier).
2. В `.env`: `FIRECRAWL_API_KEY=<ключ>`.
3. ```bash
   hermes config set web.extract_backend firecrawl
   systemctl restart hermes-gateway
   ```

Проверка: попроси бота «прочитай https://<конкретная-статья> и перескажи в двух
предложениях» — ответ по содержанию страницы.

Бесплатная альтернатива без ключа — Jina Reader (`https://r.jina.ai/<url>`): пока
Firecrawl-ключа нет, агент может читать страницы через `curl https://r.jina.ai/<url>`
в терминале; штатный extract-бэкенд настрой, когда ключ появится.
