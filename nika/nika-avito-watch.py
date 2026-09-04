#!/usr/bin/env python3
"""Сторож Авито: замечает то, что иначе замечают поздно.

Смотрит четыре вещи и пишет в Telegram, когда есть что сказать:

  1. Баланс кошелька Авито упал ниже порога — размещения остановятся.
  2. У активного объявления скоро истекает срок размещения.
  3. Объявление, которое было активным, пропало из активных.
  4. Кандидат написал в Авито, и ему до сих пор не ответили.

Текст переписки тариф не отдаёт (402), но метаданные чата — отдаёт: кто
написал последним, когда и по какому объявлению. Этого хватает, чтобы
сказать «вас ждут в чате, вот ссылка», а прочитает человек уже сам.

Отправка идёт через `hermes send` — без модели и без единого токена, то есть
бесплатно. Состояние хранится в файле, чтобы не повторять одно и то же.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

API = "https://api.avito.ru"
TIMEOUT = 30
MSK = timezone(timedelta(hours=3))

BALANCE_FLOOR = int(os.environ.get("NIKA_BALANCE_FLOOR", "200"))      # рублей
EXPIRY_DAYS = int(os.environ.get("NIKA_EXPIRY_DAYS", "3"))            # дней до снятия
MANAGER = os.environ.get("NIKA_MANAGER", "Управляющая")               # к кому обращаться в чате
MAX_LIST = int(os.environ.get("NIKA_MAX_LIST", "8"))                 # строк в одном сообщении
BALANCE_EVERY_MIN = int(os.environ.get("NIKA_BALANCE_EVERY_MIN", "60"))  # как часто трогать баланс
SEND_BIN = os.environ.get("NIKA_SEND_BIN", "/usr/local/bin/hermes-nika")
MESSENGER_URL = "https://www.avito.ru/profile/messenger"


def read_env(path: str) -> dict:
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
    except OSError:
        pass
    return out


def post_form(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def post_json(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Source", "hermes-nika")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def load_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(path: str, state: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def rub(value) -> str:
    try:
        return "{:,}".format(int(value)).replace(",", " ") + " руб."
    except (TypeError, ValueError):
        return str(value)


def ago(seconds: int) -> str:
    if seconds < 3600:
        return "%d мин назад" % max(1, seconds // 60)
    if seconds < 86400:
        return "%d ч назад" % (seconds // 3600)
    return "%d дн назад" % (seconds // 86400)


def send(target: str, subject: str, body: str) -> bool:
    """Отправка через hermes send: без модели, без расхода токенов."""
    try:
        res = subprocess.run([SEND_BIN, "send", "-t", target, "-s", subject, "-q", body],
                             capture_output=True, text=True, timeout=90)
    except Exception as exc:
        print("nika-avito-watch: не отправилось: %s" % exc, file=sys.stderr)
        return False
    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip()[:300]
        print("nika-avito-watch: hermes send вернул %d: %s" % (res.returncode, detail), file=sys.stderr)
        return False
    return True


def check_balance(token: str, user: str, state: dict, out: list) -> None:
    """У Авито два разных баланса, и путать их нельзя.

    /core/v1/accounts/{u}/balance/ — кошелёк для разовых платных услуг.
    У студии он пустой, и это нормально: она за них так не платит. Ноль здесь
    ни о чём не говорит и поводом для тревоги не является.

    POST /cpa/v3/balanceInfo — тот самый баланс Авито.Работы, который виден в
    личном кабинете и с которого списывается за продвижение вакансий. Именно
    он кончается, и именно из-за него объявления перестают показываться.
    Значение приходит в копейках. Эндпоинт быстро упирается в 429 — тогда
    просто молчим до следующего раза, а не пугаем человека.
    """
    now = int(datetime.now(timezone.utc).timestamp())
    checked_at = int(state.get("balance_checked_at") or 0)
    if now - checked_at < BALANCE_EVERY_MIN * 60:
        return                      # эндпоинт быстро отдаёт 429, не трогаем его лишний раз

    try:
        kopecks = post_json(API + "/cpa/v3/balanceInfo", token, {}).get("balance")
    except Exception as exc:
        print("nika-avito-watch: баланс Авито.Работы недоступен (%s) — пропускаю проверку"
              % exc, file=sys.stderr)
        return
    state["balance_checked_at"] = now
    if not isinstance(kopecks, (int, float)):
        print("nika-avito-watch: неожиданный ответ по балансу, пропускаю", file=sys.stderr)
        return

    rubles = kopecks / 100.0
    was_low = bool(state.get("balance_low"))
    is_low = rubles < BALANCE_FLOOR
    state["balance_low"] = is_low
    state["balance_value"] = rubles

    if is_low and not was_low:
        out.append("%s, баланс Авито.Работы упал до %s — это ниже порога %s\n"
                   "Когда он кончится, продвижение вакансий остановится и объявления "
                   "уйдут из показа.\n"
                   "Пополнить: https://www.avito.ru/profile/wallet"
                   % (MANAGER, rub(rubles), rub(BALANCE_FLOOR)))
    elif was_low and not is_low:
        out.append("%s, баланс Авито.Работы пополнен, сейчас %s. Всё в порядке."
                   % (MANAGER, rub(rubles)))


def check_items(token: str, user: str, state: dict, out: list) -> None:
    try:
        active = (get_json("%s/core/v1/items?per_page=100&status=active" % API, token)
                  .get("resources") or [])
    except Exception as exc:
        print("nika-avito-watch: объявления недоступны: %s" % exc, file=sys.stderr)
        return

    now = datetime.now(timezone.utc)
    seen_before = state.get("active_items") or {}
    seen_now = {}

    for item in active:
        iid = str(item.get("id"))
        title = item.get("title") or "без названия"
        seen_now[iid] = title
        try:
            info = get_json("%s/core/v1/accounts/%s/items/%s/" % (API, user, iid), token)
        except Exception:
            continue
        finish = info.get("finish_time")
        if not finish:
            continue
        try:
            ends = datetime.fromisoformat(finish).replace(tzinfo=MSK)
        except ValueError:
            continue
        days = (ends - now).total_seconds() / 86400
        key = "expiry_%s_%s" % (iid, ends.date().isoformat())
        if 0 <= days <= EXPIRY_DAYS and not state.get(key):
            state[key] = True
            out.append("%s, объявление «%s» снимется %s, осталось %d дн.\n"
                       "Если вакансия ещё нужна, продлите: %s"
                       % (MANAGER, title, ends.strftime("%d.%m в %H:%M"), int(days),
                          item.get("url") or "личный кабинет Авито"))

    for iid, title in seen_before.items():
        if iid not in seen_now:
            out.append("%s, объявление «%s» больше не активно: снято, закончилось "
                       "или отклонено.\nОтклики по нему приходить перестанут."
                       % (MANAGER, title))
    state["active_items"] = seen_now


def describe_author(chat: dict, author_id) -> str:
    """Имя автора, но только если человек не запретил обработку профиля."""
    for user in chat.get("users") or []:
        if user.get("id") == author_id:
            if user.get("parsing_allowed") and user.get("name"):
                return user["name"]
            return "кандидат"
    return "кандидат"


def check_new_leads(token: str, user: str, state: dict, out: list) -> None:
    """Только первичные отклики: чат, которого раньше не было.

    Намеренно НЕ следим за тем, ответили ли на сообщение в уже известном чате.
    Переписку ведут живые люди, текста её мы не видим, и напоминать «вам не
    ответили» по каждому чужому диалогу — значит спамить. Повод написать один:
    появился новый человек, которого ещё никто не видел.
    """
    try:
        chats = (get_json("%s/messenger/v2/accounts/%s/chats?limit=100" % (API, user), token)
                 .get("chats") or [])
    except Exception as exc:
        print("nika-avito-watch: чаты недоступны: %s" % exc, file=sys.stderr)
        return

    known = state.get("known_chats")
    first_run = known is None
    known = known or {}
    now = int(datetime.now(timezone.utc).timestamp())
    leads = []

    for chat in chats:
        cid = chat.get("id")
        if not cid:
            continue
        seen_before = cid in known
        known[cid] = 1
        if seen_before or first_run:
            continue

        last = chat.get("last_message") or {}
        if last.get("direction") != "in":
            continue                        # чат завели мы сами — это не отклик

        value = ((chat.get("context") or {}).get("value")) or {}
        leads.append("- %s, по объявлению «%s» (%s), %s\n  %s"
                     % (describe_author(chat, last.get("author_id")),
                        value.get("title") or "без названия",
                        value.get("price_string") or "цена не указана",
                        ago(now - int(last.get("created") or now)),
                        value.get("url") or MESSENGER_URL))

    state["known_chats"] = known

    if first_run:
        print("nika-avito-watch: запомнил %d существующих чатов, "
              "дальше сообщаю только про новые" % len(known))
        return
    if not leads:
        return

    shown = leads[:MAX_LIST]
    tail = len(leads) - len(shown)
    head = ("%s, у нас новый отклик на Авито:" % MANAGER if len(leads) == 1
            else "%s, у нас новые отклики на Авито — %d:" % (MANAGER, len(leads)))
    parts = [head, "\n".join(shown)]
    if tail > 0:
        parts.append("…и ещё %d." % tail)
    parts.append("Не забудьте обработать: %s" % MESSENGER_URL)
    out.append("\n\n".join(parts))


def resolve_target(home: str, env: dict) -> str:
    """Куда писать: общий чат, если он уже известен, иначе владелице в личку.

    Общий чат появляется сам, как только бота добавят в рабочую группу и там
    кто-нибудь напишет: Hermes записывает известные каналы в channel_directory.
    Поэтому специально ничего настраивать не нужно — переключится само.
    """
    explicit = os.environ.get("NIKA_ALERT_CHAT")
    if explicit:
        return explicit

    try:
        with open(os.path.join(home, "channel_directory.json"), encoding="utf-8") as fh:
            directory = json.load(fh)
        for entry in (directory.get("platforms") or {}).get("telegram") or []:
            if (entry.get("type") or "").lower() in ("group", "supergroup") and entry.get("id"):
                target = "telegram:" + str(entry["id"])
                thread = entry.get("thread_id")
                return target + ":" + str(thread) if thread else target
    except (OSError, ValueError, AttributeError):
        pass

    first = (env.get("TELEGRAM_ALLOWED_USERS") or "").split(",")[0].strip()
    if not first:
        print("nika-avito-watch: некому писать, задай NIKA_ALERT_CHAT", file=sys.stderr)
        raise SystemExit(1)
    return "telegram:" + first


def main() -> None:
    home = os.environ.get("HERMES_HOME", "/opt/hermes-nika-home")
    env = read_env(os.path.join(home, ".env"))
    if not env.get("AVITO_CLIENT_ID") and os.path.exists("/root/.hermes/.env"):
        env.update({k: v for k, v in read_env("/root/.hermes/.env").items()
                    if k.startswith("AVITO_") and k not in env})

    cid, secret = env.get("AVITO_CLIENT_ID"), env.get("AVITO_CLIENT_SECRET")
    user = env.get("AVITO_USER_ID")
    if not (cid and secret and user):
        print("nika-avito-watch: нет ключей AVITO_*, нечего сторожить", file=sys.stderr)
        raise SystemExit(1)

    target = resolve_target(home, env)

    try:
        token = post_form(API + "/token", {"grant_type": "client_credentials",
                                           "client_id": cid,
                                           "client_secret": secret}).get("access_token")
    except Exception as exc:
        print("nika-avito-watch: токен Авито не получен: %s" % exc, file=sys.stderr)
        raise SystemExit(1)

    state_path = os.path.join(home, "avito-watch-state.json")
    state = load_state(state_path)
    messages: list = []

    check_balance(token, user, state, messages)
    check_items(token, user, state, messages)
    check_new_leads(token, user, state, messages)

    if os.environ.get("NIKA_WATCH_DRY_RUN"):
        print("--- сухой прогон, отправки не будет, состояние не пишется ---")
        print("\n\n".join(messages) if messages else "(сказать нечего)")
        return

    sent = 0
    for body in messages:
        if send(target, "Авито", body):
            sent += 1
    save_state(state_path, state)
    print("nika-avito-watch: поводов %d, отправлено %d" % (len(messages), sent))


if __name__ == "__main__":
    main()
