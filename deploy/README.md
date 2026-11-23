# School Kubernetes deployment

Target cluster `student-cluster`, Rancher project `Flask`, namespace `diplomacy`.
Public origin `https://diplomacy.kube.sspu-opava.cz`.
The checked cluster uses `csi-rbd-sc`, Ingress class `nginx`, and certificate
issuer `letsencrypt-prod`. These values come from the live cluster on 2026-11-22.

## Architecture

The application Deployment runs the existing backend and frontend images in
one Pod, with one replica and `Recreate` updates. The two containers share the
media PVC, which uses ReadWriteOnce. nginx reaches Gunicorn on Pod loopback and
serves uploaded media read-only. PostgreSQL 18 runs in a separate StatefulSet
with a 2 GiB PVC mounted at `/var/lib/postgresql`.

The Kubernetes nginx ConfigMap replaces the image's Compose nginx configuration.
It preserves the Ingress HTTPS header for Django's secure redirect and cookies.
The existing Docker Compose workflow continues to use the original nginx file.

`docker_init.py` runs as a one-shot Job before the web Pod starts. It applies
migrations and seeds only an entirely empty map. A CronJob runs the existing
`process_deadlines` command every minute with concurrency forbidden. This also
handles deadline reminders. Schedule only this command for this deployment.

## Images

Push the deployment changes to `master`. The `Build deployment images` GitHub
Actions workflow builds both existing Dockerfiles and publishes
`ghcr.io/toustovac007/diplomacy-backend` and
`ghcr.io/toustovac007/diplomacy-frontend`, tagged with the full commit SHA and
`master`. Wait for both matrix jobs to succeed. Deploy the SHA tag so the web
Pod, migrations and scheduler all use the same backend revision.

Both published packages were verified to support anonymous pulls for this
deployment, so the manifests use public image pulls. If package visibility changes
to private, create a namespace-scoped Docker registry Secret in Rancher for
`ghcr.io` with a token scoped to `read:packages`, then reference it with
`imagePullSecrets` in the application, migration and deadline Pod templates.
Keep the token out of source files and terminal command history.

## First deployment

Run these commands from the repository root in PowerShell 7, after both images
are available. `namespace.yaml` was already created during preparation. For a
fresh cluster, create it in the designated Rancher project first.

```powershell
./deploy/deploy.ps1 -Kubeconfig 'C:\Users\Dell\Downloads\student-cluster.yaml' -ImageTag '<full-commit-sha>'
```

The script creates random application/DB credentials inside Kubernetes only
when the Secret is absent. An existing Secret is preserved on repeat runs.
It waits for PostgreSQL, waits for the migration Job, starts the application,
then enables the scheduler and applies the HTTPS Ingress. All commands use the
explicit cluster context and namespace. Existing local database contents are
not imported. Initial deployment starts with an empty database and new accounts.

TLS issuance can take a few minutes. Check the certificate before using accounts.

```powershell
kubectl --kubeconfig 'C:\Users\Dell\Downloads\student-cluster.yaml' -n diplomacy get certificate
kubectl --kubeconfig 'C:\Users\Dell\Downloads\student-cluster.yaml' -n diplomacy logs job/diplomacy-migrate
kubectl --kubeconfig 'C:\Users\Dell\Downloads\student-cluster.yaml' -n diplomacy logs deployment/diplomacy -c backend --tail=50
```

Visit `/`, `/login`, `/register`, `/maps/standard.svg`, `/admin/login/` and
`/api/users/me/`. An unauthenticated API request should return JSON 401. Check
registration/login, a private invitation, a two-player start, orders and chat.
Verify a deadline expires without manually invoking a management command.

Create an administrator interactively if needed.

```powershell
kubectl --kubeconfig 'C:\Users\Dell\Downloads\student-cluster.yaml' -n diplomacy exec -it deployment/diplomacy -c backend -- python manage.py createsuperuser
```

## Subsequent deployments and persistence

Use the same script with the new SHA after a successful image build. Updates
pause the scheduler and scale the app to zero before migrations, so they cause
a short outage. A migration/build failure stops the script. Inspect the failing
Job and resolve it before rerunning. StatefulSet/PVCs and credentials are retained.
Deleting the namespace or PVCs destroys the deployment's persistent data.

Before a schema update, take a DB dump from the PostgreSQL Pod and copy it out
with `kubectl cp`. Store backups outside the cluster and test restoration to a
separate database. Never overwrite an existing database during a deployment.

## Initial feature configuration

`DEBUG=false`, secure cookies, explicit allowed hosts/origins, and HTTPS are
enabled. Manual phase resolution is disabled. Email is initially disabled via
Django's dummy backend until SMTP credentials are supplied. Notifications handled
by that backend can be recorded as sent, and are not replayed when SMTP is enabled.
Google/GitHub OAuth remains unconfigured. Email/password registration and login
work independently. Configure production OAuth callbacks to the same public
origin when enabling providers.

The signing key, DB password, SMTP password, registry credentials and kubeconfig
belong in Secrets or local files outside Git. Kubernetes Secret access should be
limited to the project operators. The initial DB role has the same dedicated
database privileges as the existing Compose setup.

## Validation record, 2026-11-22

Deployed revision `7f7ca0ffaa3054f5bc6b5504f3a89029d3ea55c6`. Both GitHub Actions
image jobs succeeded after retrying the backend publication. The original GHCR
manifest push rejection was not reproduced on retry, and package access already
included the repository with Admin permission.

- Kubernetes server-side dry runs and `nginx -t` passed.
- PostgreSQL and media PVCs bound, schema migrations applied, and the reference
  map seeded with 7 countries, 75 provinces, 6 coasts and 428 directed adjacencies.
- The TLS certificate is Ready. Public HTTPS page routes, SVG map, Django admin
  and admin CSS returned 200. The unauthenticated user API returned JSON 401.
- Temporary API accounts verified registration/login, private UUID invitations,
  rejection of private numeric-ID joins, game start, HOLD orders, direct chat,
  readiness advancement and an expired phase processed by the scheduled CronJob.
  The temporary accounts and their game were deleted afterwards.
- The full backend suite ran 261 tests against a separate PostgreSQL test DB.
  256 passed initially. Five test methods had seven failing assertions because
  they expected manual resolution while the production environment disabled it.
  Those five methods passed when rerun with `ALLOW_MANUAL_PHASE_RESOLVE=true`
  in the test process. Production keeps manual resolution disabled.
- Django found no pending model migrations. Deployment checks reported existing
  warnings for an empty optional static directory and HSTS subdomain/preload
  options. HTTPS redirects, secure cookies and HSTS for this hostname are enabled.
- The deployment script's final resource-list argument was quoted for PowerShell.
  Unused private-registry Secret references were removed after public image
  pulls were verified.
- A second run of `deploy.ps1` completed successfully. Migrations preserved the
  existing map, and a temporary media file survived Pod recreation and was served
  through public nginx. The file was removed after the check. Final HTTPS checks
  returned 200 for the frontend and JSON 401 for the unauthenticated user API.
