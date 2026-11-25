#!/usr/bin/env bash
# Crea, apaga o inspecciona el clúster zonal y sus recursos.
# Uso: exportar GCP_PROJECT_ID y ejecutar ./cluster.sh up|down|status [--yes].
set -euo pipefail

accion=${1:-}
if [[ ! $accion =~ ^(up|down|status)$ || $# -gt 2 || ( $# -eq 2 && $2 != --yes ) ]]; then
  printf 'Uso: %s up|down|status [--yes]\n' "$0" >&2
  exit 2
fi

: "${GCP_PROJECT_ID:?Define GCP_PROJECT_ID}"
GCP_ZONE=${GCP_ZONE:-us-central1-a}
GKE_CLUSTER=${GKE_CLUSTER:-filtros}
proyecto=(--project="$GCP_PROJECT_ID")
cluster=("$GKE_CLUSTER" "${proyecto[@]}" --zone="$GCP_ZONE")
etiquetas="labels.goog-k8s-cluster-name = '$GKE_CLUSTER' AND labels.goog-k8s-cluster-location = '$GCP_ZONE'"

confirmar() {
  if [[ ${2:-} == --yes ]]; then
    return 0
  fi
  local respuesta
  printf '%s [s/N] ' "$1" >&2
  read -r respuesta && [[ $respuesta == [sS] ]]
}

buscar_cluster() {
  gcloud container clusters list "${proyecto[@]}" \
    --filter="name = '$GKE_CLUSTER' AND location = '$GCP_ZONE'" --format='value(name)'
}

case "$accion" in
  up)
    existente=$(buscar_cluster)
    if [[ -z $existente ]]; then
      # Cada e2-standard-4 deja ~3.4 CPU disponibles tras la carga del sistema.
      # Solo cabe un trabajador de 2 CPU por nodo. Tres nodos alojan las tres
      # réplicas y dejan capacidad para el despachador.
      printf '%s\n' \
        'Referencia de costo en us-central1: ~0.42 USD/h (3 VM, 90 GB pd-standard y 3 IPv4 externas).' \
        'Gestión de GKE: +0.10 USD/h si el crédito mensual de gestión se agotó.' \
        'El costo varía por zona y consumo de red, registro y telemetría.'
      confirmar "¿Crear $GKE_CLUSTER en $GCP_ZONE?" "${2:-}" || exit 0
      gcloud container clusters create "${cluster[@]}" --num-nodes=3 \
        --machine-type=e2-standard-4 --disk-type=pd-standard --disk-size=30 \
        --workload-pool="${GCP_PROJECT_ID}.svc.id.goog" --logging=SYSTEM \
        --monitoring=SYSTEM --labels=proyecto=filtros --quiet
    fi
    gcloud container clusters get-credentials "${cluster[@]}"
    ;;
  down)
    existente=$(buscar_cluster)
    confirmar "¿Eliminar $GKE_CLUSTER en $GCP_ZONE y sus discos etiquetados sin uso?" "${2:-}" || exit 0
    if [[ -n $existente ]]; then
      gcloud container clusters delete "${cluster[@]}" --quiet
    fi

    discos=$(gcloud compute disks list "${proyecto[@]}" \
      --filter="$etiquetas AND NOT users:*" --format='value(selfLink)')
    printf 'Discos huérfanos de %s en %s:\n%s\n' "$GKE_CLUSTER" "$GCP_ZONE" "${discos:-Ninguno}"
    if [[ -n $discos ]]; then
      while IFS= read -r disco; do
        if [[ $disco =~ /zones/([^/]+)/disks/([^/]+)$ ]]; then
          gcloud compute disks delete "${BASH_REMATCH[2]}" "${proyecto[@]}" --zone="${BASH_REMATCH[1]}" --quiet
        elif [[ $disco =~ /regions/([^/]+)/disks/([^/]+)$ ]]; then
          gcloud compute disks delete "${BASH_REMATCH[2]}" "${proyecto[@]}" --region="${BASH_REMATCH[1]}" --quiet
        else
          printf 'No se pudo identificar la ubicación del disco %s.\n' "$disco" >&2
          exit 1
        fi
      done <<< "$discos"
    fi
    gcloud container clusters list "${proyecto[@]}"
    ;;
  status)
    gcloud container clusters list "${proyecto[@]}"
    gcloud compute instances list "${proyecto[@]}" --filter="$etiquetas AND labels.goog-gke-node:*"
    gcloud compute disks list "${proyecto[@]}" --filter="$etiquetas"
    ;;
esac
