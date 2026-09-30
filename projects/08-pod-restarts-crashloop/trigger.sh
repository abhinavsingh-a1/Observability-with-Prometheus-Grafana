#!/usr/bin/env bash
# Project 08 (Kubernetes). Usage: ./trigger.sh crashloop|oom|imagepull|all|reset
set -euo pipefail
M="$(dirname "$0")/../../k8s/manifests"
case "${1:-help}" in
  crashloop) kubectl apply -f "$M/08-crashloop.yaml" ;;
  oom)       kubectl apply -f "$M/08-oomkill.yaml" ;;
  imagepull) kubectl apply -f "$M/08-imagepull.yaml" ;;
  all)       kubectl apply -f "$M/08-crashloop.yaml" -f "$M/08-oomkill.yaml" -f "$M/08-imagepull.yaml" ;;
  reset)     kubectl delete --ignore-not-found -f "$M/08-crashloop.yaml" -f "$M/08-oomkill.yaml" -f "$M/08-imagepull.yaml" ;;
  *)         echo "usage: $0 crashloop|oom|imagepull|all|reset"; exit 1 ;;
esac
echo; echo "watch:  kubectl -n lab get pods -w"
