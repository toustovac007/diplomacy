# GameChat reconciliation regression

Run from `frontend`: `node --test tests/gameChatLifecycle.test.mjs`.

The test uses Node's built-in test runner, jsdom, the installed React DOM, and
the project's Vite/compiler configuration. It renders actual GameDetail,
GameChat, DrawProposalPanel, and GameHistory. API responses and authentication
are fixtures; GameMap's unrelated SVG loader is stubbed. No real game is resolved.
Lifecycle instrumentation is injected into the test bundle only.

## Evidence

Before the fix, GameChat and DrawProposalPanel were siblings with the identical
key `${game.id}:${currentPlayer.id}`. Duplicate sibling keys are invalid even
when component types differ. Reconciliation can overwrite the old chat's entry
when matching remaining children by key, leaving its DOM and effects behind.
Changes before these siblings (including the phase-keyed history component)
make this apparent; the source having one chat expression does not prevent it.

Fresh-process reproduction, with StrictMode and no HMR:

| Observation | Before | After |
| --- | --- | --- |
| Chat counts: initial, then 3 resolve-button clicks | 3, 7, 11, 15 | 1, 1, 1, 1 |
| Root container children | 1 | 1 |
| Duplicate-key warnings | 15 | 0 |
| Active 10s timers after transitions | 16 (15 chats + draw) | 2 (chat + draw) |
| Active 5s message timers | 1 | 1 |

GameDetail had only the expected StrictMode setup/cleanup/setup. Before the fix,
new chat setups accumulated without cleanup of each previously surviving
instance. Afterwards GameChat also had just the expected initial StrictMode
setup/cleanup/setup and no additional mounts across transitions.

The fix namespaces sibling keys as `chat:<game>:<player>` and
`draw:<game>:<player>`. Identity still changes with game/player, not phase.
One application root exists in main.jsx; one GameDetail route exists in App.jsx;
one GameChat mount expression exists in GameDetail. No root/bootstrap, router,
StrictMode, backend, or polling-interval changes were needed.

The guard clicks the real manual-resolve control and exercises its POST then
loadGame GET path using fixture responses. It asserts DOM counts, stable mounts,
one chat request and one message request per simulated polling tick, finished
read-only mode, route exit cleanup, and returning to the game.

## Verification limits

The tabbed interface assertions additionally cover the active/finished default
tab, hidden panels, keyboard navigation, conversation/draft preservation across
tab switches, lazy embedded history, unread badges without a second poller,
no mark-read while the chat panel is hidden, proposer-only cancellation versus
other voters' accept/reject buttons, and a waiting lobby without tabs.

This is an executed React DOM regression, not a live-browser/backend session.
The browser tool did not expose the user's authenticated game tabs. Live Vite
restart/HMR, real backend phase transitions, and independent browser tabs were
not verified. The fresh-process reproduction proves HMR is not required for
this defect. Existing tabs with orphaned DOM should be fully reloaded once
after receiving the fix; the key change prevents subsequent accumulation.
