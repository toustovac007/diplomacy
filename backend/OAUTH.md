# Google and GitHub login

Password login remains available. Providers are optional: missing client ID,
secret or redirect URI disables that provider. No credentials are needed for
automated tests. `Authlib==1.9.1` and `requests==2.34.2` extend the existing
SimpleJWT authentication; they do not establish a Django login session.

## Local setup

Use **127.0.0.1 consistently**, including the browser address bar. Do not mix it
with localhost during a flow. Django does not automatically read `.env` files:
set these via the IDE environment, PowerShell environment or your secret store.
`backend/.env.example` contains placeholders only.

1. Install `backend/requirements.txt` into the existing virtual environment.
2. Run `python manage.py migrate` in backend.
3. Set `FRONTEND_BASE_URL=http://127.0.0.1:5173`.
4. Run Django on `127.0.0.1:8000` and Vite on `127.0.0.1:5173`.
5. Open `http://127.0.0.1:5173`. Frontend API base is
   `http://127.0.0.1:8000/api/` (`VITE_API_BASE_URL` if overridden).

Google: create a **Web application** OAuth client in Google Cloud / Google Auth
Platform. Configure the consent screen and test users if in testing mode. Set
the authorized redirect URI exactly to:

`http://127.0.0.1:8000/api/users/oauth/google/callback/`

Set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and
`GOOGLE_OAUTH_REDIRECT_URI` on the backend. Only `openid email profile` is
requested; no Google API access such as Drive or Calendar is needed.

GitHub: create a **GitHub OAuth App** in Developer settings, with homepage
`http://127.0.0.1:5173` and authorization callback URL exactly:

`http://127.0.0.1:8000/api/users/oauth/github/callback/`

Set `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` and
`GITHUB_OAUTH_REDIRECT_URI` on the backend. Only `read:user user:email` is
requested, using PKCE S256. No repositories or device flow. A new account needs
a verified email: primary verified first, otherwise the alphabetically first
verified address returned by GitHub. Existing identity login and authenticated
linking do not depend on provider email equality.

Never commit real secrets or put them in `VITE_*` variables.

## Production

Configure explicit HTTPS backend callback URIs and `FRONTEND_BASE_URL` (origin,
without path/query). Register exactly those URIs with each provider. Redirects
never derive from Host or user-supplied URL parameters. Frontend and backend must
be same-site (e.g. app.example.com and api.example.com); add the exact frontend
origin to `DJANGO_CORS_ALLOWED_ORIGINS`. The transient HttpOnly flow cookie uses
SameSite=Lax and Secure; it is not an authenticated application session. JWTs
still live only in per-tab sessionStorage. Different-site deployments need a
separate cookie/topology design and are not supported by this version.

Disable query-string/body logging for `/api/users/oauth/*` and `/oauth/callback`
at the proxy/CDN/frontend host. Django strips OAuth URLs from request logs and
suppresses library protocol logs. Keep normal security settings from SECURITY.md.
Do not expose the development server publicly.

### School Kubernetes Google client

Email ownership checks also apply to social login and ticket exchange. See
`EMAIL_VERIFICATION.md` for Google authoritative-address handling and migration
of existing accounts. Local accounts must complete email verification before
logging in to explicitly link a social identity.

The deployed frontend origin is `https://diplomacy.kube.sspu-opava.cz`. Register
this exact authorized redirect URI on the existing Google Web application client
under Google Auth Platform / Clients:

`https://diplomacy.kube.sspu-opava.cz/api/users/oauth/google/callback/`

The callback is also set in `deploy/k8s/config.yaml`. The backend container reads
`GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` from the separate Secret
`diplomacy-google-oauth` in namespace `diplomacy`. This optional Secret is mounted
into the backend container's environment only. Supply its values through Rancher
or a local credentials transfer. Existing development callback URIs can remain
registered on the client. Restart the Deployment after changing Secret values.

Check `/api/users/oauth/providers/` for `google: true`, then verify the login in a
browser. A local password account with the same email needs deliberate linking
from the account panel before Google login can access that account.

## Endpoints and storage

- GET `api/users/oauth/providers/`: public enabled booleans.
- POST `api/users/oauth/{google|github}/start/`: login authorization URL.
- POST `api/users/oauth/{google|github}/link/start/`: authenticated link start.
- GET `api/users/oauth/{google|github}/callback/`: consumes ten-minute flow.
- POST `api/users/oauth/exchange/`: `{ticket}` -> ordinary JWT pair, one use/90s.
- GET `api/users/oauth/identities/`: current user's linked booleans only.

Start and exchange requests use `withCredentials` for the binding cookie;
link/identities additionally require the current tab's JWT. Public endpoints
never receive a stale JWT from the Axios interceptor. Each flow has its own
cookie, so starting another tab's flow does not overwrite it. The flow's local
user at authenticated link start is authoritative, even if another tab logs in.

Models/migration: `SocialIdentity`, `OAuthFlow`, `OAuthLoginTicket` in
`users/0002_oauthflow_oauthloginticket_socialidentity.py`. No provider token fields.
Local usernames are normalized to Django characters, capped below 150 chars,
with a random suffix on collisions. Database constraints/transactions prevent
duplicate identities and roll back losing user creation. Email is already
unique in User (database exact uniqueness; lookup also checks case-insensitively).

## Manual browser checks (requires real provider credentials)

These are a test plan, not a claim of completed provider testing.

1. For each provider, authorize a new verified account. Return to Home, check
   local username and users/me, then refresh tokens and log out. Social-only
   password login must fail.
2. Create a password account, then try first social login with its email. It
   must show the account-link-required message, without logging in. Log in by
   password, expand “Účet a přihlášení”, link provider, log out, and log in through
   that provider. It must return the original local account. Repeat linking to
   the same account (idempotent); try another user's identity (must be rejected).
3. Link an identity with a different email: allowed after deliberate JWT-backed
   link start. Return to Home and reopen account details; status must be updated.
4. Cancel provider consent; verify a Czech error and back-to-login button. Retry
   an old callback URL/ticket; it must fail. Unknown errors must stay generic.
5. Log France in via Google in tab A; independently log England in via GitHub
   in tab B. Verify each tab's requests/me and logout B without affecting A.
   Reload each tab: its session persists. A newly duplicated tab may initially
   inherit the opener's sessionStorage snapshot; subsequent logins remain
   independent. Start simultaneous flows to check neither cookie is overwritten.
6. Check URLs/history/network: no JWT in redirects, no secret/provider token in
   frontend data, one ticket exchange even under React StrictMode, no ticket left
   in the final Home URL. Confirm STP/game/map/chat behavior remains unchanged.

Automated tests mock provider HTTP and exercise Authlib with signed RSA Google
ID tokens (including invalid signatures/claims), plus replay, expiry, binding,
ownership, concurrency, normal JWT rotation/logout and frontend integration.
No live Google/GitHub HTTP is used in tests.

References: [Authlib web clients](https://docs.authlib.org/en/stable/client/frameworks.html),
[Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect),
[GitHub authorization code/PKCE](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps).

Deferred: unlink, password reset/social password setting, 2FA/passkeys, other
providers, HttpOnly JWT migration and provider API integrations.

## Files changed by this OAuth task

Backend:

- `apps/users/models.py`: three new models; existing User email policy retained.
- `apps/users/migrations/0002_oauthflow_oauthloginticket_socialidentity.py`: new migration.
- `apps/users/oauth.py`: transactional flow, account and ticket operations.
- `apps/users/oauth_providers.py`: Authlib provider integration.
- `apps/users/oauth_views.py`, `apps/users/urls.py`: OAuth endpoints.
- `apps/users/oauth_logging.py`: request URL redaction.
- `apps/users/throttles.py`: two OAuth throttle scopes.
- `apps/users/test_oauth.py`: mocked-provider, JWT and concurrency regressions.
- `config/settings.py`: optional provider settings, URL checks, OAuth CORS/logging.
- `requirements.txt`: pinned Authlib and requests additions (existing encoding retained).
- `.env.example`, `SECURITY.md`, `OAUTH.md`: configuration, security and setup guide.
- `db.sqlite3`: applied the new migration to the existing local database.

Frontend:

- `src/services/api.js`: public OAuth endpoint allowlist.
- `src/services/oauth.js`: provider start and safe Czech error messages.
- `src/context/AuthContext.jsx`: shared password/OAuth session completion.
- `src/App.jsx`: callback route outside auth gating.
- `src/pages/OAuthCallback.jsx`: one-time exchange, safe URL cleanup/navigation.
- `src/components/SocialLogin.jsx`, `src/pages/login.jsx`: optional provider buttons.
- `src/components/AccountLogin.jsx`, `src/pages/home.jsx`: compact linking section.
- `src/index.css`: small provider/account spacing rules.
- `index.html`: no-referrer policy for callback tickets.
- `tests/oauth.test.mjs`: real component/context/Axios integration with mocked HTTP.
- `tests/apiSecurity.test.mjs`: public/protected endpoint and independent-tab regression.

Other pre-existing working-tree changes were preserved. No gameplay/backend
adjudication, map or order interaction code was changed by this OAuth task.
