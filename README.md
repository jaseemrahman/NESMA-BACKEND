# NESMA – Nesma Infrastructure & Technology (NIT) Backend

Django 4.2 backend for the NIT website (Next.js frontend: https://nit-hazel.vercel.app).

| App | Purpose |
|-----|---------|
| `superadmin` | Custom admin panel (Django templates) at the site root `/` – Blog categories, Blogs (EN/AR), Enquiries, Career applications |
| `website` | Public REST API at `/api/` – no token / no auth |

## Setup

Requires Python 3.9+ and PostgreSQL.

```bash
createdb nesma                # or create a role + database in psql
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set DATABASE_URL, SMTP, SECRET_KEY, MEDIA_DOMAIN
python manage.py migrate      # also seeds: News, Article, Announcement, Insights
python manage.py createsuperuser
python manage.py seed_demo_data   # optional: demo blogs (EN/AR), enquiries, career applications
python manage.py runserver        # admin panel: http://127.0.0.1:8000/
```

`seed_demo_data` is safe to run again (it skips existing records); `--reset` removes and re-creates the demo
records (demo enquiries/applications use `@example.com` emails).

Admin login uses **email + password** and requires `is_staff=True` (superusers have it).

Production: `DEBUG=False`, `python manage.py collectstatic`, run with
`gunicorn config.wsgi:application --workers 3`, serve `/media/` from Nginx.
With more than one worker set `CACHE_URL=redis://127.0.0.1:6379/1` so cache invalidation is shared.

## Performance

- Blog API responses are cached (`API_CACHE_TIMEOUT`, default 15 min) and **invalidated instantly**
  whenever a blog/category is saved or deleted (version-key cache, `website/cache.py`).
- List endpoints run 2 queries (count + page) using `select_related` + `only()`; DB indexes on the ordering/filter columns.
- Uploaded images are optimised losslessly (original resolution, format and quality kept).
- Notification emails are sent in a background thread after commit – form APIs respond immediately.
- GZip + WhiteNoise compressed static files, persistent DB connections.

## Frontend API

The API contract for the Next.js team is in [docs/NIT_API_Integration_Guide.pdf](docs/NIT_API_Integration_Guide.pdf).

Every endpoint accepts `?lang=ar` (or `Accept-Language: ar`); Arabic fields fall back to English when empty.
Images are returned as full `https://` URLs built from `MEDIA_DOMAIN`.

## Tests

```bash
python manage.py test        # needs a Postgres role allowed to create the test database
```

## Admin panel notes

- Blogs and categories require English **and** Arabic text; URL slugs are generated from the English title/name.
- Enquiries and career applications export to a branded PDF using the filters on screen (max `PDF_EXPORT_MAX_ROWS`, default 3000).
- Clicking a blog / career application row opens its detail page.

## Admin CSS bundle

The admin theme CSS (Bootstrap + theme + feather icons, ~1.8 MB) is purged and minified into
`static/superadmin/assets/css/admin.bundle.min.css` (~340 KB, ~35 KB with brotli). Sources live in `assets_src/admin-theme/`.
Hand-written styles go in `static/superadmin/assets/css/style-custom.css` (not purged).

If you use **new** Bootstrap/theme classes in templates, rebuild the bundle (needs Node 18+):

```bash
npm install && npm run build:css
```

## Production notes

- Static files use hashed names (`CompressedManifestStaticFilesStorage`): run `collectstatic` on every deploy;
  browsers cache them for a year and always get new files after a deploy. Brotli + gzip are served by WhiteNoise.
- Serve `/media/` (uploads) from Nginx. Blog images are kept at original quality; the admin list uses
  auto-generated 160px thumbnails (`blogs/thumbs/`).

