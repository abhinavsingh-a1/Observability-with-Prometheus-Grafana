#!/usr/bin/env bash
# Project 14 - Kafka lag. Requires: make mq-on
# Usage: ./trigger.sh slow|stop|burst|reset
set -euo pipefail
cd "$(dirname "$0")/../.."
docker inspect lab-kafka >/dev/null 2>&1 || { echo "Run 'make mq-on' first."; exit 1; }
case "${1:-help}" in
  slow)  CONSUMER_PROCESS_MS=200 docker compose --profile mq up -d mq-consumer
         echo "consumer now 200 ms/msg (5 msg/s) vs producer 20 msg/s -> lag +15/s -> KafkaConsumerLagHigh in ~3 min" ;;
  stop)  docker compose --profile mq stop mq-consumer
         echo "no consumers -> KafkaConsumerGroupNoMembers + growing lag" ;;
  burst) PRODUCER_RATE=200 docker compose --profile mq up -d mq-producer
         echo "producer 200 msg/s vs consumer capacity ~200 msg/s -> lag on the edge. Try with 'slow' too." ;;
  reset) docker compose --profile mq up -d mq-producer mq-consumer
         echo "producer 20 msg/s, consumer 5 ms/msg -> lag drains (watch 'time to drain')" ;;
  *)     echo "usage: $0 slow|stop|burst|reset"; exit 1 ;;
esac
