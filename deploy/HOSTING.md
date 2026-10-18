# NIT Admin & API - Hosting Guide

Nesma Infrastructure & Technology · Production server runbook · No passwords in this document

## 1. Overview

| Item | Value |
|------|-------|
| Admin panel | `https://nit-admin.zakhf.com/` |
| Website API | `https://nit-admin.zakhf.com/api/` |
| Frontend (Next.js) | `https://nit-hazel.vercel.app` |
| Server | Hostinger VPS, `88.222.214.123`, Ubuntu 24.04 LTS (2 CPU, 8 GB RAM) |
| Stack | Django 4.2 · Python 3.12 · PostgreSQL 16 · Redis · Gunicorn · Nginx · Let's Encrypt |
| Linux user | `nesma` (SSH key only, no password) |
| Repository | `https://github.com/jaseemrahman/NESMA-BACKEND` (branch `main`) |
| Deploys | Automatic on every push to `main` (GitHub Actions), after tests pass |

The server also hosts other projects (BlueDot, NKE, Zuarak, Eclat, Dojo). NIT is fully isolated: own Linux user,
folder, database, Redis database, service and Nginx site. Nothing of the other projects was changed.

## 2. Server access

| Purpose | Command / location |
|---------|--------------------|
| Administration (root) | `ssh root@88.222.214.123` (SSH key) |
| Run a command as the app user | `sudo -u nesma <command>` (from root) |
| CI deploy key | `~/.ssh/nesma_deploy` on the maintainer's Mac (GitHub secret `SSH_KEY`) |

Where the secrets are:

- Django `SECRET_KEY`, database password, SMTP password: only in `/var/www/nesma/app/.env` (mode 600, owner `nesma`).
- GitHub: repository secrets `HOST`, `USERNAME`, `SSH_KEY`.
- Never commit `.env`; it is in `.gitignore`.

The `nesma` user's SSH key is restricted with a forced command: it can only run the deploy script
(no shell, no port forwarding). To revoke CI access, delete its line in `/home/nesma/.ssh/authorized_keys`.

## 3. Folder structure (server)

```
/var/www/nesma/                      owner nesma, group www-data
├── app/                             git checkout of the repository (branch main)
│   ├── .env                         production settings + secrets (chmod 600)
│   ├── config/                      Django settings, urls, wsgi
│   ├── superadmin/                  admin panel app (models, views, PDF export, migrations)
│   ├── website/                     public REST API app
│   ├── templates/                   admin + email templates
│   ├── static/                      static source files (collected into ../static)
│   ├── deploy/                      deploy.sh, nesma.service, nginx + sudoers templates, this guide
│   └── manage.py
├── venv/                            Python virtual environment
├── static/                          collectstatic output - served by Nginx (cached 1 year)
├── media/                           uploads: blogs/ public, careers/ CVs admin-only
└── cache/                           spare (cache uses Redis)
```

Other files created for NIT (and nothing else):

| Path | What |
|------|------|
| `/etc/systemd/system/nesma.service` | Gunicorn service |
| `/run/nesma/gunicorn.sock` | Unix socket between Nginx and Gunicorn (no TCP port) |
| `/etc/nginx/sites-available/nesma` (+ link in `sites-enabled/`) | Nginx site incl. SSL (certbot) |
| `/etc/letsencrypt/live/nit-admin.zakhf.com/` | SSL certificate |
| `/etc/sudoers.d/nesma` | `nesma` may only restart / check its own service |
| `/etc/cron.daily/nesma-backup` | daily backup job |
| `/var/backups/nesma/` | backups (14 days) |
| `/home/nesma/.ssh/authorized_keys` | restricted CI deploy key |
| PostgreSQL `nesma_db` / role `nesma_user` | database |
| Redis database `7`, key prefix `nesma:` | cache (db 2 belongs to another project) |

## 4. Application service (Gunicorn)

| Task | Command (as root) |
|------|-------------------|
| Status | `systemctl status nesma` |
| Restart (after .env change) | `systemctl restart nesma` |
| Live logs | `journalctl -u nesma -f` |
| Last 100 log lines | `journalctl -u nesma -n 100 --no-pager` |
| Enable at boot | `systemctl enable nesma` (already enabled) |

Gunicorn runs 3 workers x 2 threads, 60 s timeout, workers recycled every ~1000 requests.

## 5. Nginx & SSL

| Task | Command (as root) |
|------|-------------------|
| Test config (always before reload) | `nginx -t` |
| Reload | `systemctl reload nginx` |
| Access / error logs | `/var/log/nginx/nesma.access.log` · `/var/log/nginx/nesma.error.log` |
| Certificate status | `certbot certificates --cert-name nit-admin.zakhf.com` |
| Test renewal | `certbot renew --dry-run --cert-name nit-admin.zakhf.com` |

The certificate renews automatically (certbot timer). HTTP redirects to HTTPS; HSTS is enabled.
Upload limit: 15 MB (`client_max_body_size`).

## 6. Database (PostgreSQL 16)

| Task | Command (as root) |
|------|-------------------|
| Open psql | `sudo -u postgres psql nesma_db` |
| Size | `sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('nesma_db'))"` |
| Manual dump | `sudo -u postgres pg_dump --no-owner nesma_db \| gzip > /root/nesma_$(date +%F).sql.gz` |
| Restore a dump | `gunzip -c FILE.sql.gz \| sudo -u postgres psql nesma_db` |

Only reachable on localhost. Connection string: `DATABASE_URL` in `.env`.

## 7. Django management commands

Run from root (the settings are read from `/var/www/nesma/app/.env`):

```bash
DJ="sudo -u nesma /var/www/nesma/venv/bin/python /var/www/nesma/app/manage.py"
$DJ createsuperuser                 # email is required - the admin signs in with email
$DJ changepassword USERNAME
$DJ migrate
$DJ collectstatic --noinput
$DJ check --deploy
$DJ seed_demo_data --blogs-only     # the 6 posts from the website's media page (skips existing)
$DJ shell
```

Clear only NIT's cache (Redis db 7): `redis-cli -n 7 FLUSHDB`

## 8. Environment variables (.env)

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django secret (generated on the server) |
| `DEBUG` | `False` in production |
| `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` | `nit-admin.zakhf.com` |
| `DATABASE_URL` | PostgreSQL connection |
| `CACHE_URL` / `CACHE_KEY_PREFIX` | Redis db 7 / `nesma` |
| `CORS_ALLOW_ALL_ORIGINS` | `True` = any website may call the API |
| `SITE_URL` / `MEDIA_DOMAIN` | used for full https image URLs and email links |
| `STATIC_ROOT` / `MEDIA_ROOT` | `/var/www/nesma/static` / `/var/www/nesma/media` |
| `EMAIL_*` | SMTP for enquiry / career notifications |
| `ADMIN_NOTIFICATION_EMAIL` | receives enquiries and applications |
| `SUBMISSION_THROTTLE_RATE` | form limit per IP (default `10/hour`) |
| `CV_MAX_SIZE_MB` / `PDF_EXPORT_MAX_ROWS` | upload and export limits |
| `SECURE_SSL_REDIRECT` / `SECURE_HSTS_SECONDS` | HTTPS enforcement |

After editing `.env`: `systemctl restart nesma`.

## 9. CI/CD - automatic deploys

Workflow: `.github/workflows/ci-cd.yml`

1. Every push and pull request to `main`: Django checks, migration check and the full test suite on PostgreSQL 16.
2. Push to `main` with green tests: GitHub validates the deploy key, connects to the server as `nesma`
   (server host key pinned) and runs `deploy/deploy.sh`.
3. `deploy.sh`: pull `main` → `pip install` → `check --deploy` → `migrate` → `collectstatic` → restart →
   health check on `/api/career-options/`. If the service is not healthy, the previous commit is restored
   automatically (database migrations are not reversed - keep migrations backward compatible).

| GitHub secret | Value |
|---------------|-------|
| `HOST` | `88.222.214.123` |
| `USERNAME` | `nesma` |
| `SSH_KEY` | private key `~/.ssh/nesma_deploy` |

Manual deploy (same as CI): `sudo -u nesma bash /var/www/nesma/app/deploy/deploy.sh`

Roll back to an older commit by hand:

```bash
sudo -u nesma git -C /var/www/nesma/app reset --hard <commit>
systemctl restart nesma
```

## 10. Backups

`/etc/cron.daily/nesma-backup` runs every night and keeps 14 days in `/var/backups/nesma/`:
`nesma_db_YYYY-MM-DD.sql.gz` (database) and `nesma_media_YYYY-MM-DD.tar.gz` (uploads).
Run now: `/etc/cron.daily/nesma-backup`. Copy important backups off the server regularly.

## 11. Troubleshooting

| Symptom | Check |
|---------|-------|
| 502 Bad Gateway | `systemctl status nesma` and `journalctl -u nesma -n 100 --no-pager` |
| 500 error | `journalctl -u nesma -n 100 --no-pager` (Django tracebacks are logged there) |
| Old CSS/JS after deploy | run `collectstatic`; file names are hashed so browsers refresh automatically |
| Images 404 | file exists in `/var/www/nesma/media/`? Nginx `alias` path in `/etc/nginx/sites-available/nesma` |
| Emails not sent | `EMAIL_*` in `.env`; logs show `Background task ... failed` |
| GitHub deploy failed | Actions log → "Validate SSH key" / "Deploy over SSH" step; server: `journalctl -u ssh \| grep nesma` |
| Disk / memory | `df -h` · `free -h` · `du -sh /var/www/nesma/* /var/backups/nesma` |

## 12. Notes

- The repository's `deploy/nginx-nit-admin.zakhf.com.conf` is the pre-SSL template; the live file additionally
  contains the HTTPS block added by certbot.
- Other projects on this server were not modified. Observed during setup: the certificate for
  `bluedot.zuarak.com` had expired (30 Sep 2026) - unrelated to NIT.
- Rotate any passwords that were shared in chat or documents.
