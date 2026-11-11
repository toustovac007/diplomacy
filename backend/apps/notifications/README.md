# Email notifications

The existing `PhaseNotification` table is migrated to `EmailNotification` by
`0002_email_notifications`. Existing sent phase records keep their IDs,
timestamps and deduplication keys. Preferences are created lazily; all five
categories default to enabled. GET/PATCH/PUT `/api/notifications/preferences/`
always addresses the authenticated user.

## Delivery and privacy

Events register ID-based `transaction.on_commit` callbacks in `create_phase`,
chat `send_message`, draw `propose`/`vote`/`cancel`, and `finish_game`.
All recipients need a valid nonempty email and an enabled category preference.
Each email contains plain text and an autoescaped HTML alternative.

Chat recipients come only from conversation memberships, excluding the sender.
Draw creation notifies snapshotted voters except the proposer. Rejection and
explicit cancellation notify all snapshotted voters. Acceptance and automatic
cancellation on solo victory produce only the authoritative game-finished email,
sent to all enabled game players. No private orders or invite codes are included.

The unique `(recipient, event_type, event_key)` constraint plus an atomic
pending-to-sending claim gives at most one delivery attempt per event/recipient.
Success records `sent_at`; failure records only the exception class and is
contained inside the notification layer. Logs omit exception text and traceback.
Failed or interrupted (`sending`) attempts are not automatically retried: SMTP
acceptance can be ambiguous, and retrying could duplicate an email. Delivery is
best effort; exactly-once receipt cannot be guaranteed by SMTP. No message body
or SMTP credentials are stored in delivery records.

`process_deadlines` resolves expired phases and processes reminders. The existing
`process_game_tasks` and `process_notifications` commands remain compatible and
call the same reminder service; no new scheduler was added. Schedule just one
periodic flow (for example `process_deadlines` every minute). The server alone
does not run a scheduler. Reminders require an active game, open phase and future
deadline. Phases of at most 60 minutes use a 15-minute window; longer phases use
60 minutes. Each phase/user gets at most one reminder attempt.

## Local Windows / PyCharm test (no internet email)

1. In a terminal with working directory `backend`, run:
   `venv\Scripts\python.exe manage.py migrate`
2. In the PyCharm backend Run Configuration, set environment variables:
   `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`
   and optionally `FRONTEND_BASE_URL=http://localhost:5173`.
   Or set them in PowerShell before starting Django:

   ```powershell
   $env:EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
   $env:FRONTEND_BASE_URL = 'http://localhost:5173'
   .\venv\Scripts\python.exe manage.py runserver
   ```

3. Run the frontend (`npm run dev` from `frontend`). Log into two accounts in
   separate tabs. Both must have valid email addresses. Enable the relevant
   checkbox under **E-mailová upozornění** on Home and click **Uložit**.
4. Start a game with both accounts, or send a fresh chat message in an active
   game. The backend Run/terminal console prints the multipart email, including
   `To`, subject, plain text and HTML. A direct message prints only the other
   member's email, not the sender's. Nothing is sent to an internet mailbox.
5. For reminders, run `venv\Scripts\python.exe manage.py process_deadlines`
   when a phase is inside its reminder window. Run it twice: the second run
   must report no repeat reminders. Output appears in that command's console.

An already-delivered event will not print again. Trigger a *new* message or
phase when testing repeatedly. Switching from console to SMTP does not replay
events already recorded as sent by the console backend.

## SMTP later

Configure environment variables in the server process/PyCharm Run Configuration:

- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST`: SMTP hostname
- `EMAIL_PORT`: SMTP port, default 587
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`: supplied by the operator
- `EMAIL_USE_TLS=true` (or false for a server configured differently)
- `DEFAULT_FROM_EMAIL`: authorized sender address
- `EMAIL_TIMEOUT`: seconds, default 10
- `FRONTEND_BASE_URL`: deployed frontend origin, optional

No secrets belong in source control. Settings read the **process environment**;
this project does not automatically load `.env`. Debug defaults to console mail,
and non-debug defaults to SMTP unless `EMAIL_BACKEND` is supplied. A trailing
slash on `FRONTEND_BASE_URL` is removed; without it emails simply omit the link.
Tests use Django locmem mail and require no SMTP server.

Digest/rate limiting, background workers, delivery retry tooling, push, SMS and
external providers are intentionally deferred. Synchronous post-commit delivery
can add request latency, bounded per SMTP attempt by `EMAIL_TIMEOUT`.
