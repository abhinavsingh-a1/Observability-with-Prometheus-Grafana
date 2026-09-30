#!/usr/bin/env bash
# Publishes the Kubernetes-track dashboards as ConfigMaps. The Grafana sidecar
# (see values.yaml) imports every ConfigMap labelled grafana_dashboard=1.
set -euo pipefail
cd "$(dirname "$0")/.."
for p in 08-pod-restarts-crashloop 09-deployment-health; do
  kubectl -n monitoring create configmap "lab-dashboard-${p%%-*}" \
    --from-file="${p}.json=projects/${p}/dashboard.json" \
    --dry-run=client -o yaml \
  | kubectl label --local -f - grafana_dashboard=1 -o yaml \
  | kubectl annotate --local -f - grafana_folder="Observability Lab" -o yaml \
  | kubectl apply -f -
done
