#!/usr/bin/env bash
# Фаза 0/1 — инвентаризация сервера. Ничего не меняет, только смотрит.
set -uo pipefail
echo "=== OS ==="
. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"
uname -r
echo "=== RAM / SWAP ==="
free -m | awk '/Mem:/{print "RAM: "$2" MB"} /Swap:/{print "SWAP: "$2" MB"}'
echo "=== DISK ==="
df -h / | awk 'NR==2{print "root: "$2" всего, "$4" свободно"}'
echo "=== CPU ==="
nproc | awk '{print $1" ядер"}'
echo "=== HOSTNAME / TZ ==="
hostnamectl --static 2>/dev/null || hostname
timedatectl show -p Timezone --value 2>/dev/null
echo "=== SSH KEYS (сколько ключей уже авторизовано) ==="
if [ -s /root/.ssh/authorized_keys ]; then
  grep -c '^ssh-' /root/.ssh/authorized_keys
else
  echo "0  <-- ключей нет, Фазу 2 (отключение пароля) запускать НЕЛЬЗЯ"
fi
echo "=== УЖЕ УСТАНОВЛЕНО? ==="
command -v hermes >/dev/null && hermes --version 2>&1 | head -1 || echo "hermes: не установлен"
command -v ufw    >/dev/null && ufw status 2>/dev/null | head -1 || echo "ufw: не установлен"
systemctl is-active fail2ban 2>/dev/null | sed 's/^/fail2ban: /'
echo "=== ВНЕШНИЙ ДОСТУП ==="
curl -s -m 10 -o /dev/null -w "api.telegram.org: %{http_code}\n" https://api.telegram.org/ || echo "api.telegram.org: НЕДОСТУПЕН"
