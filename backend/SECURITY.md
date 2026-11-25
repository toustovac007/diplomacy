# Security hardening v1 — 2026-10-22

The follow-up SQL input review and creator quotas (2026-11-25) are documented in
`SQL_AND_CREATION_SECURITY.md`. Current email ownership enforcement is documented
in `EMAIL_VERIFICATION.md`; the older findings below describe their original scope.

This is a bounded source/configuration and authorization review, not a penetration
test or a claim of production readiness. No gameplay rules were changed.

## Findings by severity

| Severity | Finding and impact | Status |
| --- | --- | --- |
| CRITICAL if used outside development | Django's signing secret was committed. Someone with that key could forge signed data/JWTs. | Removed from current settings. Production now requires `DJANGO_SECRET_KEY`. The previous value is never a fallback. **Operators must replace it everywhere it was deployed**, including any externally configured JWT signing key, and invalidate sessions/tokens. Removing source does not erase Git history or copies. |
| HIGH | Production configuration did not explicitly enforce host/origin restrictions and HTTPS defaults. | Strict environment configuration, HTTPS cookies/redirect and HSTS defaults added; deployment still needs TLS, trusted hosts, secure environment and proxy configuration. |
| MEDIUM | Registration used `create_user()` and write-only passwords, but only checked length, bypassing Django's configured password validators. | Calls `validate_password` with username/email context. Model already requires unique email; retained without migration. Duplicate username/email and invalid format remain serializer errors. |
| MEDIUM | No targeted login/registration/refresh throttles. | IP-based DRF throttles: 10/min, 5/hour, 30/min. No blanket polling throttle. These are approximate cache-backed abuse controls, not brute-force/DoS prevention. |
| MEDIUM | Refresh tokens were reusable until expiration; logout only removed local credentials; concurrent 401s could refresh concurrently. | Official SimpleJWT rotation/blacklist enabled, authenticated owner-scoped logout, per-tab refresh single-flight and stale-session guards. Both rotated tokens are stored together. |
| MEDIUM | Logging whole Axios errors can expose request passwords or Authorization headers in developer consoles. | Auth, Home, GameDetail and OrderPanel error logs now contain status only. GameMap's bundled-asset fetch error has no JWT; existing successful-order debug output contains only the current player's order, not credentials. |
| HIGH dependency advisory | `follow-redirects` 1.16.0 had credential-stripping flaws. It is an Axios transitive runtime dependency for the Node adapter, not the browser XHR adapter. | Patched only this package to 1.16.1 in the lockfile; runtime npm audit now reports zero vulnerabilities. |
| LOW / HARDENING | Missing root ignore rules allowed accidental secret/database additions. | Added `.env*` exclusions with `.env.example` exception, Python caches, local DB and build/tool artifacts. **`backend/db.sqlite3` was already tracked and remains tracked**; ignore rules do not untrack it. Do not publish it. No data deleted. |
| LOW / deployment | Frontend API and refresh URLs were duplicated localhost constants. | Both use `VITE_API_BASE_URL`; development fallback is localhost, production fallback is same-origin `/api/`. |

No additional confirmed object-level authorization bypass was found in the
reviewed routes. Existing controls were preserved rather than duplicated.

## Authorization and data audit

- Games: lists/details restrict to participant membership. Public discovery is
  authenticated, waiting + public only and excludes joined games. Private ID-only
  join rejects; UUID invitation flow remains. Invite codes are serialized only
  for members, never public discovery. Active/finished outsider access is denied.
- Orders: open Movement/Retreat queries filter unit owner; Adjustment queries
  filter current GamePlayer. Writes validate unit game and owner; adjustment
  cancellation also checks player, phase and deadline. New regression covers
  cross-account reads/writes in all three phases. Resolved history intentionally
  exposes all countries' resolved decisions to game members.
- Manual resolve: all three endpoints check `ALLOW_MANUAL_PHASE_RESOLVE` and
  creator ownership server-side. False always denies, including the creator.
- History: requires membership and resolves phase IDs from the requested game's
  resolved phases. Existing foreign-phase and outsider tests retained.
- Readiness: membership required, strict `{ready: boolean}` input; player comes
  from request.user. Existing game/phase locking and terminal-state checks retained.
- Draw: current player is derived server-side; voter and proposer checks, strict
  vote input and game-scoped proposal lookup remain. Forged voter IDs are rejected.
- Chat: conversation membership is the only access grant, including creator and
  winner. Foreign game/player IDs are rejected. Read/send/mark-read require the
  same membership; finished chats are read-only. Text is limited to 4000 characters,
  titles to 100, at the server serializer. Existing tests exercise these limits.
- Notifications: only `/preferences/` is exposed, acting on request.user; extra
  user IDs are rejected. Delivery records are not public. SMTP errors log only
  exception type, never password/content; email credentials remain environment-based.
- Mass assignment: registration only accepts username/email/password, not staff
  flags. Game creator/status/result/winner/finish data and order results are
  server-controlled. Public player representations omit email/password/token data.
- XSS: GameChat uses React text children. Backend and real-component frontend
  tests preserve `<script>alert(1)</script>` as literal text. No custom sanitizer
  needed. The only `dangerouslySetInnerHTML` is GameMap's fixed bundled
  `/maps/standard.svg` asset; fetch path is not user-controlled and dynamic marker
  labels use `textContent`. Replacing that trusted asset requires trusted deployment.
- SQL: application search found no `raw()`, `RawSQL`, `extra()` or
  `cursor.execute()` usage. Normal ORM filters are parameterized; no SQL rewrite.
- CSRF: middleware remains active; no application `csrf_exempt` was introduced.
  Header JWT APIs do not use cookies for authentication. Admin/session forms still
  require CSRF. CORS is a browser origin policy, not API authorization.

## Configuration and operations

`backend/.env.example` documents variables; Django **does not auto-load .env**.
python-dotenv is already in requirements but no loader was added. Set variables
in PyCharm, PowerShell (`$env:NAME='value'`) or the deployment environment.
Vite does load `frontend/.env.local`; `VITE_*` values are public build-time data.

- `DJANGO_DEBUG` accepts 1/true/yes/on or 0/false/no/off, case-insensitive;
  malformed input raises ImproperlyConfigured. Legacy `DEBUG` is accepted only
  when DJANGO_DEBUG is absent. Local default remains true.
- Development without a key uses an explicitly insecure development-only key.
  Production requires a real secret (placeholder values are rejected), explicit
  non-wildcard `DJANGO_ALLOWED_HOSTS` and HTTPS `FRONTEND_BASE_URL`.
- Generate a secret locally using
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`.
  Store its output in the deployment secret store, never Git/chat/logs.
- `DJANGO_CORS_ALLOWED_ORIGINS` and `DJANGO_CSRF_TRUSTED_ORIGINS` are comma-separated.
  Development CORS allows localhost:5173 and 127.0.0.1:5173. Production origins
  must be explicit HTTPS. CORS wildcard is disabled. Credentialed CORS is enabled
  only when OAuth is configured, for transient flow-binding cookies (see below).
- With DEBUG=false: SSL redirect and secure session/CSRF cookies default on;
  HSTS defaults to 31536000 seconds (`DJANGO_HSTS_SECONDS`). Local HTTP remains
  usable: redirect off, secure cookies off, HSTS zero.
- HSTS subdomains require explicit `DJANGO_HSTS_INCLUDE_SUBDOMAINS=true` after
  verifying every subdomain is HTTPS. Preload remains false. Deployment checks
  W005/W021 are intentional, documented and **not globally silenced**.
- `DJANGO_TRUST_X_FORWARDED_PROTO=true` enables the HTTPS proxy header only for
  a proxy that strips untrusted forwarding headers and sets its own. Never enable
  it for a backend directly reachable by untrusted clients. DRF NUM_PROXIES=0
  ignores spoofable X-Forwarded-For for throttling; behind a proxy this groups
  clients by proxy IP. Before deployment, configure a vetted proxy count/shared
  throttle cache or edge rate limiting appropriate to the actual topology.
- Django 6 defaults verified in installed source: X-Frame-Options DENY,
  X-Content-Type-Options nosniff, COOP same-origin, Referrer-Policy same-origin.
  SecurityMiddleware and clickjacking middleware are retained.
- Django serves APIs, Vite serves React HTML. A Django CSP alone would not protect
  that frontend HTML. Frontend CSP belongs to its eventual host/reverse proxy and
  must be designed/tested there; no misleading or broken policy added.

## JWT lifecycle

Access lifetime: **15 minutes**. Refresh lifetime: **7 days**, renewed on rotation
(no absolute session lifetime yet). SimpleJWT 5.5.1 official blacklist app is
enabled with ROTATE_REFRESH_TOKENS and BLACKLIST_AFTER_ROTATION. Its official
migrations 0001 through 0013 (upstream numbering skips 0009) were applied to the
development DB; run `python manage.py migrate --noinput` on every installation.
Run `python manage.py flushexpiredtokens` regularly in production.

`POST /api/users/logout/` requires authentication and revokes only a refresh
belonging to that user. Invalid/already-blacklisted refresh tokens are idempotent.
The frontend waits for an existing rotation before logout and revokes the newest
refresh. If access expired, logout can rotate then revoke without restoring local
credentials. Offline/unreachable-server logout still clears local state; remote
revocation cannot be guaranteed in that case. Existing access JWTs remain valid
until expiration; blacklisting is not immediate access-token revocation.

All credential reads/writes/removals use **sessionStorage**. Only removal of stale
legacy keys touches localStorage. France/England tabs retain independent storage
and logout; refreshes preserve the active tab account. Browsers may copy initial
sessionStorage into a duplicated/opener-created tab; logging into another account
replaces that copy. Rotation may invalidate a copied old refresh. This is not a
cross-tab synchronization mechanism. sessionStorage is still readable by XSS.

Axios uses a per-session single-flight refresh and one retry. Late 401s reuse a
new access token; old-account responses/refreshes cannot overwrite a new login.
Login failures do not refresh an old session. AuthContext tracks a session version,
not refresh-token equality (which changes during legitimate rotation), and clears
its user state on authentication failure. No cookies/OAuth architecture change.

## Regression coverage and validation

New tests: `apps.users.test_security` covers strict environment settings, password
validation/hashing/write-only fields, generic login failures, endpoint throttles,
rotation/replay rejection, logout and foreign-token revocation rejection.
`apps.orders.tests.test_security` fills cross-account open-order coverage for all
three phases. Existing games, draw, history, readiness, chat and notification tests
remain the authorization regression suite; no duplicate framework was introduced.
Readiness's settings-loading test now supplies required production configuration.

Frontend `apiSecurity.test.mjs` exercises the real Axios interceptors with a fake
transport: configured shared URL, legacy cleanup, simultaneous 401s, rotation,
logout, expired access at logout, failed refresh, and stale response isolation.
Chat lifecycle regression also verifies malicious markup is rendered as text.

Validation results:

- `python manage.py test apps.users apps.games apps.games.readiness_tests apps.orders apps.chats apps.notifications --noinput`: **234 passed**.
- `python manage.py check`: no issues. `check --deploy` with non-secret production-like
  environment: only documented W005 and W021. No warnings silenced.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- Official blacklist migrations applied successfully using `migrate token_blacklist --noinput`.
- Frontend tests: **18 passed**, including real AuthContext loading through initial
  token rotation and logout, all prior gameplay UI regressions and chat XSS rendering.
- `npm run build`: passed. `npm run lint`: existing 3 errors (OrderPanel effect,
  AuthContext mixed exports, Home effect) and 3 effect-dependency warnings remain.
- `git diff --check`: passed. `python -m pip check`: no broken requirements.
- `npm audit --omit=dev`: zero vulnerabilities after the patch. Full audit's three
  development-only findings are listed below. pip-audit unavailable/not installed.

Changed files (paths relative to repository root):

- `.gitignore`, `backend/.env.example`, `frontend/.env.example`, `backend/SECURITY.md`.
- `backend/config/settings.py`, `backend/config/environment.py`, `backend/config/urls.py`.
- `backend/apps/users/serializers.py`, `views.py`, `urls.py`, `throttles.py`, `test_security.py`.
- `backend/apps/games/readiness_tests.py`, `backend/apps/orders/tests/test_security.py`.
- `frontend/src/services/api.js`, `frontend/src/context/AuthContext.jsx`.
- `frontend/src/pages/login.jsx`, `register.jsx`, `home.jsx`, `gameDetail.jsx`,
  `frontend/src/components/game/OrderPanel.jsx` (logging only in the last three).
- `frontend/tests/apiSecurity.test.mjs`, `authContextSecurity.test.mjs`, `gameChatLifecycle.test.mjs`.
- `frontend/package-lock.json` (follow-redirects patch only).
- `backend/db.sqlite3` changed by official migrations; already tracked, retained.

## Deferred / deployment-dependent work

- Actually rotate previously deployed secrets; clean repository history where
  appropriate and remove the tracked development database from future commits
  through a deliberate backup/repository cleanup. This task did not erase history
  or developer data. Blacklist tables necessarily changed the local DB.
- Production TLS, shared cache, edge rate limits, trusted proxy topology, backups,
  monitoring and frontend CSP. DRF in-memory throttling is per-process and non-atomic.
- HttpOnly JWT cookie migration/2FA/password-reset architecture, absolute session lifetimes and
  stronger token-family replay detection/atomic cross-process refresh handling.
- Dependency audit: pip check validates compatibility, not known vulnerabilities.
  pip-audit was not installed; no security toolchain was installed for this task.
  Runtime npm audit is clean after follow-redirects 1.16.1. Full npm audit reports
  three HIGH **dev-only** findings: brace-expansion, source-map-js (transitive DoS),
  and Vite 8.1.5 (dev server/editor integration, including Windows). These were
  not mixed into the runtime patch; update/test development tooling separately
  and do not expose the Vite development server publicly. No forced/major upgrade.
  npm also warned that Node 23.7.0 is outside ESLint 10's declared engine range;
  use a supported LTS runtime for repeatable tooling.
- Real deployment, Cloudflare/nginx, WebSockets and UI redesign remain
  outside scope. Existing unrelated lint errors remain outside this task.

Database preparation now requires PostgreSQL configuration when DEBUG=false;
partial POSTGRES_* configuration fails in all modes, with no silent SQLite
fallback. DEBUG-only SQLite convenience remains. Driver, Windows setup, database
ownership/test permissions and the live-validation boundary are in [POSTGRESQL.md](POSTGRESQL.md).
Never log database passwords or full connection dictionaries.

References: [SimpleJWT settings](https://django-rest-framework-simplejwt.readthedocs.io/en/latest/settings.html),
[Django 6 settings](https://docs.djangoproject.com/en/6.0/ref/settings/).

## Social login v1

Google and GitHub only prove identity. Authlib 1.9.1 (requests 2.34.2 transport)
handles authorization-code/PKCE and Google discovery, signature, issuer, audience,
expiry and nonce validation. Scopes are exactly `openid email profile` and
`read:user user:email`. Secrets and provider tokens never enter frontend code;
provider access/refresh/ID tokens are not persisted.

`SocialIdentity` is uniquely bound by `(provider, subject)` and `(user, provider)`.
Google uses verified `sub`; GitHub uses its numeric ID as a string. Email changes
never reassign an identity. New users require verified email, stored in the
existing unique `User.email` field for notifications, with an unusable password.
Existing email matches (case-insensitive lookup) require password/social login
followed by explicit linking. Linking is authenticated at start, stores that
user in the flow, permits a different provider email, and never transfers an
identity from another user, including to admins. No unlink endpoint exists.

Random state is stored as SHA-256; random PKCE verifier and Google nonce stay
server-side for a ten-minute flow. Transactional single-use consumption clears
those secrets. An independent random HttpOnly, SameSite=Lax cookie binds each
flow to the initiating browser, preventing login/link CSRF; separate cookie names
allow concurrent tabs. These cookies cannot authorize game/API requests and do
not replace JWT auth. Secure is required outside DEBUG. Deployment must keep
frontend and API same-site and explicitly allow the frontend CORS origin.

Login redirects carry only an opaque 90-second ticket, never application JWTs.
Only its digest is stored. Exchange requires its browser binding and atomically
claims the ticket before issuing the usual SimpleJWT pair. Row locks plus
conditional updates protect one-use consumption; SQLite lock contention fails
closed. Inactive users cannot log in. Expired records older than one hour are
deleted opportunistically at flow start. Current refresh rotation, blacklist,
logout, per-tab sessionStorage and sessionVersion protections remain in use.

Public OAuth responses are no-store/no-referrer. The frontend strips callback
parameters promptly and declares a no-referrer policy. Errors expose allowlisted
codes only. Authlib/urllib3 logging is suppressed and Django OAuth request logs
omit URLs; production proxy/CDN/frontend-host logs MUST omit OAuth query strings
and request bodies too (configuration outside this repository). Never enable
HTTP body tracing for token exchange. OAuth does not remove the existing XSS
risk of JavaScript-readable sessionStorage JWTs.

Setup, environment variables and the real-provider manual test plan: [OAUTH.md](OAUTH.md).
