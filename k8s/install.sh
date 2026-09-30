#!/usr/bin/env bash
# Creates the kind cluster, installs kube-prometheus-stack, the lab rules,
# the lab dashboards and the demo namespace.
set -euo pipefail
cd "$(dirname "$0")"

command -v kind >/dev/null    || { echo "Install kind:    https://kind.sigs.k8s.io/docs/user/quick-start/"; exit 1; }
command -v kubectl >/dev/null || { echo "Install kubectl: https://kubernetes.io/docs/tasks/tools/"; exit 1; }
command -v helm >/dev/null    || { echo "Install helm:    https://helm.sh/docs/intro/install/"; exit 1; }

if ! kind get clusters | grep -qx obs-lab; then
  echo "==> creating kind cluster obs-lab"
  kind create cluster --config kind-config.yaml
fi

echo "==> installing kube-prometheus-stack (takes 2-4 minutes)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace -f values.yaml --wait --timeout 10m

echo "==> lab namespace, rules and dashboards"
kubectl apply -f manifests/00-namespace.yaml
kubectl apply -f lab-rules.yaml
./load-dashboards.sh

cat <<MSG

Ready.
  Grafana     http://localhost:30000   (admin / admin)
  Prometheus  http://localhost:30090

Next: follow projects/08-pod-restarts-crashloop/README.md and projects/09-deployment-health/README.md
MSG
