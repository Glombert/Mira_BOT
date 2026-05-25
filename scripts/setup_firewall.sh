#!/bin/bash
# scripts/setup_firewall.sh — идемпотентная настройка ufw + fail2ban + unattended-upgrades
# Запуск: sudo bash scripts/setup_firewall.sh

set -e

echo "=== Настройка UFW ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
ufw allow 80/tcp comment "HTTP"
ufw allow 443/tcp comment "HTTPS"
ufw --force enable
ufw status verbose

echo ""
echo "=== Установка fail2ban ==="
apt-get update -qq
apt-get install -y -qq fail2ban

# SSH jail
cat > /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled  = true
port     = ssh
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 5
bantime  = 3600
findtime = 600

[nginx-http-auth]
enabled  = true
port     = http,https
filter   = nginx-http-auth
logpath  = /var/log/nginx/error.log
maxretry = 10
bantime  = 3600
EOF

systemctl restart fail2ban
echo "fail2ban status:"
fail2ban-client status sshd 2>/dev/null || echo "(ожидание первого запуска)"

echo ""
echo "=== unattended-upgrades ==="
apt-get install -y -qq unattended-upgrades apt-listchanges

cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
EOF

cat > /etc/apt/apt.conf.d/50unattended-upgrades << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF

echo ""
echo "=== ГОТОВО ==="
echo "UFW: deny incoming, allow 22/80/443"
echo "fail2ban: sshd + nginx-http-auth jails активны"
echo "unattended-upgrades: security-обновления ежедневно"
