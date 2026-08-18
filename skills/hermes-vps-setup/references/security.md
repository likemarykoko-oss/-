# Безопасность сервера — подробные шаги

Порядок фиксирован: сначала подтверждённый вход по ключу, потом отключение паролей,
потом фаервол. Каждый шаг проверяется до перехода к следующему — цена ошибки здесь
потеря доступа к серверу.

## 1. Харденинг SSH (отключение входа по паролю)

Предусловие: `ssh -o BatchMode=yes hermes-vps "echo OK"` уже работает.

Drop-in конфиг (не правь основной `/etc/ssh/sshd_config` — drop-in проще откатить):

```bash
ssh hermes-vps 'cat > /etc/ssh/sshd_config.d/99-hermes.conf <<EOF
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
MaxAuthTries 4
EOF
sshd -t && systemctl restart ssh'
```

`sshd -t` обязателен: если конфиг битый, restart положит sshd и ты потеряешь доступ.
`prohibit-password` — root может войти, но только по ключу.

**Проверка (не закрывая текущую сессию!):**
- Новое соединение по ключу: `ssh -o BatchMode=yes hermes-vps "echo OK"` → OK.
- Пароль действительно отключён:
  `ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password root@<IP>` →
  `Permission denied` **без** запроса пароля.

Если пользователь захочет отдельного sudo-юзера вместо root — это опционально и не
входит в базовый сценарий (Hermes ставится под root); не усложняй без запроса.

## 2. UFW (фаервол)

```bash
ssh hermes-vps "ufw default deny incoming && ufw default allow outgoing && ufw allow 22/tcp && ufw --force enable && ufw status verbose"
```

⚠ **`allow 22/tcp`, ни в коем случае не `ufw limit 22/tcp`.** Боевой инцидент: `limit`
(порог 6 соединений/30 сек с одного IP) начал REJECT'ить SSH-сессии легитимного
агента, который активно работал с сервером — выглядело как случайные таймауты и «флап»
SSH. Вход и так только по ключу, брутфорс отсекает fail2ban — rate-limit на 22 порту
не даёт ничего, кроме самострела.

Если позже открываешь новые порты (например, для веб-панели) — открывай точечно и
только то, что должно быть публичным. Всё внутреннее (локальные сервисы, прокси)
держи на 127.0.0.1 — тогда порты открывать не нужно. На будущее: если на сервере
появится Docker, помни — он обходит UFW (пишет свои iptables-правила), поэтому порты
контейнеров публикуй только на `127.0.0.1:...`, иначе сервис окажется публичным
несмотря на `deny incoming`.

**Проверка:** `ufw status verbose` → `Status: active`, `Default: deny (incoming),
allow (outgoing)`, в списке только 22/tcp ALLOW. Новая SSH-сессия открывается.

## 3. fail2ban

```bash
ssh hermes-vps 'cat > /etc/fail2ban/jail.local <<EOF
[sshd]
enabled = true
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
systemctl enable --now fail2ban && systemctl restart fail2ban'
```

`backend = systemd` важен: на минимальных образах Ubuntu 24.04 может не быть
rsyslog/auth.log, и дефолтный backend молча не найдёт логов.

**Проверка:** `fail2ban-client status sshd` → jail работает, счётчики видны.

## 4. Автоматические security-обновления

```bash
ssh hermes-vps 'dpkg-reconfigure -f noninteractive unattended-upgrades && systemctl enable --now unattended-upgrades'
```

**Проверка:** `cat /etc/apt/apt.conf.d/20auto-upgrades` содержит
`APT::Periodic::Unattended-Upgrade "1";`.

## 5. Правила безопасности самого Hermes-бота

Официальные рекомендации Nous для серверных установок:

- **Режим подтверждений не отключать** (`approvals.mode: manual` — дефолт): опасные
  команды требуют явного «да» от пользователя в чате. На сервере это не опция, а норма.
- **Никогда не включать `GATEWAY_ALLOW_ALL_USERS=true`** у бота с terminal-доступом.
  Доступ — только вайтлист `TELEGRAM_ALLOWED_USERS` или DM-pairing.
- Агент со временем **пишет себе скиллы** (исполняемые инструкции в `~/.hermes/skills/`) —
  предупреди пользователя периодически их просматривать.
- Параноидальный вариант для будущего: `terminal.backend: docker` — команды агента
  выполняются в контейнере-песочнице, а не на хосте. Требует установки Docker, для
  старта не обязателен; предложи, только если пользователь спросит про изоляцию.
- **Перед каждым `hermes update` — `hermes backup`**, и копию бэкапа держать НЕ на этом
  сервере (scp на свою машину): при смерти диска локальный бэкап умирает вместе с ним.

## Откат при потере доступа

Если после какого-то шага SSH перестал пускать: в панели хостера почти всегда есть
консоль (VNC / recovery). Через неё:
- `rm /etc/ssh/sshd_config.d/99-hermes.conf && systemctl restart ssh` — вернуть пароли;
- `ufw disable` — временно выключить фаервол;
- `fail2ban-client set sshd unbanip <IP>` — разбанить свой IP.
