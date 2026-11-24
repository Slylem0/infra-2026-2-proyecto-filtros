#!/usr/bin/env bash
# Habilita APIs, crea el registro Docker y configura alertas de presupuesto.
# Uso: exportar GCP_PROJECT_ID y, para las alertas, BILLING_ACCOUNT. Ejecutar ./bootstrap.sh.
set -euo pipefail

: "${GCP_PROJECT_ID:?Define GCP_PROJECT_ID}"
GCP_REGION=${GCP_REGION:-us-central1}
AR_REPO=${AR_REPO:-filtros}
PRESUPUESTO_USD=${PRESUPUESTO_USD:-150}

gcloud services enable container.googleapis.com artifactregistry.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com \
  billingbudgets.googleapis.com compute.googleapis.com --project="$GCP_PROJECT_ID"

repositorio=$(gcloud artifacts repositories list --project="$GCP_PROJECT_ID" \
  --location="$GCP_REGION" --filter="name ~ '/repositories/${AR_REPO}$'" --format='value(format)')
if [[ -z $repositorio ]]; then
  gcloud artifacts repositories create "$AR_REPO" --project="$GCP_PROJECT_ID" \
    --location="$GCP_REGION" --repository-format=docker
elif [[ $repositorio != DOCKER ]]; then
  printf 'El repositorio %s existe con un formato distinto de Docker.\n' "$AR_REPO" >&2
  exit 1
fi

if [[ -z ${BILLING_ACCOUNT:-} ]]; then
  printf 'Aviso: BILLING_ACCOUNT sin definir. Se omite el presupuesto.\n' >&2
  exit 0
fi

numero_proyecto=$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(projectNumber)')
[[ $numero_proyecto =~ ^[0-9]+$ ]] || { printf 'Número de proyecto inválido.\n' >&2; exit 1; }
nombre_presupuesto="filtros-${GCP_PROJECT_ID}"
filtro_proyecto="projects/${numero_proyecto}"
presupuesto=$(gcloud billing budgets list --project="$GCP_PROJECT_ID" \
  --billing-account="$BILLING_ACCOUNT" --flatten=budgetFilter.projects \
  --filter="displayName = '$nombre_presupuesto' AND budgetFilter.projects = '$filtro_proyecto'" \
  --format='value(name)')
if [[ -z $presupuesto ]]; then
  gcloud billing budgets create --project="$GCP_PROJECT_ID" \
    --billing-account="$BILLING_ACCOUNT" --display-name="$nombre_presupuesto" \
    --filter-projects="$filtro_proyecto" --budget-amount="${PRESUPUESTO_USD}USD" \
    --start-date="$(date -u +%F)" --credit-types-treatment=exclude-all-credits \
    --threshold-rule=percent=0.25 --threshold-rule=percent=0.50 \
    --threshold-rule=percent=0.75 --threshold-rule=percent=0.90
fi
