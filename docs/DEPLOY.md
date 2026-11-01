# Deploying to a Linux server

The same scripts work on any **Ubuntu 24.04** machine. Pick where it runs:

| Option | Cost | Needs | Public URL |
|---|---|---|---|
| **A. Cloud VM** (Azure, AWS, Oracle, Hetzner, DigitalOcean...) | Free tier or a few €/month | An account (usually a payment card for identity checks) | `https://<ip>.sslip.io` with a real HTTPS certificate |
| **B. Ubuntu VM on your own PC** (VirtualBox) | Free | Virtualization enabled in the BIOS, 4 GB RAM to spare | `https://<random>.trycloudflare.com` through an outbound tunnel; no open ports |

Both teach the same skills: Linux administration, SSH keys, firewall, Docker in production,
HTTPS, backups and restores. Option B also shows a pattern used in industry for sites with no public
IP (offshore installations, plant networks): only outbound connections, nothing listening on the internet.

---

## Option A: cloud VM

### 1. Create the VM
- Image: **Ubuntu Server 24.04 LTS**, size: 1–2 vCPU and **2 GB RAM** minimum (e.g. Azure B1ms/B2s, AWS t3.small).
- Authentication: **SSH public key** (not a password). On Windows, create a key once in PowerShell:
  ```powershell
  ssh-keygen -t ed25519 -C "well-data-platform"
  Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub     # paste this into the cloud console
  ```
- Network rules (security group / NSG): allow inbound **22, 80, 443** only.

### 2. Prepare the server
```bash
ssh <default-user>@<server-ip>          # 'azureuser' on Azure, 'ubuntu' on AWS/Oracle
curl -fsSL https://raw.githubusercontent.com/Djaafar-ar/well-data-platform/main/deploy/provision.sh -o provision.sh
sudo bash provision.sh
```
It installs updates, the firewall, fail2ban, Docker, a swap file, the `deploy` user, SSH hardening,
the project in `/opt/well-data-platform` and the nightly backup jobs. Read the script before
running it: you should be able to explain every step.

### 3. Configure and start
```bash
ssh deploy@<server-ip>
cd /opt/well-data-platform
cp .env.example .env
nano .env
```
In `.env`:
- set **strong, different passwords** for every `*_PASSWORD` (generate them with `openssl rand -base64 24`);
- add `DOMAIN=<your-ip-with-dashes>.sslip.io` (for IP `20.30.40.50` → `20-30-40-50.sslip.io`;
  sslip.io is a free DNS name that points at your IP, so Let's Encrypt can issue a certificate);
- add `ACME_EMAIL=you@example.com` (Let's Encrypt expiry notices).

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile https up -d --build
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs -f caddy   # watch the certificate being issued
```
Open `https://<your-ip-with-dashes>.sslip.io`. Then load the data:
```bash
docker compose run --rm fetch north-sea     # Volve + 10 North Sea wells (~55 MB)
docker compose run --rm load-all
```
The `north-sea-all` set (118 wells, ~620 MB download) needs about **3.1 GB** of database space:
use a VM with at least 20 GB of disk for it.

### 4. Check the security yourself
From **your PC** (not the server):
```powershell
Test-NetConnection <server-ip> -Port 443    # TcpTestSucceeded : True
Test-NetConnection <server-ip> -Port 5432   # TcpTestSucceeded : False  <- the database is NOT reachable
Test-NetConnection <server-ip> -Port 3000   # TcpTestSucceeded : False  <- Grafana only through HTTPS
```
On the server: `sudo ufw status verbose`, `sudo fail2ban-client status sshd`.

---

## Option B: Ubuntu VM on your PC + Cloudflare tunnel

1. Install **VirtualBox**, download the **Ubuntu Server 24.04** ISO, create a VM
   (2 vCPU, 4 GB RAM, 25 GB disk). During installation tick **Install OpenSSH server**.
2. In VirtualBox → VM Settings → Network: **Bridged Adapter**, so the VM gets an address on your
   home network (e.g. `192.168.1.50`). From Windows: `ssh <your-user>@192.168.1.50`.
3. Run steps 2 and 3 of option A, but **without DOMAIN**, and start with the tunnel profile:
   ```bash
   docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile tunnel up -d --build
   docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs tunnel | grep trycloudflare
   ```
   The log shows a public `https://<random-words>.trycloudflare.com` address. Open it from your phone
   on mobile data: your Grafana, over HTTPS, while the VM accepts **no** inbound connection from the internet.

Limits to know (and to mention in an interview): a quick tunnel's address changes on every restart
and has no uptime guarantee. A permanent one needs a free Cloudflare account and a domain name
(`cloudflared tunnel create`).

---

## Backups

- `deploy/backup.sh` runs every night at 02:30 (cron, set up by `provision.sh`): compressed `pg_dump`,
  checked for readability, SHA-256 fingerprint, 7 days kept in `/var/backups/wells`.
- `deploy/restore-test.sh` runs every Sunday: restores the latest backup into a scratch database and
  compares row counts with the live one. **A backup that has never been restored is only a hope.**
- Off-site copy: install `rclone`, configure a remote (`rclone config`), then set
  `RCLONE_REMOTE=<remote>:<folder>` in the cron line or environment.
- Restore for real: `bash deploy/restore.sh /var/backups/wells/<file>.dump` (asks for confirmation,
  takes a safety backup first).

Run both by hand once after deploying:
```bash
bash deploy/backup.sh && bash deploy/restore-test.sh
```

## Automatic deployment from GitHub

See the "Automatic deployment" section of [RUNBOOK.md](RUNBOOK.md#automatic-deployment).
