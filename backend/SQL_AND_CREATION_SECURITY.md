# SQL inputs and game creation review, 2026-11-25

This is a bounded review of application query construction and game-creation
abuse controls. It is not a complete penetration test or dependency audit.

## SQL injection findings

120 non-test Python source files under `backend` were inspected, including
migrations and management commands. No application `raw()`, `RawSQL`, `extra()`,
SQL cursor execution or manually assembled SQL was found. Query values pass
through Django ORM filters/lookups, creates and updates. Ordering fields are
server-defined. The invitation lookup expands only the fixed `invite_code`
field validated by `JoinByCodeSerializer` as a UUID; it does not accept arbitrary
request keys as ORM lookup names. Numeric URL IDs are typed by the router.

No exploitable SQL injection was identified in the reviewed application paths.
Regression tests intercept SQL execution and check that quote/OR/UNION/statement
payloads are passed as separate driver parameters, never interpolated into SQL.
They exercise game creation and login, check exact stored game names, reject
malformed invitations/IDs and retain outsider access restrictions.

The deployment readiness probe's `SELECT 1` is a constant with no user input.
Maintenance SQL used by operators for backups/checks is not a public API.

Do not blacklist apostrophes or SQL keywords as an injection defense. Legitimate
game names containing quotes remain supported. Parameterized queries keep text
separate from SQL syntax. HTML output must independently remain escaped: React
renders names as text and Django HTML mail templates use autoescaping.

## Creation policy

The public creation path delegates to `apps.games.services.creation.create_game`.
It locks the creator's database row, checks quota/cooldown, inserts the game and
its creator membership, then records the timestamp in the same transaction.
PostgreSQL row locking serializes concurrent requests across workers/replicas.
SQLite development obtains a write lock first and returns a retryable 503 if
another writer holds it. Cache resets/new JWTs do not reset the policy.

- Default: one successful creation every 10 seconds per account.
- Default: at most 10 created games with status `waiting` or `active`, combined.
- Finished games and membership in games created by someone else do not count.
- Joining games is unaffected. Existing accounts/games are not deleted or renamed.
  Creators already above quota cannot create more until their open count drops.
- Cooldown rejection returns HTTP 429 and `Retry-After`. Quota rejection returns
  HTTP 409 with a user-facing message. Polling/list/detail requests are not throttled
  by this policy.
- A recent legacy game's `created_at` is respected before the creator has a new
  timestamp. Finishing/deleting a game does not clear the durable timestamp.
- Failed validation does not consume the budget. Failed membership/game writes
  roll back the game, membership and timestamp together.
- The creator and game status come from the server. Forged creator/status/timing
  values cannot create outside the policy.

`GAME_CREATE_COOLDOWN_SECONDS` defaults to 10 (environment range 1–3600).
`GAME_MAX_OPEN_CREATED` defaults to 10 (environment range 1–1000). They are
documented in `.env.example`; tests can override cooldown to isolate quota checks.
The point/stake system can later change this policy in this service. The current
rules are application quotas, not volumetric denial-of-service protection.

Migration `users.0004_game_creation_cooldown` adds only a nullable internal
timestamp. Deploy the backend migration with the new backend image. The frontend
also limits input lengths, prevents duplicate in-flight creation requests and
shows backend rejection messages while retaining entered settings.

## Input lengths

- Game names: existing server maximum 100 retained and added to the form.
  Empty names and control/invisible formatting characters are rejected. Quotes,
  punctuation and normal Unicode remain valid literal data.
- New registered usernames: maximum 32, with Django's existing Unicode username
  validator (letters/digits/underscore and `.@+-`). Quotes/control characters were
  already outside this policy. New OAuth usernames reserve room for a collision
  suffix within the same 32-character limit.
- The stored username field remains 150 characters. Existing longer usernames
  are preserved and can still log in. No username migration/automatic renaming.

## IP/login follow-up

Existing login/register/refresh throttles remain 10/min, 5/hour and 30/min. They
are cache-backed approximate controls, not complete brute-force protection.
Before stronger per-IP restrictions, configure and test trusted client-IP
forwarding across ingress/nginx. Current `NUM_PROXIES=0` avoids trusting spoofed
forwarding headers but can group users behind the application's proxy.

A future policy should combine failed-attempt budgets per account and trusted
client IP, temporary cooldowns, monitoring and optional CAPTCHA/escalation.
Permanent blanket bans or a strict one-account-per-IP rule can lock out a whole
school/shared network and are not enabled here. Mail verification alone does
not guarantee one account per human.

## Validation

- Full backend SQLite suite: 298 tests, 287 passed and 11 PostgreSQL-specific
  tests skipped. No failed tests.
- 51 focused tests passed on a separate PostgreSQL test database, including SQL
  parameter capture, creator limits, simultaneous last-slot/cooldown requests,
  OAuth username generation and existing game concurrency cases. Candidate code
  ran in an isolated temporary directory; public source/data were not replaced.
- A simulated 100-request script with cooldown disabled only in the test created
  exactly ten games and received 90 quota rejections. Separate tests cover the
  default 10-second cooldown, exact expiry, durable state after cache clearing or
  game removal, independent accounts, and transaction rollback.
- All 23 frontend tests and the production build passed. The real dashboard
  component was tested for duplicate in-flight submissions, input limits and
  backend error presentation. Existing lint findings remain three errors and
  three warnings.
- Django system checks, migration consistency and `git diff --check` passed.
  Deployment of these changes still requires publishing both images and applying
  `users.0004_game_creation_cooldown` with the usual deployment script.

References: [Django SQL protection](https://docs.djangoproject.com/en/6.0/topics/security/#sql-injection-protection),
[OWASP SQL injection prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html),
[DRF throttling/concurrency](https://www.django-rest-framework.org/api-guide/throttling/).
