#!/usr/bin/env bash
# Фаза 1 — базовая настройка сервера. Идемпотентно.
# Использование: HERMES_HOSTNAME=hermes HERMES_TZ=Europe/Moscow bash 10-base.sh
set -euo pipefail

HERMES_HOSTNAME="${HERMES_HOSTNAME:-hermes}"
HERMES_TZ="${HERMES_TZ:-Europe/Moscow}"

echo "==> Обновление системы и базовые пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y upgrade
apt-get -y install curl git jq ufw fail2ban unattended-upgrades ca-certificates

echo "==> Hostname: $HERMES_HOSTNAME"
hostnamectl set-hostname "$HERMES_HOSTNAME"

echo "==> Часовой пояс: $HERMES_TZ"
timedatectl set-timezone "$HERMES_TZ"

echo "==> Swap (создаём 2G, если RAM < 4GB и swap отсутствует)"
ram_mb=$(free -m | awk '/Mem:/{print $2}')
swap_mb=$(free -m | awk '/Swap:/{print $2}')
if [ "$ram_mb" -lt 4000 ] && [ "$swap_mb" -eq 0 ]; then
  if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "    swap 2G создан"
  else
    echo "    /swapfile уже есть, пропускаю"
  fi
else
  echo "    не требуется (RAM ${ram_mb}MB, swap ${swap_mb}MB)"
fi

echo
echo "==> ПРОВЕРКА ФАЗЫ 1"
free -m | awk '/Mem:/{print "RAM: "$2" MB"} /Swap:/{print "SWAP: "$2" MB"}'
hostnamectl --static
timedatectl show -p Timezone --value
if [ -f /var/run/reboot-required ]; then
  echo
  echo "!! ЯДРО ОБНОВИЛОСЬ — требуется перезагрузка."
  echo "!! Сейчас ничего ещё не настроено, ребутнуть дешевле всего именно сейчас: reboot"
fi
echo "ФАЗА 1 OK"
