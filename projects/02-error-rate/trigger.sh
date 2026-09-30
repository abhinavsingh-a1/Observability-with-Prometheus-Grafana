#!/usr/bin/env bash
# Project 02 - Error Rate. Usage: ./trigger.sh warn|critical|reset [service]
set -euo pipefail
SVC="${2:-orders-api}"; PORT=$([ "$SVC" = payments-api ] && echo 8082 || echo 8081)
chaos() { curl -fsS -X POST "http://localhost:${PORT}/chaos?$1"; echo; }
case "${1:-help}" in
  warn)     chaos "error_rate=0.10"; echo "$SVC: 10% errors -> HighErrorRate in ~3 min" ;;
  critical) chaos "error_rate=0.35"; echo "$SVC: 35% errors -> VeryHighErrorRate in ~3 min" ;;
  reset)    curl -fsS -X POST "http://localhost:${PORT}/chaos/reset"; echo ;;
  *)        echo "usage: $0 warn|critical|reset [orders-api|payments-api]"; exit 1 ;;
esac
