# NIT (NESMA) Production Server

No passwords in this file - they live only in `/var/www/nesma/app/.env` on the server and in your password manager.

## Overview

| Item | Value |
|------|-------|
| Admin panel | https://nit-admin.zakhf.com/ |
| Website API | https://nit-admin.zakhf.com/api/ |
| VPS | Hostinger, 88.222.214.123 (shared with other projects - untouched) |
| Linux user | `nesma` (no login shell password; SSH key only) |
| Repository | https://github.com/jaseemrahman/NESMA-BACKEND (branch `main`) |

## Layout

```
/var/www/nesma/
├── app/        git checkout of the repo (+ .env, chmod 600)
├── venv/       Python virtualenv
├── static/     collectstatic output (served by Nginx, cached 1 year)
├── media/      uploads: blog images (public), careers/ CVs (blocked in Nginx, admin-only)
└── cache/      shared Django cache (if Redis is not used)
```

## Services

| What | Where | Commands |
|------|-------|----------|
| Gunicorn | `/etc/systemd/system/nesma.service` (socket `/run/nesma/gunicorn.sock`) | `systemctl restart nesma` · `systemctl status nesma` · `journalctl -u nesma -n 100 --no-pager` |
| Nginx site | `/etc/nginx/sites-available/nesma` | `nginx -t && systemctl reload nginx` · logs `/var/log/nginx/nesma.*.log` |
| SSL | Let's Encrypt via certbot (auto-renew timer) | `certbot certificates` · `certbot renew --dry-run` |
| PostgreSQL | database `nesma_db`, user `nesma_user` (localhost only) | `sudo -u postgres psql nesma_db` |
| Deploy rights | `/etc/sudoers.d/nesma` - `nesma` may only restart its own service | |

Source copies of these configs are in this `deploy/` folder.

## CI/CD (GitHub Actions - `.github/workflows/ci-cd.yml`)

1. Every push / PR to `main`: Django checks + full test suite against PostgreSQL 16.
2. Push to `main` and tests green: SSH to the server as `nesma` and run `deploy/deploy.sh`:
   pull → pip install → `check --deploy` → migrate → collectstatic → restart → health check.
   If the service doesn't come back healthy, the previous commit is restored automatically
   (database migrations are not reversed - write backward-compatible migrations).

Repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|-------|
| `HOST` | `88.222.214.123` |
| `USERNAME` | `nesma` |
| `SSH_KEY` | private key whose public key is in `/home/nesma/.ssh/authorized_keys` |

## Manual deploy / maintenance (as root)

```bash
sudo -u nesma bash /var/www/nesma/app/deploy/deploy.sh      # same as CI
sudo -u nesma /var/www/nesma/venv/bin/python /var/www/nesma/app/manage.py createsuperuser
sudo -u nesma /var/www/nesma/venv/bin/python /var/www/nesma/app/manage.py seed_demo_data --blogs-only
```

## Backups

`/etc/cron.daily/nesma-backup` keeps 14 days of database dumps + media in `/var/backups/nesma/`.
Restore a dump: `gunzip -c FILE.sql.gz | sudo -u postgres psql nesma_db`.
