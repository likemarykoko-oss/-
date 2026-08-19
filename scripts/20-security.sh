#!/usr/bin/env bash
# Фаза 2 — безопасность. ОПАСНО при неверном порядке: отключает вход по паролю.
# ЗАПУСКАТЬ ТОЛЬКО ПОСЛЕ того, как вход по ключу подтверждён с твоей машины:
#   ssh -o BatchMode=yes -i ~/.ssh/hermes_vps root@<IP> "echo OK"   -> должно вернуть OK
# Текущую SSH-сессию НЕ закрывай, пока не проверишь новую.
set -euo pipefail

STAMP="$(date +%Y%m%d)"

echo "==> ЗАЩИТА ОТ САМОСТРЕЛА: проверяю наличие авторизованных ключей"
if [ ! -s /root/.ssh/authorized_keys ] || ! grep -q '^ssh-\|^ecdsa-\|^sk-' /root/.ssh/authorized_keys; then
  echo "СТОП: в /root/.ssh/authorized_keys нет ни одного ключа."
  echo "Отключение пароля сейчас = полная потеря доступа к серверу."
  echo "Сначала выполни Фазу 0 (ssh-copy-id) и подтверди вход по ключу."
  exit 1
fi
echo "    ключей найдено: $(grep -c '^ssh-\|^ecdsa-\|^sk-' /root/.ssh/authorized_keys)"

echo
echo "==> 1/4 Харденинг sshd (drop-in, не трогаем основной конфиг)"
mkdir -p /etc/ssh/sshd_config.d
[ -f /etc/ssh/sshd_config.d/99-hermes.conf ] && \
  cp /etc/ssh/sshd_config.d/99-hermes.conf "/etc/ssh/sshd_config.d/99-hermes.conf.bak-ssh-$STAMP"
cat > /etc/ssh/sshd_config.d/99-hermes.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
MaxAuthTries 4
CONF
sshd -t
echo "    sshd -t OK, перезапускаю"
systemctl restart ssh 2>/dev/null || systemctl restart sshd

echo
echo "==> 2/4 UFW"
# allow, а НЕ limit: limit режет SSH-сессии при активной работе агента.
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw --force enable

echo
echo "==> 3/4 fail2ban"
[ -f /etc/fail2ban/jail.local ] && cp /etc/fail2ban/jail.local "/etc/fail2ban/jail.local.bak-f2b-$STAMP"
cat > /etc/fail2ban/jail.local <<'CONF'
[sshd]
enabled = true
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
CONF
systemctl enable --now fail2ban
systemctl restart fail2ban

echo
echo "==> 4/4 Автоматические security-обновления"
dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now unattended-upgrades

echo
echo "==> ПРОВЕРКА ФАЗЫ 2"
ufw status verbose | head -6
echo "---"
sleep 2
fail2ban-client status sshd 2>&1 | head -6
echo "---"
grep -h 'Unattended-Upgrade' /etc/apt/apt.conf.d/20auto-upgrades 2>/dev/null || echo "20auto-upgrades: не найден"
echo
echo "ФАЗА 2 применена. ТЕПЕРЬ, НЕ ЗАКРЫВАЯ ЭТУ СЕССИЮ, проверь с своей машины:"
echo "  ssh -o BatchMode=yes -i ~/.ssh/hermes_vps root@<IP> 'echo OK'      # -> OK"
echo "  ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password root@<IP>"
echo "     # -> Permission denied БЕЗ запроса пароля"
