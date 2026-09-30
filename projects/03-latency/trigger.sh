#!/usr/bin/env bash
# Project 03 - Latency. Usage: ./trigger.sh slow|very-slow|reset [service]
set -euo pipefail
SVC="${2:-orders-api}"; PORT=$([ "$SVC" = payments-api ] && echo 8082 || echo 8081)
case "${1:-help}" in
  slow)      curl -fsS -X POST "http://localhost:${PORT}/chaos?latency_ms=600"; echo
             echo "$SVC +600ms (jitter +-50%) -> HighLatencyP95 in ~4 min" ;;
  very-slow) curl -fsS -X POST "http://localhost:${PORT}/chaos?latency_ms=1500"; echo
             echo "$SVC +1500ms -> HighLatencyP99 + ManySlowRequests" ;;
  reset)     curl -fsS -X POST "http://localhost:${PORT}/chaos/reset"; echo ;;
  *)         echo "usage: $0 slow|very-slow|reset [orders-api|payments-api]"; exit 1 ;;
esac
