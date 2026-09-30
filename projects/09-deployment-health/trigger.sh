#!/usr/bin/env bash
# Project 09 (Kubernetes). Usage: ./trigger.sh deploy|bad-rollout|rollback|pending|reset
set -euo pipefail
M="$(dirname "$0")/../../k8s/manifests"
case "${1:-help}" in
  deploy)      kubectl apply -f "$M/09-web.yaml"; kubectl -n lab rollout status deploy/web ;;
  bad-rollout) kubectl -n lab set image deploy/web nginx=nginx:does-not-exist
               echo "new pods can't start; 1 old pod removed (maxUnavailable=1) -> replicas mismatch, rollout stuck after 60s" ;;
  rollback)    kubectl -n lab rollout undo deploy/web; kubectl -n lab rollout status deploy/web ;;
  pending)     kubectl apply -f "$M/09-pending.yaml" ;;
  reset)       kubectl delete --ignore-not-found -f "$M/09-pending.yaml" -f "$M/09-web.yaml" ;;
  *)           echo "usage: $0 deploy|bad-rollout|rollback|pending|reset"; exit 1 ;;
esac
