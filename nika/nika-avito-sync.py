#!/usr/bin/env python3
"""Выгружает объявления студии из Авито и вкладывает их в SOUL.md Ники.

Зачем: без этого Ника не видит ни одного своего объявления и любая её фраза
про зарплату — догадка. Полного текста объявлений API на текущем тарифе не
отдаёт (мессенджер закрыт кодом 402), но заголовок, цену, адрес и ссылку —
отдаёт. Этого хватает, чтобы назвать реальную вилку и не выдумывать.

Блок вставляется между маркерами, всё остальное в SOUL.md не трогается.
Запускается из systemd-таймера; безопасен для повторного запуска.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

BEGIN = "<!-- AVITO:BEGIN -->"
END = "<!-- AVITO:END -->"
API = "https://api.avito.ru"
TIMEOUT = 30
MSK = timezone(timedelta(hours=3))


def fail(msg: str) -> "None":
    print("nika-avito-sync: %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def read_env(path: str) -> dict:
    """Разбор .env без внешних зависимостей: только строки ИМЯ=значение."""
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:]
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError as exc:
        fail("не читается %s: %s" % (path, exc))
    return out


def post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def money(value) -> str:
    if value in (None, "", 0):
        return "цена не указана"
    try:
        return "{:,}".format(int(value)).replace(",", " ") + " руб."
    except (TypeError, ValueError):
        return str(value)


# В архиве лежит и мебель, и телевизор — кандидату это неинтересно, а место
# в промпте занимает. Оставляем только то, по чему реально пишут люди.
RELEVANT = ("Вакансии", "Предложение услуг", "Резюме")


def is_relevant(item: dict) -> bool:
    return ((item.get("category") or {}).get("name") or "") in RELEVANT


def fetch_items(token: str, status: str) -> list:
    items, page = [], 1
    while page <= 10:
        url = "%s/core/v1/items?per_page=100&page=%d&status=%s" % (API, page, status)
        try:
            data = get_json(url, token)
        except Exception as exc:
            print("nika-avito-sync: %s страница %d: %s" % (status, page, exc), file=sys.stderr)
            break
        chunk = data.get("resources") or []
        items.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return items


def render(active: list, archived: list) -> str:
    now = datetime.now(MSK).strftime("%d.%m.%Y %H:%M")
    out = [BEGIN, "", "## Объявления студии на Авито", "",
           "Выгружено из личного кабинета %s МСК, обновляется само." % now,
           "Цифры здесь настоящие — на них можно ссылаться прямо.", ""]

    if active:
        out.append("**Сейчас размещены:**")
        out.append("")
        for it in active:
            kind = (it.get("category") or {}).get("name") or "объявление"
            out.append("- «%s» — %s, %s" % (it.get("title") or "без названия", kind, money(it.get("price"))))
            if it.get("address"):
                out.append("  адрес: %s" % it["address"])
            if it.get("url"):
                out.append("  %s" % it["url"])
        out.append("")
    else:
        out += ["**Сейчас не размещено ни одного объявления.** Если человек",
                "ссылается на объявление — значит, оно уже снято; уточни у него,",
                "что там было написано, и не подтверждай условий по памяти.", ""]

    if archived:
        out.append("**Сняты с публикации** (упоминать как действующие нельзя, "
                   "но по ним могут написать):")
        out.append("")
        for it in archived[:20]:
            out.append("- «%s» — %s" % (it.get("title") or "без названия", money(it.get("price"))))
        if len(archived) > 20:
            out.append("- …и ещё %d" % (len(archived) - 20))
        out.append("")

    out += ["**Как этим пользоваться.**",
            "",
            "1. Цена и адрес привязаны каждый к своему объявлению. Не переноси",
            "   их с одного на другое и не склеивай в один ответ: у обучения и",
            "   у вакансии это разные суммы и разные адреса.",
            "2. Сначала пойми, о каком объявлении речь. Если человек не назвал —",
            "   спроси, а не угадывай по самому похожему.",
            "3. Полного текста объявлений API не отдаёт: у тебя есть только",
            "   заголовок, цена, категория и адрес. Всё остальное — график,",
            "   условия обучения, соцпакет, требования — тебе неизвестно.",
            "   Про это честно говори, что уточнишь у руководителя.", "", END]
    return "\n".join(out)


def splice(soul: str, block: str) -> str:
    if BEGIN in soul and END in soul:
        head, _, rest = soul.partition(BEGIN)
        _, _, tail = rest.partition(END)
        return head.rstrip("\n") + "\n\n" + block + "\n" + tail.lstrip("\n")
    return soul.rstrip("\n") + "\n\n" + block + "\n"


def main() -> None:
    home = os.environ.get("HERMES_HOME", "/opt/hermes-nika-home")
    env = read_env(os.path.join(home, ".env"))
    for extra in ("/root/.hermes/.env",):          # запасной источник ключей Авито
        if not env.get("AVITO_CLIENT_ID") and os.path.exists(extra):
            env.update({k: v for k, v in read_env(extra).items()
                        if k.startswith("AVITO_") and k not in env})

    cid, secret = env.get("AVITO_CLIENT_ID"), env.get("AVITO_CLIENT_SECRET")
    if not cid or not secret:
        fail("AVITO_CLIENT_ID/AVITO_CLIENT_SECRET не найдены — нечего синхронизировать")

    try:
        token = post_form(API + "/token", {"grant_type": "client_credentials",
                                           "client_id": cid, "client_secret": secret}).get("access_token")
    except Exception as exc:
        fail("не получен токен Авито: %s" % exc)
    if not token:
        fail("Авито не вернул access_token")

    active = fetch_items(token, "active")
    archived = [it for it in fetch_items(token, "old") if is_relevant(it)]

    soul_path = os.path.join(home, "SOUL.md")
    try:
        soul = open(soul_path, encoding="utf-8").read()
    except OSError as exc:
        fail("не читается %s: %s" % (soul_path, exc))

    updated = splice(soul, render(active, archived))
    if updated == soul:
        print("nika-avito-sync: без изменений (%d активных, %d в архиве)" % (len(active), len(archived)))
        return

    tmp = soul_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(updated)
    os.chmod(tmp, 0o600)
    os.replace(tmp, soul_path)
    print("nika-avito-sync: SOUL.md обновлён — %d активных, %d в архиве" % (len(active), len(archived)))


if __name__ == "__main__":
    main()
