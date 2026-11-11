# Local Docker stack

This is local production-like infrastructure, **not a public production deployment**.
Docker Desktop must be running Linux containers; Compose must support health and
`service_completed_successfully` dependencies. Run commands at the repository root.

## Architecture

Browser → nginx on http://127.0.0.1:5173 → React production build or Django/Gunicorn
→ PostgreSQL 18 at internal host `postgres:5432`. PostgreSQL retains its existing
`postgres_data` volume and loopback `127.0.0.1:5432` publishing. Backend debugging,
admin and the existing Google callback remain at http://127.0.0.1:8000.
Only loopback ports are published. Native Vite/runserver must be stopped while
Docker occupies 5173/8000. Public deployment should not expose Gunicorn directly.

Backend uses Python 3.13 slim, Gunicorn 26.2.0 (two workers, non-root UID 10001),
and WhiteNoise 6.12.0 immediately after SecurityMiddleware. The image build alone
runs `collectstatic`; `/app/staticfiles` is part of that image. No shared static
initialization volume is needed. Native runserver retains its normal static handling.
Gunicorn is excluded from Windows dependency installation by a platform marker.
Its optional control socket is disabled; ordinary process/container management
does not require a writable home directory or management socket.
Frontend builds with Node 24 / `npm ci` and runs in nginx 1.28 Alpine without Node.
The existing lockfile and bundled `public/maps/standard.svg` are included.
Four imports in `src/App.jsx` now match the existing lowercase page filenames;
Windows accepted their previous capitalization, but Linux image builds did not.

nginx serves SPA routes with index fallback, proxies `/api/`, `/admin/`, `/static/`
without stripping prefixes, and serves `/media/` from a read-only volume mount.
It forwards Host (including port), X-Real-IP, X-Forwarded-For and X-Forwarded-Proto.
Neither Django proxy trust nor DRF NUM_PROXIES changes. Backend recreation is
handled by nginx's Docker DNS resolver. API errors never fall back to index.html.
Proxy access logs are disabled and error logging is critical-only to avoid OAuth
query/referrer disclosure. Gunicorn access logging remains disabled. Django's
existing OAuth log filtering remains active. No new CSP is imposed.

## Environment and secrets

Compose automatically reads ignored root `.env`; Django outside Docker does not.
Keep the existing POSTGRES_* values: changing the file does not change credentials
inside an initialized database. Never overwrite an existing `.env` with the example.
For a new checkout only: copy `.env.example`, replace both `change-me` placeholders.
Generate a local signing key without printing it (from root, using the native venv):

```powershell
backend/venv/Scripts/python.exe -c "from pathlib import Path; import secrets; from dotenv import dotenv_values; p=Path('.env'); assert not dotenv_values(p).get('DJANGO_SECRET_KEY'), 'Key already configured; edit deliberately'; f=p.open('a', encoding='utf-8'); f.write('\nDJANGO_SECRET_KEY='+secrets.token_hex(48)+'\n'); f.close()"
```

If starting from the example, remove the placeholder signing-key line first.
Use a strong database password on first initialization. Secrets enter runtime
environment only, never Docker build args, image layers or VITE_* values. Narrow
backend/frontend build contexts exclude .env variants, SQLite, venv/node_modules,
Git history, local media, logs and caches. Do not share resolved Compose output
or Docker inspect environment output. Use `config --quiet` instead.

Local HTTP uses `DJANGO_DEBUG=true` with console email. This is intentional;
production DEBUG=false validation and HTTPS requirements remain enforced.
Email settings can be supplied using the documented names in `.env.example`, but
no real SMTP is needed or configured. Console logs can contain private email text;
do not publish logs. Same-origin `/api/` is fixed at frontend image build time.

Google is optional. Manually add `GOOGLE_OAUTH_CLIENT_ID`,
`GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` to ignored root `.env`.
Keep callback `http://127.0.0.1:8000/api/users/oauth/google/callback/` and frontend
`http://127.0.0.1:5173`. Use 127.0.0.1 consistently; cookies are not port-scoped.
No secrets are discovered/copied from IDE or backend env files. No Google Cloud
configuration changes or GitHub setup are included. See [OAuth](backend/OAUTH.md).

## Start, initialization and persistence

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose ps -a migrate
docker compose logs --tail 100 migrate
```

Foreground `docker compose up --build` is also supported. PostgreSQL must become
healthy, then the one-shot `migrate` service runs `docker_init.py` using the same
backend image. It runs migrations once, then seeds only if **all four map tables
are empty**, inside a transaction. Existing maps are left untouched. `seed_map`
produces the same reference topology but deletes/recreates adjacency rows and
updates reference fields; it is not safe to silently run on every existing DB.
A partially populated map is preserved, not automatically repaired: inspect it
before deliberately running `docker compose exec backend python manage.py seed_map`.
No seed logic is duplicated. Do not run multiple initialization jobs concurrently.
`migrate` showing **Exited (0)** is normal, not a failed service.

Backend then starts Gunicorn; its healthcheck fetches admin login without
credentials. This proves HTTP availability, not database readiness by itself.
PostgreSQL has its own healthcheck; verify an actual Django DB connection below.
Frontend starts after backend health and checks its local HTTP entry.

`media_data` mounts at backend `/app/media` and nginx `/srv/media` read-only.
The backend image initializes that directory for UID 10001. Uploaded media and
PostgreSQL persist when containers are recreated. Existing native media is not
imported automatically. Media URLs are public; private upload serving would need
a separate authorization design. SQLite stays untouched and is never mounted.

```powershell
docker compose logs -f backend
docker compose logs -f frontend
docker compose stop
docker compose start
docker compose down
docker compose up -d --build
docker compose build backend frontend
docker compose up -d backend frontend
```

`stop`/`start` pause/resume existing containers; `start` does not build updated code.
`down` removes containers/network but **keeps volumes**. After code changes use
build/up so initialization uses the updated image. **DATA-DELETING: `docker compose
down -v` destroys database/media volumes. Do not run it to update or fix the stack.**

## Checks and tests

```powershell
docker compose exec backend python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print(connection.vendor); print(connection.settings_dict['HOST'])"
docker compose exec backend python manage.py showmigrations
docker compose exec backend python manage.py makemigrations --check
docker compose exec backend python manage.py check
docker compose exec backend python manage.py test --noinput
docker compose exec backend python manage.py test config.test_postgres_concurrency --noinput
docker compose exec backend python manage.py test apps.games.readiness_tests --noinput
docker compose exec backend python manage.py test apps.orders.tests.test_postgres_locks --noinput
```

Connection must print `postgresql`, `postgres`. Tests create/drop a separate normal
Django test database; run suites sequentially. PostgreSQL concurrency must not skip.
The local image-created DB superuser can create test DBs; this is not the final
production privilege design. Native frontend validation, from `frontend`:

```powershell
node --test tests/*.test.mjs
npm run build
npm run lint
```

Run `git diff --check` at root. Optional admin creation is interactive:
`docker compose exec backend python manage.py createsuperuser`.
Existing PostgreSQL accounts remain available; no default admin is created.

## Manual browser checklist

1. Open http://127.0.0.1:5173, register or log in; verify Home loads.
2. Create a game; use a second account/tab to join; start the game.
3. Verify the map, submit HOLD/MOVE, and check readiness and chat.
4. Log out/in and refresh `/login`, `/register`, a game route and `/oauth/callback`;
   frontend routes should load the SPA, including callback error handling without a ticket.
5. Visit `/admin/`; verify login HTML and admin CSS.
6. Optionally test configured Google login/linking as described in OAUTH.md.
   Providers endpoint `/api/users/oauth/providers/` reports enabled configuration.
   Real Google login must be performed manually, not by automated tests.

## Native workflow and limitations

Stop Docker backend/frontend before running native servers:
`docker compose stop frontend backend`. Keep `docker compose up -d postgres`,
configure native Django with matching credentials and `POSTGRES_HOST=127.0.0.1`,
install backend requirements, then `python manage.py runserver 127.0.0.1:8000`.
Run `npm run dev -- --host 127.0.0.1` in frontend. The DEBUG-only SQLite fallback
still works when all POSTGRES_* variables are absent. See [PostgreSQL](backend/POSTGRESQL.md).

There is **no automatic deadline scheduler in this stack**. Existing
`process_deadlines`, `process_game_tasks`, and `process_notifications` are one-shot
commands. Explicitly run `docker compose exec backend python manage.py process_deadlines`
to process expired phases/reminders; it mutates game state. Deployment must schedule
one recurring flow, e.g. process_deadlines every minute. No Celery/Redis or ad-hoc loop
was introduced. Readiness/manual resolution continue to use existing application logic.

Next task: design and validate the actual HTTPS deployment: domain/TLS edge,
DEBUG=false, secret store, DB runtime/migration privileges, backups with tested
restore, production OAuth callbacks, SMTP, recurring deadline scheduler, monitoring,
shared/edge rate limiting, frontend CSP, and production logging. None are supplied
by this loopback-only HTTP stack.

Implementation references: [Gunicorn package](https://pypi.org/project/gunicorn/)
and [WhiteNoise Django integration](https://whitenoise.readthedocs.io/en/stable/django.html).

## Docker v2 validation record — 2026-11-09

Before editing, the working tree already contained extensive modified/untracked
gameplay, OAuth, security, PostgreSQL preparation and frontend work, including a
modified tracked SQLite file. The existing PostgreSQL 18 container was healthy.
Those unrelated changes were preserved; no reset, SQLite import or volume deletion
was performed. PostgreSQL v1 live results supplied by the user are recorded in
POSTGRESQL.md, separate from this task's container validation.

Source files added/updated for v2:

- Root: `compose.yaml`, `.env.example`, `DOCKER.md`.
- Backend: `Dockerfile`, `.dockerignore`, `docker_init.py`, `requirements.txt`,
  `config/settings.py`, `POSTGRESQL.md`, `apps/games/readiness_tests.py`.
- Frontend: `Dockerfile`, `.dockerignore`, `nginx.conf`, `src/App.jsx`.

Ignored root `.env` received a random local signing key without exposing its value;
existing PostgreSQL values were preserved. No Google credentials were copied.
Native venv received WhiteNoise; Gunicorn remains Linux-only.

Build/test failures diagnosed and corrected during validation:

- Linux could not resolve four uppercase page imports: paths now match actual filenames.
- Two Compose services exporting one image tag raced: backend is now the only build owner.
- Gunicorn's optional control socket wanted a missing non-root home: disabled that socket.
- Three subcases in one readiness settings test inherited local HTTP origins while
  testing DEBUG=false: `patch.dict(..., clear=True)` now isolates its settings fixture.
  The targeted test then passed. No production validation or readiness logic changed.

HTTP checks returned 200 for `/`, `/login`, `/register`, `/games/1`, `/oauth/callback`,
admin login, `/static/admin/css/base.css` and `/maps/standard.svg` (206648 bytes).
`/api/users/me/` and `/api/games/` returned JSON 401; GET `/api/token/` returned JSON
405. `/api/orders/` is not a defined collection route and returned Django 404,
not SPA HTML. Providers returned 200 with Google/GitHub disabled. Direct backend
admin login also returned 200. Missing media returned nginx 404. A temporary file
written by UID 10001 was readable through nginx after backend recreation and then
removed; the read-only nginx media mount and persistent backend media were verified.

The original PostgreSQL container and `diplomacie_postgres_data` mount were retained.
SQLite SHA-256 before/after: `A16BBFE79A42CE7CFD60562BAEBF0D2BBB6426DFBDA7EACA81DA011710FCCBD6`.
No real SMTP or Google login was used. Browser gameplay checks above remain a manual
checklist; HTTP routing and automated frontend/backend regressions were performed.

| Validation | Final result |
| --- | --- |
| `docker compose config --quiet` | Passed; secrets not printed |
| `docker compose build` | Backend and frontend passed; migrate reuses backend |
| `docker compose up -d --build` | Passed |
| `docker compose ps -a` | PostgreSQL, backend, frontend healthy; migrate Exited (0) |
| Initialization logs | No pending migrations; existing map preserved |
| Gunicorn logs | 26.2.0, two sync workers, no control-socket error after fix |
| PostgreSQL logs | Inspected last 100 lines; no FATAL entries |
| Actual in-container connection | `postgresql`, host `postgres` |
| `showmigrations` | All migrations applied |
| `makemigrations --check` | No changes detected; no new model migration |
| Django `check` | Passed in container and native venv |
| `python manage.py test --noinput` | 261 passed, zero skipped |
| `config.test_postgres_concurrency` | 6 passed, zero skipped |
| `apps.games.readiness_tests` | 18 passed |
| `apps.orders.tests.test_postgres_locks` | 1 passed |
| Frontend `node --test tests/*.test.mjs` | 19 passed |
| Frontend `npm run build` | Passed natively and in Linux image |
| Frontend `npm run lint` | Existing 3 errors / 3 warnings, unchanged |
| `git diff --check` | Passed (Git emitted an informational LF/CRLF conversion warning) |
| `nginx -t` | Passed |
| Native `pip check` | Passed |
| Media persistence and permissions | Verified non-root write, read-only proxy mount and recreation survival |

Existing lint findings remain in OrderPanel, AuthContext, home and gameDetail.
The stack is left running. This is a **local production-like Docker stack validated**,
with manual browser gameplay/OAuth checks and the deployment limitations described above.
