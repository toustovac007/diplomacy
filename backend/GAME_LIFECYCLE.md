# Lobby cancellation, expiry and inactive-game draws

## Waiting games

The creator can DELETE `/api/games/{id}/` only while it is waiting. The lobby
shows a confirmation dialog with cancel, Escape, focus handling and disabled
controls while sending. Failure keeps the dialog open for retry; success returns
to headquarters with a refund notice. Members cannot delete another creator's
game; active/finished games return 409. No unauthenticated deletion is allowed.

`cancel_waiting_game` locks the game, validates escrow, then locks all affected
users in ascending PK order. Every stake is returned exactly once as available
tokens, with a `refund` ledger entry. The game and game-related rows are deleted;
ledger rows remain with a null game reference and still reconcile each account.
Any failure rolls back the entire refund/deletion. The creator's existing
creation cooldown is not reset by cancellation.

`process_deadlines` also removes waiting games whose latest successful member
join (including initial creation) is at least 48 hours old. The existing minute
CronJob runs this without browsers. A full waiting lobby also expires if nobody
starts it. A successful new member join restarts the window; duplicate/failed
joins, viewing, copying the code or editing local UI do not. Expiry is rechecked
under the same game lock used by joins/start, so a concurrent new member can
rescue the lobby and a started game cannot be deleted. An expiry can happen up
to the next successful scheduled check after the 48-hour threshold.

The API exposes `waiting_expires_at`; lobby polling handles a deleted game by
returning home. No separate scheduler or additional secrets are required.

## Ten inactive resolved phases

Each successful movement, retreat or adjustment resolution counts once.
`inactive_phase_count` records the consecutive streak. Any successfully submitted
player order, including explicit HOLD/disband or an order later cancelled,
resets the streak at resolution. Invalid requests do not. Chat, login, readiness,
generated HOLDs and automatic disbands do not constitute an order submission.

`GamePhase.has_submitted_orders` preserves accepted activity when an order or
its unit is deleted. API writes and adjudication share game/phase locks.
`inactivity_checked` prevents double counting. Existing open non-default orders
are marked during migration. Existing games start the new streak at zero;
historical activity is not guessed retroactively.

On the tenth consecutive inactive phase the game finishes immediately with
`result_type=draw`, `termination_reason=inactivity` and all survivors included.
A survivor has a center OR any unit (including a dislodged unit). No next phase
is created. Fall ownership changes apply before SoS weights are computed; normal
solo victory has priority when its threshold has been reached. DSS, SoS and
unranked use the existing settlement service and minimum-refill policy. A single
survivor receives the pot; if nobody survives, stakes are returned rather than
leaving inaccessible funds. Manual draw proposals still require two participants.

## Immediate unranked refunds

Ranked elimination still forfeits the stake into the pot. Unranked elimination
now changes a locked reservation to `refunded`, records its paid amount, returns
the entire stake to available balance and removes it from frozen funds. The
historical pot stays intact for accounting; `token_pot_remaining` excludes these
refunds. Final settlement skips refunded reservations and preserves their receipts.

`games.0016_lifecycle_backfill` returns already-eliminated unranked stakes once
and preserves existing open player orders. The initial 1,000-token grant is not
repeated. Deploy with `games.0015` and `users.0006` together after backup and the
usual pause of the application and both schedulers. Do not downgrade to the old
settlement code after refunds; restore a consistent backup if rollback is needed.

## Checks

Tests in `test_lifecycle.py` cover creator permissions, refund rollback,
48-hour boundaries, renewed membership, all phase types, ten actual default
resolutions under all scoring modes, deleted retreat orders, early refunds and
migration backfill. `test_lifecycle_concurrency.py` requires PostgreSQL and checks
delete/join/start races, simultaneous cleanup, early/final refunds, double
resolution and last-moment orders. These run against a separate test database.

Validation on 2026-11-25: complete SQLite suite 351 tests (327 passed, 24
PostgreSQL-only skips); 71 focused PostgreSQL tests passed without skips; all
25 frontend tests and the production build passed. Lint retains the existing
three errors and three warnings. Migration consistency and Django checks passed.
The new nginx headers were exercised on an isolated localhost server in the
existing Pod without changing the live nginx configuration. Built HTML, XML
sitemap and robots rules were checked. Deployment of this revision is pending.
