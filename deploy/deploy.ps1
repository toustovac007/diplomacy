[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Kubeconfig,
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$')]
    [string]$ImageTag
)

$ErrorActionPreference = 'Stop'
$Kubeconfig = (Resolve-Path -LiteralPath $Kubeconfig).Path
$ManifestDirectory = Join-Path $PSScriptRoot 'k8s'

function Invoke-Kube {
    & kubectl --kubeconfig $Kubeconfig --context student-cluster --namespace diplomacy @args
    if ($LASTEXITCODE -ne 0) { throw 'Kubernetes command failed. Inspect the output above.' }
}

function Apply-Manifest([string]$Name) {
    $manifest = Get-Content -Raw -Encoding utf8 -LiteralPath (Join-Path $ManifestDirectory $Name)
    $manifest = $manifest.Replace('ghcr.io/toustovac007/diplomacy-backend:master', "ghcr.io/toustovac007/diplomacy-backend:$ImageTag")
    $manifest = $manifest.Replace('ghcr.io/toustovac007/diplomacy-frontend:master', "ghcr.io/toustovac007/diplomacy-frontend:$ImageTag")
    $manifest | & kubectl --kubeconfig $Kubeconfig --context student-cluster --namespace diplomacy apply -f -
    if ($LASTEXITCODE -ne 0) { throw "Applying $Name failed." }
}

# Preserve credentials and database contents across repeat deployments.
$existingSecret = Invoke-Kube get secret diplomacy-secrets --ignore-not-found -o name
if (-not $existingSecret) {
    $secret = @{
        apiVersion = 'v1'
        kind = 'Secret'
        metadata = @{ name = 'diplomacy-secrets'; namespace = 'diplomacy' }
        type = 'Opaque'
        stringData = @{
            POSTGRES_PASSWORD = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
            DJANGO_SECRET_KEY = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(64))
        }
    }
    $secret | ConvertTo-Json -Depth 5 | & kubectl --kubeconfig $Kubeconfig --context student-cluster --namespace diplomacy create -f -
    if ($LASTEXITCODE -ne 0) { throw 'Creating application credentials failed.' }
    Remove-Variable secret
}

Apply-Manifest 'config.yaml'
Apply-Manifest 'postgres.yaml'
Invoke-Kube rollout status statefulset/diplomacy-postgres --timeout=300s

# Updates pause the scheduler and web application before schema migrations.
$existingCron = Invoke-Kube get cronjob diplomacy-deadlines --ignore-not-found -o name
if ($existingCron) {
    Invoke-Kube patch cronjob diplomacy-deadlines --type merge -p '{"spec":{"suspend":true}}'
    $jobs = Invoke-Kube get jobs -o json | ConvertFrom-Json
    foreach ($job in $jobs.items) {
        if ($job.status.active -gt 0 -and $job.metadata.ownerReferences.name -contains 'diplomacy-deadlines') {
            Invoke-Kube wait --for=condition=complete "job/$($job.metadata.name)" --timeout=330s
        }
    }
}
$existingApp = Invoke-Kube get deployment diplomacy --ignore-not-found -o name
if ($existingApp) {
    Invoke-Kube scale deployment diplomacy --replicas=0
    Invoke-Kube wait --for=delete pods -l app=diplomacy --timeout=120s
}

Invoke-Kube delete job diplomacy-migrate --ignore-not-found --wait=true
Apply-Manifest 'migrate.yaml'
Invoke-Kube wait --for=condition=complete job/diplomacy-migrate --timeout=330s
Apply-Manifest 'app.yaml'
# ConfigMap files mounted with subPath refresh when the Pod is recreated.
if ($existingApp) { Invoke-Kube rollout restart deployment/diplomacy }
Invoke-Kube rollout status deployment/diplomacy --timeout=300s
Apply-Manifest 'deadlines.yaml'
if ($existingCron) { Invoke-Kube patch cronjob diplomacy-deadlines --type merge -p '{"spec":{"suspend":false}}' }
Apply-Manifest 'ingress.yaml'
Invoke-Kube get pods,services,ingresses,pvc,cronjobs
Write-Host 'Application deployed. Verify HTTPS and the certificate at https://diplomacy.kube.sspu-opava.cz.'

