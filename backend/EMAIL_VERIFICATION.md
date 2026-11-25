# Email verification

Password registration now creates an unverified account and returns a generic
confirmation message, without JWTs. The frontend displays a check-your-mail
screen instead of automatically logging in. Existing accounts, passwords,
games and social identity links are retained. No existing address is marked
verified by migration.

## Account access

- `User.email_verified_at` records when the proof was accepted.
- `email_verified_for` binds that proof to the stored address. Address comparison
  follows the existing case-insensitive OAuth lookup policy. New password/OAuth
  registrations normalize addresses to lowercase. Provider-specific dot/plus
  transformations are not applied.
- Password login checks verification before issuing JWTs. The API authentication
  class and refresh serializer recheck the current database state, so old JWTs
  cannot bypass verification, including after an address change.
- Game notification delivery skips inactive and unverified users without creating
  a delivery record. Historical game events are not automatically replayed.
- Google Gmail and verified Workspace addresses can be verified from fresh,
  validated provider claims matching the stored address. Third-party Google
  addresses need our email confirmation even if `email_verified` is true.
  GitHub's verified-email API is also supported when that provider is configured.
- A linked identity with a different email cannot verify the stored address.
  Matching an existing account by email never automatically links identities.
- Django administration retains its existing staff/active-account policy. It
  does not grant an unverified staff account access to the game API.

## Email and endpoints

Dedicated `users/email/verify.txt` and `verify.html` templates use the existing
SMTP configuration. The link is built from the configured frontend origin,
never the incoming Host header, and has the form `/verify-email#token=...`.
The fragment is removed from browser history on page mount. Merely opening the
link, refreshing the page or an email scanner's GET does not activate an account.
Activation requires the user's confirmation button and an explicit API POST.
Confirmation never signs a user in or replaces an existing password.

- `POST /api/users/register/`: validates credentials, retains existing credentials
  for a duplicate email, creates a pending account if necessary, and requests
  verification. Returns a generic message with HTTP 201.
- `POST /api/users/email/verification/request/` with `email`: HTTP 202 with the
  same message for unknown, already verified, inactive and pending addresses.
- `POST /api/users/email/verification/confirm/` with `token`: HTTP 200 after
  activation or HTTP 400 `verification_invalid` for unusable proofs. GET is 405.
- `POST /api/token/`: a correct password for an unverified account returns HTTP
  401 `email_not_verified`. Incorrect passwords retain the generic login error.

Tokens contain 32 cryptographically random bytes, are stored only as SHA-256
digests, expire after 24 hours and are single-use. A successful resend replaces
the old token. A failed resend leaves the previous valid link usable. Changing
the account address invalidates both its old proof and existing JWT access.

Requests are serialized using database row locks. Per-account limits are one
attempt per 60 seconds and five per rolling hour, including SMTP failures.
Registration/resend share an additional database-backed budget of 20 requests
per direct client IP per hour. Confirmation allows 120 requests per IP/hour.
Budgets survive worker changes/cache clearing. Existing login/register throttles
also apply. Responses are non-cacheable and confirmation URLs/tokens are not
included in application logs. SMTP failures log only the exception class and
leave the account pending; a later request can retry within the limits.

The frontend exposes resend on the login screen and `/verify-email`, including
when an old session is rejected. A wrong registration address can be corrected
by returning to registration. Existing passwords are never overwritten by a
registration attempt using an already registered address.

## Deployment and checks

Build both images, then deploy the same immutable revision with `deploy.ps1`.
Its maintenance sequence stops the app/scheduler before migration
`users.0003_email_verification`, then restarts both with the new code.
Deploying only the frontend or backend is insufficient. Existing Gmail SMTP and
Google OAuth Secrets are reused; no extra provider configuration is needed.
Existing sessions will require verification or a new trusted Google sign-in.

Backend tests cover activation, expiration, invalid input, replay, API/JWT gates,
resend limits, SMTP failures, email changes and provider verification. PostgreSQL
tests also cover simultaneous resends, confirmation and IP budget reservations.
Frontend integration tests cover pending registration, explicit confirmation,
URL cleanup, invalid links and resend without attaching or issuing JWTs.

After deployment, register a test account with an inbox you control. Confirm
that login/game actions are blocked, receive the real message, open its link,
click confirmation, then log in. Check reusing the link and resend, and check
the existing Google login. Delete only test data created for this check.

## Validation record, 2026-11-25

- The full SQLite backend suite ran 282 tests: 273 passed and nine requiring
  PostgreSQL were skipped. A final malformed-Unicode-token regression also passed.
- 79 focused tests passed on a separate PostgreSQL test database, including user
  authentication/OAuth, notifications, legacy game migrations and concurrency.
  Candidate code ran in an isolated temporary directory; production source and
  data were not migrated or replaced. The temporary directory/test DB were removed.
- All 22 frontend tests passed. Affected registration/verification integration
  tests were rerun after the final UI changes, and the production build passed.
- Django system/migration checks and `git diff --check` passed. Existing frontend
  lint findings remain three errors and three warnings; focused lint of the new
  components and changed login/registration/API files passed.
- Real mailbox activation through the public website awaits image publication,
  coordinated deployment and the operator's browser confirmation.

## Current limits

- Delivery is synchronous, as with existing game notifications. Generic response
  bodies do not promise indistinguishable SMTP-dependent response timings.
  A background mail outbox is a later improvement.
- IP budgets deliberately use the direct request peer rather than trusting
  arbitrary X-Forwarded-For headers. Behind nginx this can group users into a
  shared proxy budget. Trusted-proxy/client-IP handling needs a separate audited
  configuration before making those limits client-specific in production.
- Email verification proves mailbox access, not a unique human identity. Token
  economy/multi-account abuse controls are separate backlog items.

References: [OWASP email verification](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html),
[Google authoritative addresses](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).
