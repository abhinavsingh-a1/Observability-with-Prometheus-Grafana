#!/usr/bin/env bash
# Project 07 - CPU throttling. Usage: ./trigger.sh hog|app|reset
set -euo pipefail
case "${1:-help}" in
  hog)   docker rm -f lab-cpu-hog >/dev/null 2>&1 || true
         docker run -d --rm --name lab-cpu-hog --cpus 0.2 polinux/stress stress --cpu 2 --timeout 600 >/dev/null
         echo "lab-cpu-hog: 2 busy threads with a 0.2 CPU limit -> ~100% throttled periods. Alert in ~8 min." ;;
  app)   curl -fsS -X POST "http://localhost:8081/chaos/burn?seconds=600"; echo
         echo "orders-api burns CPU above its 0.5 limit -> throttled -> real requests get slower (see p95 panel)." ;;
  reset) docker rm -f lab-cpu-hog >/dev/null 2>&1 || true
         curl -fsS -X POST "http://localhost:8081/chaos/reset" >/dev/null || true
         echo "stopped the CPU hog and the orders-api CPU burn." ;;
  *)     echo "usage: $0 hog|app|reset"; exit 1 ;;
esac
