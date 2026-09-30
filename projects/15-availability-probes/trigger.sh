#!/usr/bin/env bash
# Project 15 - Availability. Usage: ./trigger.sh down|unhealthy|reset
set -euo pipefail
cd "$(dirname "$0")/../.."
case "${1:-help}" in
  down)      docker compose stop payments-api
             echo "payments-api stopped -> TargetDown (up==0) + EndpointDown (probe_success==0) in ~1-2 min" ;;
  unhealthy) curl -fsS -X POST "http://localhost:8081/chaos?healthy=false"; echo
             echo "orders-api /healthz returns 503 but /metrics still works -> only EndpointDown fires" ;;
  reset)     docker compose start payments-api
             curl -fsS -X POST "http://localhost:8081/chaos/reset" >/dev/null || true
             echo "back to normal" ;;
  *)         echo "usage: $0 down|unhealthy|reset"; exit 1 ;;
esac
