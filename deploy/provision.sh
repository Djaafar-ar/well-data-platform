#!/bin/bash
# Prepare a fresh Ubuntu 24.04 (or newer) server for the Well Data Platform. Run once, as root:
#
#   curl -fsSL https://raw.githubusercontent.com/Djaafar-ar/well-data-platform/main/deploy/provision.sh -o provision.sh
#   sudo bash provision.sh
#
# Safe to run again (every step checks before changing anything). What it does:
#   1. security updates now, and automatic security updates from now on
#   2. firewall: deny everything incoming except SSH, HTTP, HTTPS
#   3. fail2ban: block IPs that keep failing SSH logins
#   4. Docker Engine + Compose plugin from Docker's official repository
#   5. a 2 GB swap file (small cloud VMs run out of memory without one)
#   6. a 'deploy' user that runs the platform (in the docker group, no password login)
#   7. SSH hardening: no root login, no passwords -- ONLY if 'deploy' already has an SSH key,
#      so you cannot lock yourself out
#   8. the project in /opt/well-data-platform and the backup jobs in cron
set -euo pipefail
 
REPO_URL="${REPO_URL:-https://github.com/Djaafar-ar/well-data-platform.git}"
APP_DIR="/opt/well-data-platform"
DEPLOY_USER="deploy"
 
log() { printf '\n==> %s\n' "$*"; }
 
if [ "$(id -u)" -ne 0 ]; then
    echo "run as root: sudo bash $0" >&2
    exit 1
fi
. /etc/os-release
if [ "${ID:-}" != "ubuntu" ]; then
    echo "this script is written for Ubuntu (found: ${PRETTY_NAME:-unknown})" >&2
    exit 1
fi
 
export DEBIAN_FRONTEND=noninteractive
 
log "1/8 updates and automatic security updates"
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git ufw fail2ban unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades
 
log "2/8 firewall (ufw): allow SSH, HTTP, HTTPS only"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
# Note: ports PUBLISHED by Docker bypass ufw. That is why the production compose file publishes
# nothing except Caddy's 80/443: the database is never published at all.
 
log "3/8 fail2ban for SSH"
cat > /etc/fail2ban/jail.d/sshd.local <<'JAIL'
[sshd]
enabled  = true
maxretry = 5
findtime = 10m
bantime  = 1h
JAIL
systemctl enable --now fail2ban
systemctl restart fail2ban
 
log "4/8 Docker Engine"
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    codename="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
    # A brand-new Ubuntu release can appear before Docker publishes packages for it: fall back to 24.04 (noble)
    if ! curl -fsI "https://download.docker.com/linux/ubuntu/dists/$codename/Release" >/dev/null; then
        echo "Docker has no packages for '$codename' yet: using the Ubuntu 24.04 (noble) ones"
        codename="noble"
    fi
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $codename stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -q
    apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
 
log "5/8 swap file"
if ! swapon --show | grep -q '/swapfile'; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
 
log "6/8 deploy user"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
# Reuse the key you logged in with: the user who ran sudo (e.g. a VirtualBox install), or the
# default user of cloud images
for src in "/home/${SUDO_USER:-none}/.ssh/authorized_keys" /root/.ssh/authorized_keys \
           /home/ubuntu/.ssh/authorized_keys /home/azureuser/.ssh/authorized_keys; do
    if [ -s "$src" ] && [ ! -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]; then
        cp "$src" "/home/$DEPLOY_USER/.ssh/authorized_keys"
    fi
done
[ -f "/home/$DEPLOY_USER/.ssh/authorized_keys" ] && chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys" \
    && chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
 
log "7/8 SSH hardening"
if [ -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]; then
    cat > /etc/ssh/sshd_config.d/90-hardening.conf <<'SSHD'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
SSHD
    sshd -t && systemctl reload ssh
    echo "SSH: key-only login enabled. Log in from now on as: ssh $DEPLOY_USER@<server-ip>"
else
    echo "SKIPPED: '$DEPLOY_USER' has no SSH key yet, so password login stays on (to avoid a lock-out)."
    echo "Add your public key to /home/$DEPLOY_USER/.ssh/authorized_keys and run this script again."
fi
 
log "8/8 project and scheduled jobs"
if [ ! -d "$APP_DIR/.git" ]; then
    git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /var/backups/wells
cat > /etc/cron.d/well-data-platform <<CRON
# Nightly database backup at 02:30, weekly restore test on Sunday at 03:30 (server time)
30 2 * * * $DEPLOY_USER cd $APP_DIR && bash deploy/backup.sh >> /var/backups/wells/backup.log 2>&1
30 3 * * 0 $DEPLOY_USER cd $APP_DIR && bash deploy/restore-test.sh >> /var/backups/wells/restore-test.log 2>&1
CRON
chmod 644 /etc/cron.d/well-data-platform
 
cat <<NEXT
 
Server ready. Next steps (as $DEPLOY_USER):
  sudo -iu $DEPLOY_USER
  cd $APP_DIR
  cp .env.example .env && nano .env      # strong passwords + DOMAIN (or use the tunnel option)
  docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile https up -d --build
 
See docs/DEPLOY.md for the full guide.
NEXT
 