#!/usr/bin/env bash
# Project 01 - Request Rate. Usage: ./trigger.sh drop|spike|reset
set -euo pipefail
cd "$(dirname "$0")/../.."
case "${1:-help}" in
  drop)   docker compose stop loadgen
          echo "loadgen stopped -> traffic ~0. TrafficDrop fires in ~4 min, NoTraffic in ~10 min." ;;
  spike)  docker rm -f lab-loadgen-spike >/dev/null 2>&1 || true
          docker compose run -d --rm --name lab-loadgen-spike -e RPS=40 loadgen >/dev/null
          echo "extra 40 rps started -> TrafficSpike fires in ~4 min." ;;
  reset)  docker rm -f lab-loadgen-spike >/dev/null 2>&1 || true
          docker compose start loadgen
          echo "traffic back to normal (10 rps)." ;;
  *)      echo "usage: $0 drop|spike|reset"; exit 1 ;;
esac
