#!/usr/bin/env bash
# Project 06 - Container limits. Usage: ./trigger.sh memory|oom|cpu|reset
set -euo pipefail
leak() { curl -fsS -X POST "http://localhost:8081/chaos/leak?mb=$1" >/dev/null && echo "  +$1 MB"; }
case "${1:-help}" in
  memory) echo "leaking orders-api up to ~225 MB (88% of 256 MB) -> ContainerMemoryNearLimit"
          for i in $(seq 1 15); do leak 12; sleep 8; done ;;
  oom)    echo "leaking orders-api past 256 MB -> OOM kill -> Docker restarts it -> ContainerRestarted"
          for i in $(seq 1 30); do leak 15 || { echo "orders-api died (OOM) - it will be restarted"; break; }; sleep 3; done ;;
  cpu)    curl -fsS -X POST "http://localhost:8081/chaos/burn?seconds=720"; echo
          echo "orders-api uses >100% of its 0.5 CPU limit for 12 min -> ContainerCpuNearLimit in ~9 min" ;;
  reset)  curl -fsS -X POST "http://localhost:8081/chaos/reset" || true; echo ;;
  *)      echo "usage: $0 memory|oom|cpu|reset"; exit 1 ;;
esac
