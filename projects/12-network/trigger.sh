#!/usr/bin/env bash
# Project 12 - Network. Usage: ./trigger.sh traffic|reset
set -euo pipefail
case "${1:-help}" in
  traffic)
    docker network create lab-net-test >/dev/null 2>&1 || true
    docker rm -f lab-iperf-server lab-iperf-client >/dev/null 2>&1 || true
    docker run -d --rm --name lab-iperf-server --network lab-net-test networkstatic/iperf3 -s >/dev/null
    sleep 2
    docker run -d --rm --name lab-iperf-client --network lab-net-test networkstatic/iperf3 \
      -c lab-iperf-server -t 300 -b 800M >/dev/null
    echo "iperf3 800 Mbit/s for 5 min between two containers -> ContainerUnusualEgress (>50 MB/s) in ~3 min" ;;
  reset)
    docker rm -f lab-iperf-server lab-iperf-client >/dev/null 2>&1 || true
    docker network rm lab-net-test >/dev/null 2>&1 || true
    echo "stopped" ;;
  *) echo "usage: $0 traffic|reset"; exit 1 ;;
esac
