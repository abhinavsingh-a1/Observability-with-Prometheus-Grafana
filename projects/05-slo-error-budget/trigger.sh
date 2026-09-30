#!/usr/bin/env bash
# Project 05 - SLO burn rate. Usage: ./trigger.sh fast-burn|slow-burn|latency|reset
set -euo pipefail
post() { curl -fsS -X POST "http://localhost:8081$1"; echo; }
case "${1:-help}" in
  fast-burn) post "/chaos?error_rate=0.25"
             echo "25% errors = 250x burn rate. SLOErrorBudgetBurnFast fires in ~5-8 min (1h window must exceed 1.44%)." ;;
  slow-burn) post "/chaos?error_rate=0.008"
             echo "0.8% errors = 8x burn. Only the 6h/30m alert will fire - after hours. Good for an overnight run." ;;
  latency)   post "/chaos?latency_ms=900"
             echo "Latency SLO (99% < 500ms) burning fast -> SLOLatencyBudgetBurnFast" ;;
  reset)     post "/chaos/reset" ;;
  *)         echo "usage: $0 fast-burn|slow-burn|latency|reset"; exit 1 ;;
esac
