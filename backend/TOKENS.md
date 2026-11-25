# Token economy

Every account starts with 1,000 available tokens. `users.0005` grants this to
existing accounts once; the model default covers registrations, superusers and
new OAuth accounts. Login, email verification and identity linking never repeat
the grant. Tokens have no payment integration.

## Reservations and accounting

Game creation accepts `token_stake` of 100, 200, 300, 500, 800, 1000 or 1500 and
`scoring` (`dss`, `sos`, `unranked`). Settings cannot be changed through the API
after creation. Creation/public join/private invitation join reserve a stake,
including the creator. Insufficient available funds return 409 and roll back
membership, pot, balance and creation timestamp. The existing 10-second creation
cooldown and 10-open-created-game safeguard remain.

Frozen funds are the sum of `GameStake` rows in state `locked`; available tokens
live on `User`. `Game.token_pot` preserves the historical accepted stakes, and
`tokens_settled_at` records payment. A settled historical pot is not unpaid
escrow. Clients cannot write balances, pots, settlement times or payouts.

`TokenEntry` records available/frozen deltas for reservations, eliminations,
settlements and refills. The opening 1,000 is implicit, not a recurring ledger
event. Available balance reconciles to 1,000 plus available deltas, and frozen
balance to frozen deltas while game history is retained. Direct deletion/manual
modification of funded games or accounts is unsupported. Creators can delete
waiting games through the authenticated DELETE endpoint, which refunds all
stakes transactionally. Automatic 48-hour lobby expiry uses the same service.

## Results

- Ranked solo: the sole winner gets the whole pot.
- DSS draw: selected shared winners receive equal portions.
- SoS draw: selected shared winners receive portions proportional to their
  squared supply-center counts. If all their counts are zero, split equally,
  since a power may survive on units alone.
- Exact integer arithmetic; all remaining tokens go to the recipient with the
  most centers. Ties use the earliest membership.
- Unranked: eliminated players are refunded immediately. Remaining participants
  get their stake back at completion; early refunds are never paid twice.

Stable phase transitions mark a ranked player's reservation `forfeited` when
they have no centers AND no units. Dislodged/retreating units still count. The
stake disappears from personal frozen wealth but stays in the pot. Unranked
stakes are returned immediately on elimination, preserving their owner's wealth.
Elimination alone does not trigger a minimum refill. `token_pot_remaining`
excludes early refunds and becomes zero after settlement; active UI uses this
value, while `token_pot` retains the historical total accepted stakes.

Finishing and payment are one transaction; email callbacks run after commit.
Game operations lock the game then users in ascending PK order. Settlement
checks the pot against reservations and records completion; repeated settlement
is inert. A stale finish cannot change an already-settled result.

## Minimum refill

After settlement, funded participants with available + frozen below 300 get
exactly their deficit as available tokens. The first refill is immediate. Later
refills require 48 hours since the previous actual grant; otherwise the account
records `token_refill_due_at`.

`python manage.py process_token_refills` processes indexed due timestamps,
locking/rechecking each account. A grant starts a fresh 48-hour cooldown from
the granting time. If wealth has recovered to 300, cancel the queued grant
without consuming the cooldown. Frozen stakes in other games count toward 300.

CronJob `diplomacy-token-refills` runs hourly; an expired cooldown waits for the
next successful run. Overdue grants catch up by due timestamp. No open browser
is needed. Deployment pauses both schedulers and waits for active jobs before
migrations, then resumes them on the deployed image. Refills need no SMTP/OAuth.

## UI and API

Verified authenticated users read their own `GET /api/users/tokens/` and the
top ten at `GET /api/users/ranking/`. Ranking includes active verified accounts,
ordered by available + frozen descending, then account PK ascending. It exposes
usernames/counts, never email addresses. Responses use no-store.

Only headquarters shows the generated coin and desaturated frozen icon.
Creation uses native dropdowns, disables unaffordable choices/public joins and
also validates on submit; backend checks remain authoritative. Balances refresh
after creation/join, on focus and each visible minute. Cards/lobbies show stake,
scoring and bank; completed personal cards show payout. Below 300, the notice
shows pending days/hours or explains eligibility at game completion. `/ranking`
is a separate view with a horizontally scrollable table on narrow screens.

## Rollout

Deploy `games.0014`, `users.0005`, both images and `deploy/k8s/token-refills.yaml`
together after a database backup. Old backend writes must stop before migration.

The 108 pre-token games were explicitly reset on 2026-11-25 after validating a
custom-format database backup. Four accounts and two OAuth identities remained.
The deletion is not in migrations/deployment scripts. Check that no unfunded
legacy games appeared before rollout; do not silently delete newly created games.

Tests: `apps.games.test_tokens`, `apps.games.test_token_concurrency`, existing
creation/gameplay suites and `frontend/tests/homeDashboard.test.mjs`. Concurrency
tests skip SQLite and must also run on a separate PostgreSQL test database.

Reference: https://webdiplomacy.net/points.php. Selected draw winners retain this
application's existing semantics, as confirmed by the operator.

## Validation (2026-11-25)

- Complete SQLite suite: 328 tests, 310 passed and 18 PostgreSQL-only skips.
- 48 focused PostgreSQL tests passed without skips against a separate test
  database, including simultaneous cross-game joins, creation versus joining,
  repeated settlement, opposite winners sharing accounts, refill workers and
  elimination racing settlement. Both migration regressions passed there.
- All 25 frontend tests passed; production build passed. The dashboard test
  covers balances, disabled choices, guarded submission, scoring payloads,
  refresh after reservation, refill countdown and ranking rows/navigation.
- Migration consistency, Django checks, deployment-script parsing, server-side
  CronJob dry-run and whitespace checks passed. Existing frontend lint findings
  remain three errors and three warnings; no new lint findings.
- These results validate candidate source, not a deployed token economy.
  Building/publishing the new images and applying migrations remain rollout work.
