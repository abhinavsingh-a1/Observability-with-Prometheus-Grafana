#!/usr/bin/env bash
# Project 04 - Runtime Health. Usage: ./trigger.sh leak|cpu|reset [service]
set -euo pipefail
SVC="${2:-orders-api}"; PORT=$([ "$SVC" = payments-api ] && echo 8082 || echo 8081)
case "${1:-help}" in
  leak)  echo "leaking 10 MB every 20s, 190 MB in total (RSS ~230 MB, just below the 256 MB limit). Ctrl+C to stop."
         for i in $(seq 1 19); do
           curl -fsS -X POST "http://localhost:${PORT}/chaos/leak?mb=10"; echo "  (step $i)"; sleep 20
         done ;;
  cpu)   curl -fsS -X POST "http://localhost:${PORT}/chaos/burn?seconds=720"; echo
         echo "burning CPU for 12 min -> ProcessHighCpu in ~9 min" ;;
  reset) curl -fsS -X POST "http://localhost:${PORT}/chaos/reset"; echo
         echo "leaked memory released (RSS may shrink slowly - Python keeps freed arenas)" ;;
  *)     echo "usage: $0 leak|cpu|reset [orders-api|payments-api]"; exit 1 ;;
esac
