# PostgreSQL setup and validation

PostgreSQL is required when `DJANGO_DEBUG=false`. Development can temporarily use
the existing `backend/db.sqlite3` only when no nonempty POSTGRES_* setting exists.
Partial configuration is an error in both modes; it never silently selects SQLite.
The driver is `psycopg[binary]==3.3.7`, with a Python 3.13 Windows wheel. The former
psycopg2 requirement had no application-specific usage and was replaced.

## Configuration

| Variable | Policy |
| --- | --- |
| POSTGRES_DB | Required when PostgreSQL is selected |
| POSTGRES_USER | Required when PostgreSQL is selected |
| POSTGRES_PASSWORD | Required; value preserved exactly, never printed |
| POSTGRES_HOST | Defaults to 127.0.0.1 |
| POSTGRES_PORT | Integer 1–65535, default 5432 |
| POSTGRES_CONN_MAX_AGE | Nonnegative integer seconds, default 0 (Django default) |

Any nonempty value among these six variables selects PostgreSQL and requires the
three required fields. Empty numeric values are invalid once PostgreSQL is selected.
No pool, isolation override, timeout or SSL policy is introduced. Production
security settings (secret, allowed hosts, HTTPS frontend origin) still apply.
`.env.example` is documentation; Django does **not** automatically load `.env`.
Use PyCharm Run Configuration environment variables or the process environment.
Do not paste the full DATABASES dictionary into logs or support messages.

## PostgreSQL via Docker Compose (Windows, local infrastructure v1)

The root `compose.yaml` is the single Compose entry point. For native development,
run only `docker compose up -d postgres`; Django/PyCharm and React/Vite keep running
on Windows. For the complete Docker v2 stack, see [DOCKER.md](../DOCKER.md). No native
PostgreSQL installation is needed for this path. The native setup below remains
an alternative, not an additional prerequisite.

The service `postgres` uses the official `postgres:18` image, binds only
`127.0.0.1:5432`, and persists data in the project-scoped named volume
`postgres_data` (normally `diplomacie_postgres_data`). PostgreSQL 18 needs the
volume mounted at `/var/lib/postgresql`, with its default PGDATA underneath at
`/var/lib/postgresql/18/docker`; do not use the older image's mount path.
See the [official image documentation](https://hub.docker.com/_/postgres).

1. Install/start Docker Desktop with Linux containers. It typically uses WSL2;
   follow Docker Desktop's prerequisite prompts yourself. This task does not
   install Docker or change Windows/WSL features. From the repository root:

   ```powershell
   docker --version
   docker compose version
   docker info --format '{{.ServerVersion}}'
   ```

   If the Linux-engine named pipe is missing, Desktop's engine is not running.
   Start Desktop and wait until it reports running before continuing.

2. If root `.env` does not exist, create it from the example, then replace
   `change-me` with a strong local-only password:

   ```powershell
   if (-not (Test-Path .env)) { Copy-Item .env.example .env }
   notepad .env
   ```

   Root `.env.example` now documents the complete local Docker stack environment.
   `backend/.env.example` remains the complete Django/security/OAuth/email example.
   Existing ignore rules cover `.env` and secret variants and retain both examples.
   Do not overwrite an existing local file or commit a real password. Compose
   requires all three nonempty values; no trust/passwordless mode is enabled.
   If the task already generated an ignored `.env`, keep its generated password.

3. Validate and start from the root:

   ```powershell
   docker compose config --quiet
   docker compose up -d postgres
   docker compose ps
   docker compose logs --tail 50 postgres
   docker compose exec postgres sh -c 'pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
   ```

   `config --quiet` validates the resolved configuration without printing its
   password. Plain `docker compose config` and `config --environment` can expose
   secrets; do not paste their output. The pg_isready healthcheck uses configured
   user/database, interval 10s, timeout 5s, five retries and 30s startup grace.
   Wait for `healthy` in `compose ps`. Restart policy is `unless-stopped`.
   A port conflict requires stopping the other local database or deliberately
   changing both the Compose host port and Django port; do not expose all interfaces.

4. Set matching variables in the **Windows Django process**, not in a container:

   ```powershell
   $env:DJANGO_DEBUG = 'true'
   $env:POSTGRES_DB = 'diplomacy'
   $env:POSTGRES_USER = 'diplomacy'
   $env:POSTGRES_HOST = '127.0.0.1'
   $env:POSTGRES_PORT = '5432'
   $env:POSTGRES_CONN_MAX_AGE = '0'
   $pgCredential = Get-Credential -UserName diplomacy -Message 'Same password as root .env'
   $env:POSTGRES_PASSWORD = $pgCredential.GetNetworkCredential().Password
   Remove-Variable pgCredential
   Set-Location backend
   .\venv\Scripts\Activate.ps1
   ```

   If you changed DB/user in root `.env`, use those same values above. PyCharm
   needs these values in its Run/Test Configuration, using `backend` as working
   directory and its venv interpreter. Compose reads root `.env` automatically;
   Django does not. Use `127.0.0.1`, **not `postgres`**, for native Django.
   Process environment variables override Compose's `.env`; avoid stale exports.
   Keep existing Google/email configuration; frontend API URLs remain unchanged.

5. Verify the real connection, migrate the fresh database, seed and test:

   ```powershell
   python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print(connection.vendor); print(connection.settings_dict['HOST'])"
   python manage.py migrate --noinput
   python manage.py makemigrations --check
   python manage.py seed_map
   python manage.py check
   python manage.py test --noinput
   python manage.py test apps.games.readiness_tests --noinput
   python manage.py test config.test_postgres_concurrency --noinput
   python manage.py test apps.orders.tests.test_postgres_locks --noinput
   ```

   The connection must print `postgresql` and `127.0.0.1` after connecting. The
   six PostgreSQL concurrency tests must execute without skips. Django creates
   its normal temporary test database; do not point tests at the regular database
   with TEST.MIRROR or use `--keepdb` as a prerequisite. All OAuth/blacklist/history
   models migrate normally; no real provider login is required for these tests.
   Optionally run `createsuperuser`, then `runserver 127.0.0.1:8000` as usual.

   The official image-created POSTGRES_USER is a database **superuser**, able to
   create/drop test databases. This is accepted for this loopback-only local
   development instance, not a production role design. Later deployment should
   separate runtime/migration/test privileges. Credentials initialize only an
   empty volume: editing `.env` later does not change existing database passwords.

6. From the repository root, lifecycle commands:

   ```powershell
   docker compose stop postgres
   docker compose start postgres
   docker compose down
   ```

   `stop` keeps the container/data; `start` resumes it. `down` removes containers
   and the network but **keeps the named database volume**. A later `up -d postgres`
   reuses that data. **Destructive, optional reset:** `docker compose down -v`
   deletes the PostgreSQL volume and all its data. It is never run automatically.
   No SQLite file is mounted, deleted or imported by this setup.

## Windows native PostgreSQL alternative: fresh database

1. Install PostgreSQL using the [official Windows download](https://www.postgresql.org/download/windows/).
   Use a supported server release; the installed Django 6.0.7 backend requires
   PostgreSQL 14 or later. Add its `bin` directory to PATH or use full paths.
   Installation/service changes are developer-controlled and were not automated.
2. In a terminal, verify the service and tools:

   ```powershell
   psql --version
   pg_isready -h 127.0.0.1 -p 5432
   psql -h 127.0.0.1 -U postgres -d postgres
   ```

3. Inside psql, create a **new** local role/database. `\password` prompts without
   placing the password in shell/SQL history:

   ```sql
   CREATE ROLE diplomacy LOGIN CREATEDB;
   \password diplomacy
   CREATE DATABASE diplomacy OWNER diplomacy;
   \q
   ```

   Ownership lets this role create/migrate its schema. CREATEDB is for local
   Django tests, which create/drop `test_diplomacy`. Do not grant SUPERUSER.
   A deployed runtime role should not have CREATEDB; use a separate local/CI
   test role with that privilege. Never use the production database for tests.

4. From the repository's `backend` directory, use the existing virtual environment:

   ```powershell
   .\venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   $env:DJANGO_DEBUG = 'true'
   $env:POSTGRES_DB = 'diplomacy'
   $env:POSTGRES_USER = 'diplomacy'
   $env:POSTGRES_HOST = '127.0.0.1'
   $env:POSTGRES_PORT = '5432'
   $env:POSTGRES_CONN_MAX_AGE = '0'
   $pgCredential = Get-Credential -UserName diplomacy -Message 'Local PostgreSQL password'
   $env:POSTGRES_PASSWORD = $pgCredential.GetNetworkCredential().Password
   Remove-Variable pgCredential
   ```

   In PyCharm, select `backend/venv/Scripts/python.exe`, use `backend` as working
   directory, and set the same six POSTGRES_* variables in the run/test configuration.
   Keep passwords out of shared run configurations. OAuth/email variables remain
   exactly as documented in OAUTH.md and SECURITY.md.

5. Check both the configured vendor and an actual connection, without printing secrets:

   ```powershell
   python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print(connection.vendor); print(connection.settings_dict['HOST'])"
   ```

   Expected: `postgresql` and `127.0.0.1`. Merely printing `connection.vendor`
   without `ensure_connection()` verifies configuration, not server availability.

6. Apply all migrations from zero; do not use `--fake`:

   ```powershell
   python manage.py migrate --noinput
   python manage.py makemigrations --check
   python manage.py seed_map
   python manage.py createsuperuser
   ```

   `createsuperuser` is optional. `seed_map` loads standard map data needed for
   actual games; it does not import SQLite games/users. All app, OAuth, readiness,
   draw, snapshot and token-blacklist migrations run normally.

7. Run checks and tests with these PostgreSQL variables still present:

   ```powershell
   python manage.py check
   python manage.py check --deploy
   python manage.py test --noinput
   python manage.py test apps.games.readiness_tests --noinput
   python manage.py runserver 127.0.0.1:8000
   ```

   Readiness uses the existing nonstandard `readiness_tests.py` name, so it needs
   the explicit command in addition to default discovery. Django creates its own
   temporary test database; no `--keepdb` or TEST.MIRROR override is needed.
   The six PostgreSQL-only concurrency tests in `config.test_postgres_concurrency`
   must run, not skip. Deploy checks under DEBUG=true naturally report development
   settings; production-style settings retain documented W005/W021 warnings.

## Compatibility and lock audit

- Application queries use Django ORM. No application `raw()`, `RawSQL`, `extra()`,
  `cursor.execute()` or migration `RunSQL` was found. Existing RunPython migrations
  use historical ORM models and the schema editor's database alias.
- Models use portable JSONField, timezone-aware DateTimeFields (`USE_TZ=True`),
  boolean defaults, BigAutoField and normal FK deletion policies. PostgreSQL
  supports the partial unique open-draw constraint and nullable uniqueness used
  by adjustment orders and group chats. No model/migration changes were needed.
- Game join/start both lock Game first; start then locks GamePlayer rows. This
  serializes capacity checks with joins and country assignment.
- Order writes, readiness and phase resolution lock Game → GamePhase → readiness,
  orders/units. Resolvers lock units before orders where needed. The game lock
  serializes writers, and the phase-manager's repeated game lock is reentrant
  within the same transaction. No reverse phase→game entry path was found.
- **Confirmed PostgreSQL incompatibility fixed:** Movement unit/order, Retreat
  unit and Adjustment order queries used unqualified FOR UPDATE with nullable
  `select_related()` outer joins (coast, target, supported unit, etc.). PostgreSQL
  rejects locking the nullable side. These four queries now use
  `select_for_update(of=("self",))`, keeping locks on the intended base rows.
  Related map/reference rows do not need locks; game/phase locks remain held.
  A regression compiles queries issued by actual resolvers with PostgreSQL's
  compiler even without a server. This is SQL-shape validation, not a live DB test.
- Draw operations lock Game → DrawProposal, then update votes/results under that
  game lock. Chat locks Game before conversation creation; direct-pair and
  membership constraints remain authoritative. Neither architecture was changed.
- OAuth flows lock only their flow row and conditionally consume once. Tickets
  perform a conditional write before locking ticket/user, avoiding SQLite lock
  upgrades and serializing PostgreSQL exchanges. SocialIdentity joins only its
  nonnullable user; uniqueness and atomic rollback protect identity ownership.
  Existing OAuth code and provider setup were not changed.
- Deadline scanning is unlocked, but each resolver reacquires game/phase locks
  and rechecks status. A competing worker can report an already-resolved error;
  it cannot resolve that same phase again. Notification on_commit hooks and
  unique delivery records remain unchanged. Commands run only in isolated tests
  during this preparation, never against the preserved SQLite developer data.
- Foreign keys already supply indexes for game/player/phase joins. Existing
  order/readiness uniqueness indexes, game/phase sequence and conversation/-id
  history index cover the reviewed relational lookups. No workload evidence
  justified new indexes. Global deadline/list ordering tuning is deferred.
- OAuth `email__iexact` matching remains explicit; username/email exact database
  uniqueness is unchanged. No SQLite LIKE dependency was found in application
  filters. Timezone/expiry/deadline behavior stays covered by existing tests.

PostgreSQL's nullable-join restriction and `of` option are documented in the
[Django QuerySet reference](https://docs.djangoproject.com/en/6.0/ref/models/querysets/#select-for-update).
Driver support: [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).

## Historical validation boundary (superseded by live validation below)

**Historical preparation result: PostgreSQL server was not available then.** No psql or
pg_isready on PATH, no PostgreSQL Windows service/install directory found, no
POSTGRES_* environment configured, and no listener detected on 127.0.0.1:5432.
No server was installed. Configured vendor verification and Django checks using
PostgreSQL settings do not establish a live database connection.

At that earlier point, fresh PostgreSQL migrations, full
gameplay/notification/deadline tests, real row-lock concurrency, and application
startup on PostgreSQL were unverified. Tests run locally on SQLite are fallback
regressions only. Live Google OAuth was not retested; provider behavior was not
changed and existing mocked OAuth tests remain part of the backend suite.

## Existing data

Option A (current plan): use a fresh PostgreSQL database and create new test users
and games. Apply migrations and seed the map as above.

Option B (future, explicitly authorized): back up SQLite, plan an ORM-based
export/import with dependency ordering, content types/permissions handling,
sequence reset and integrity checks in a staging database. Decide whether old
test games are worth transferring. No importer or automatic data copy is included.

`backend/db.sqlite3` remains present and git-tracked. This task does not delete,
untrack, migrate, import from, or modify its data. Tests use Django test databases.

## Historical results recorded for the preparation

- `python manage.py test --noinput`: 261 discovered, 255 passed, six PostgreSQL-only
  concurrency tests skipped, on Django's isolated SQLite test database.
- `python manage.py test apps.games.readiness_tests --noinput`: 18 passed on SQLite.
- The backend run includes orders/convoys/retreats/adjustments, game/draw history,
  deadline command and notification tests, users/security/OAuth and existing
  ticket/direct-chat concurrency regressions. None establish PostgreSQL concurrency.
- Six new live-only tests cover final-slot join, start/join, simultaneous final
  Ready, duplicate resolution, final draw votes and OAuth flow consumption. Existing
  direct-chat/ticket/Ready-versus-order regressions are reused, not duplicated.
- Configuration and actual-resolver PostgreSQL SQL compilation: seven tests passed.
- `makemigrations --check`: no changes detected; no migration files added.
- PostgreSQL-configured `check`: passed. `check --deploy`: W005/W021 only, with
  explicit production-style settings. Configured vendor was `postgresql`; actual
  unconfigured development vendor was `sqlite`. No live PostgreSQL connection.
- Fresh PostgreSQL `migrate`/server startup: pending, not run against SQLite instead.
- `pip check`: passed; psycopg 3.3.7 import confirmed.
- Frontend `node --test tests/*.test.mjs`: 19 passed; `npm run build`: passed.
  `npm run lint`: existing three errors/three warnings in OrderPanel, AuthContext,
  home and gameDetail. `git diff --check`: passed. Frontend files were not edited.
- SQLite SHA-256 before/after matched; its pre-existing git modification was
  preserved, and no data was modified or copied by this task.

Files changed: `config/settings.py`, `config/environment.py`,
`config/test_database.py`, `config/test_postgres_concurrency.py`,
`requirements.txt`, `.env.example`, `SECURITY.md`, this `POSTGRESQL.md`,
`apps/orders/services/adjudication.py`, `apps/orders/services/retreat.py`,
`apps/orders/services/adjustments.py`, `apps/orders/tests/test_postgres_locks.py`,
`apps/users/test_security.py`, and `apps/games/readiness_tests.py`.
The last two only supply required database environment values to pre-existing
production-settings tests. Resolver edits only scope the four SQL locks.

## Historical Compose v1 attempt (2026-11-05; superseded)

Docker CLI 29.1.3 and Compose v5.0.0-desktop.1 are installed. Starting Docker
Desktop launched its processes, but the Linux engine pipe remained unavailable:
`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.`
`docker compose up -d postgres` and `docker compose ps` therefore failed to connect.
**The engine was unavailable during that attempt.** The later live validation
below supersedes this limitation. At that time the recommended action was to open Docker
Desktop, finish any first-run/prerequisite prompts and wait for its Linux engine
to report running, then follow the Compose steps above. Windows/WSL configuration
was not changed, and no PostgreSQL container/volume was created by this run.

- `docker compose config --quiet`: passed. Parsed resolved configuration also
  confirmed one postgres service, official major-pinned image, loopback binding,
  named volume and a non-placeholder local password without displaying it.
- Root `.env` was newly generated with a random development password, confirmed
  ignored and untracked. No real password is present in the example or Compose file.
  Root `docker/` and `docs/` directories were empty; no competing Compose/Dockerfile
  existed. Only `compose.yaml`, root `.env.example` and this guide were added/edited
  for the source change. Existing ignore rules were sufficient.
- Container start/health, actual Django PostgreSQL connection/vendor, migrations,
  migration consistency against PostgreSQL, map seeding, full backend test count,
  readiness, live concurrency and lock regression: **not run/live-unverified**.
  Previous preparation results above are historical, not this task's live results.
  No SQLite fallback was used to claim PostgreSQL success.
- Frontend regression: 19 passed. Production build: passed. `git diff --check`:
  passed. No frontend files changed.
- Existing tracked `backend/db.sqlite3` has an identical before/after SHA-256.
  No SQLite data was modified, imported or mounted. No volume was destroyed.

## Completed live PostgreSQL v1 validation

Before Docker v2, the user confirmed a healthy PostgreSQL 18 container and an
actual native Django connection (`vendor=postgresql`, `HOST=127.0.0.1`). The full
backend suite passed 261/261, concurrency 6/6 without skips, readiness 18/18, and
the browser authentication/API smoke test passed. These supersede the historical
engine-unavailable notes above; they are user-reported v1 results.

Docker v2 reuses the same service and persistent volume. Its backend uses internal
`POSTGRES_HOST=postgres`; native Windows Django continues to use `127.0.0.1`.
See [DOCKER.md](../DOCKER.md) for startup, guarded map initialization, tests and
local stack validation. Public deployment, production roles/backups/TLS and a
recurring deadline scheduler remain separate work.
