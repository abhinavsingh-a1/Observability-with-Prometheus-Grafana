#!/usr/bin/env bash
# Project 10 - Host CPU/memory. Usage: ./trigger.sh cpu|memory [percent]|reset
# WARNING: this really loads YOUR machine (or the Docker VM). cpu stops after 12 min, memory after 5 min.
set -euo pipefail
IMG=alpine:3.20
run() { docker rm -f lab-host-stress >/dev/null 2>&1 || true
        docker run -d --rm --name lab-host-stress "$IMG" sh -c "apk add -q --no-cache stress-ng >/dev/null && $1" >/dev/null; }
case "${1:-help}" in
  cpu)    run "stress-ng --cpu 0 --timeout 720s"
          echo "all cores busy for 12 min -> HostHighCpu fires after ~9 min (5m average must exceed 85%, then for: 5m)" ;;
  memory) PCT="${2:-90}"
          run "stress-ng --vm 1 --vm-bytes ${PCT}% --vm-keep --timeout 300s"
          echo "allocating ${PCT}% of available memory for 5 min -> HostMemoryLow (<15% available)" ;;
  reset)  docker rm -f lab-host-stress >/dev/null 2>&1 || true; echo "stopped" ;;
  *)      echo "usage: $0 cpu|memory [percent-of-available, default 90]|reset"; exit 1 ;;
esac
