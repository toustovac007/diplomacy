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

New GHCR packages can be private. Provide a namespace-scoped `ghcr-pull` Docker
registry Secret in Rancher if anonymous pulling is unavailable. Choose registry
`ghcr.io`, your GitHub username and a token with `read:packages`. Keep the token
out of source files and terminal command history. The manifests already refer
to `ghcr-pull`. Public images can be pulled without that Secret.

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
