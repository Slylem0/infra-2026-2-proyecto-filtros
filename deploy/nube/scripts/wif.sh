#!/usr/bin/env bash
# Configura federación OIDC de GitHub Actions e imprime la configuración para gh.
# Uso: exportar GCP_PROJECT_ID, correr ./bootstrap.sh y luego ejecutar ./wif.sh.
set -euo pipefail

: "${GCP_PROJECT_ID:?Define GCP_PROJECT_ID}"
GCP_REGION=${GCP_REGION:-us-central1}
GCP_ZONE=${GCP_ZONE:-us-central1-a}
GKE_CLUSTER=${GKE_CLUSTER:-filtros}
AR_REPO=${AR_REPO:-filtros}
GITHUB_REPO=${GITHUB_REPO:-Slylem0/infra-2026-2-proyecto-filtros}

if [[ ! $GITHUB_REPO =~ ^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$ ]]; then
  printf 'GITHUB_REPO debe tener formato propietario/repositorio.\n' >&2
  exit 1
fi

numero_proyecto=$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(projectNumber)')
[[ $numero_proyecto =~ ^[0-9]+$ ]] || { printf 'Número de proyecto inválido.\n' >&2; exit 1; }
pool="projects/${numero_proyecto}/locations/global/workloadIdentityPools/github"
WIF_PROVIDER="$pool/providers/github"
GCP_SA="github-deployer@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
proyecto=(--project="$GCP_PROJECT_ID")
ubicacion=("${proyecto[@]}" --location=global)

existente=$(gcloud iam workload-identity-pools list "${ubicacion[@]}" \
  --filter="name = '$pool'" --format='value(name)')
if [[ -z $existente ]]; then
  gcloud iam workload-identity-pools create github "${ubicacion[@]}" --display-name='GitHub Actions'
fi

proveedor=("${ubicacion[@]}" --workload-identity-pool=github)
config_oidc=(
  --issuer-uri=https://token.actions.githubusercontent.com
  "--attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref"
  --attribute-condition="assertion.repository == \"$GITHUB_REPO\""
)
existente=$(gcloud iam workload-identity-pools providers list "${proveedor[@]}" \
  --filter="name = '$WIF_PROVIDER'" --format='value(name)')
if [[ -z $existente ]]; then
  gcloud iam workload-identity-pools providers create-oidc github "${proveedor[@]}" "${config_oidc[@]}"
else
  gcloud iam workload-identity-pools providers update-oidc github "${proveedor[@]}" "${config_oidc[@]}"
fi

existente=$(gcloud iam service-accounts list "${proyecto[@]}" \
  --filter="email = '$GCP_SA'" --format='value(email)')
if [[ -z $existente ]]; then
  gcloud iam service-accounts create github-deployer "${proyecto[@]}" --display-name='GitHub deployer'
fi

# IAM añade cada par rol/miembro como un conjunto, sin duplicarlo al repetir.
gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" "${proyecto[@]}" \
  --location="$GCP_REGION" --member="serviceAccount:$GCP_SA" --role=roles/artifactregistry.writer --condition=None
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member="serviceAccount:$GCP_SA" --role=roles/container.developer --condition=None
gcloud iam service-accounts add-iam-policy-binding "$GCP_SA" "${proyecto[@]}" \
  --member="principalSet://iam.googleapis.com/$pool/attribute.repository/$GITHUB_REPO" \
  --role=roles/iam.workloadIdentityUser --condition=None

printf '\nWIF_PROVIDER=%s\nGCP_SA=%s\n\n' "$WIF_PROVIDER" "$GCP_SA"
for nombre in WIF_PROVIDER GCP_SA; do
  printf 'gh secret set %s --repo %q --body %q\n' "$nombre" "$GITHUB_REPO" "${!nombre}"
done
for nombre in GCP_PROJECT_ID GCP_REGION GCP_ZONE GKE_CLUSTER AR_REPO GITHUB_REPO; do
  printf 'gh variable set %s --repo %q --body %q\n' "$nombre" "$GITHUB_REPO" "${!nombre}"
done
