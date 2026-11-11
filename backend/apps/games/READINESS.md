# Phase readiness

Apply `python manage.py migrate` to install `0013_phase_readiness.py` before
using readiness. No historical data backfill is needed.

Participants use GET/POST `/api/games/<game_id>/readiness/`. POST accepts only
`{"ready": true}` or `{"ready": false}` for their current open phase.
The response contains aggregate ready/required counts and only the caller's
readiness and missing-order/build/disband counts. A finished game's GET returns
terminal status with no open phase so other tabs can stop; POST is rejected.

Movement requires players with active units. Missing orders remain implicit
until adjudication supplies HOLD. Winter uses the existing adjustment delta;
zero is excluded, builds may be waived, mandatory disbands must all be saved.
Retreat continues to complete automatically when all decisions are entered.

All readiness/order mutations and resolvers lock game, phase, then orders/units
inside a transaction. Draw voting shares the game lock. SQLite obtains a write
lock with a no-op game update; contention can return a retryable 503 instead of
allowing a late order write. Ready records belong to one phase and are retained.

Last Ready calls the existing resolver. Deadline fallback, phase skipping,
victory, draw cancellation, and existing on-commit notification hooks remain
authoritative. There are no Ready emails.

## Manual resolution configuration

This repository defaults to development (`DEBUG=true`). For presentation or
deployment, set `DEBUG=false`; manual resolution then defaults to disabled.
Set `ALLOW_MANUAL_PHASE_RESOLVE=false` explicitly to disable it even in debug.
The explicit override `ALLOW_MANUAL_PHASE_RESOLVE=true` enables creator-only
manual testing regardless of DEBUG. True values (case insensitive, surrounding
whitespace ignored): `1`, `true`, `yes`, `on`. Every other supplied value is
false. These are process environment variables; this settings file does not
load `.env` automatically.

All three manual API endpoints reject even the creator with 403 when disabled.
The participant serializer exposes only `manual_resolve_allowed`, true for an
allowed creator in an active game with an open phase. The UI requires that
capability; automatic deadline/readiness/Retreat resolution ignores the manual
setting. Setting this flag is not a substitute for normal Django production
configuration.

The Hra readiness panel polls every 10 seconds, prevents overlapping requests,
aborts on unmount, and reloads game state on phase mismatch. Ready disables map,
text, build/disband, and cancellation inputs, preserving saved orders and all
chat/history/draw functionality.
