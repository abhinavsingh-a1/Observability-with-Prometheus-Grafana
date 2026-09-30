# 14 · Message Queue: Kafka Consumer Lag

> **Are consumers keeping up with producers, and how late is our "async" work?**

| | |
|---|---|
| **Layer** | Dependencies (event streaming / queues) |
| **Method** | Saturation of consumers: lag, lag growth, time to drain |
| **Data source** | `kafka_exporter` (:9308) |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Prerequisite** | `make mq-on` (Kafka KRaft single node, exporter, producer and consumer) |
| **Time** | ~20 min |

## 1. Why this matters

Queues decouple services, and they also **hide failures**. When a consumer is slow or dead:

- Producers keep succeeding, so HTTP dashboards look perfect.
- Orders aren't processed, emails aren't sent, and payments aren't settled.
- Lag grows silently until the business notices ("my order has been pending for 3 hours"), or until messages expire past the topic retention and are **lost**.

Consumer lag is therefore the #1 queue metric. The real-world questions:

1. Is lag high?
2. Is it growing?
3. How long until we catch up?
4. Is anyone consuming at all?

## 2. How it works

```
mq-producer ──20 msg/s──▶ topic "orders" (3 partitions) ──▶ mq-consumer (group "order-processor")
                                   ▲
                          kafka_exporter asks the broker for:
                          latest offset per partition  vs  committed offset of each group
```

**Lag = latest offset − committed offset**, per partition. kafka_exporter also sums it per group and topic.

The consumer processes each message in `CONSUMER_PROCESS_MS` (default 5 ms, a capacity of about 200 msg/s). Making it 200 ms drops capacity to 5 msg/s, below the producer's 20 msg/s, so lag grows by about 15 messages per second.

## 3. Key metrics

| Metric | Meaning |
|---|---|
| `kafka_consumergroup_lag{consumergroup,topic,partition}` | Lag per partition |
| `kafka_consumergroup_lag_sum{consumergroup,topic}` | Total lag |
| `kafka_consumergroup_current_offset_sum` | Committed offsets; `rate()` gives the consume rate |
| `kafka_topic_partition_current_offset` | Latest offsets; `rate()` gives the produce rate |
| `kafka_consumergroup_members` | Active consumers in the group |
| `kafka_brokers` | Brokers in the cluster |

## 4. PromQL cookbook

```promql
# Lag per group/topic
sum by (consumergroup, topic) (kafka_consumergroup_lag_sum)

# Produce vs consume rate
sum by (topic) (rate(kafka_topic_partition_current_offset{topic!~"__.*"}[5m]))
sum by (topic) (rate(kafka_consumergroup_current_offset_sum[5m]))

# Is lag growing?
deriv(kafka_consumergroup_lag_sum[10m]) > 0

# Estimated seconds to drain (if producers stopped)
sum by (consumergroup, topic) (kafka_consumergroup_lag_sum)
/ sum by (consumergroup, topic) (rate(kafka_consumergroup_current_offset_sum[5m]))

# Hot partition (skewed keys or a stuck consumer instance)
topk(3, kafka_consumergroup_lag)
```

## 5. Alerts (`alerts.yml`)

| Alert | Condition | Severity |
|---|---|---|
| `KafkaConsumerLagHigh` | lag > 1000 for 2m | warning |
| `KafkaConsumerLagGrowing` | lag grew over 10m (and > 100), for 10m | warning |
| `KafkaConsumerGroupNoMembers` | 0 members but pending messages | critical |
| `KafkaTimeToDrainLong` | > 10 min to catch up | warning |
| `KafkaBrokerDown` | `kafka_brokers < 1` | critical |

Absolute lag thresholds are workload-specific: 1,000 messages may be 1 second for one topic and 1 hour for another. **Time to drain** and **lag growth** transfer better across topics.

## 6. Dashboard

- **Stats:** total lag, estimated time to drain, group members, and brokers.
- **Graphs:** lag by group and topic, lag per partition, produce vs consume rate, and members.

## 7. Hands-on lab

```bash
make mq-on                                           # ~1 min until messages flow
./projects/14-message-queue-lag/trigger.sh slow      # lag grows ~15/s
./projects/14-message-queue-lag/trigger.sh stop      # consumer gone
./projects/14-message-queue-lag/trigger.sh reset     # watch lag drain at ~180 msg/s
make mq-off
```

Useful CLI check, the same numbers the exporter reports:

```bash
docker exec lab-kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-processor
```

## 8. Runbook

**Lag high or growing**

1. Compare produce and consume rates:
   - Produce rate spiked → it's a traffic burst. Wait, or scale consumers.
   - Consume rate dropped → the consumers have a problem.
2. Consumer problems:
   - Check errors and latency of the downstream dependency (DB, API). This is usually the cause.
   - Check consumer CPU and memory (06, 07).
   - Look for rebalance storms in the consumer logs.
3. Scale consumers, **up to the partition count**. Extra consumers beyond that sit idle.
4. A single partition lagging points to a hot key or a stuck consumer instance.

**No members:** the consumer deployment is down or crash-looping (08). Restart it and check its logs.

## 9. Production tips & pitfalls

- Burrow, or the Strimzi/Confluent exporters, add lag **evaluation** (OK / WARN / STOP) and time-based lag.
- **RabbitMQ equivalents:** the built-in `rabbitmq_prometheus` plugin on :15692 exposes `rabbitmq_queue_messages_ready` (backlog, the "lag"), `rabbitmq_queue_messages_unacked`, `rabbitmq_queue_consumers`, and `rabbitmq_global_messages_delivered_total`. Alert on backlog > N and growing, and on `consumers == 0`.
- **SQS / cloud queues:** `ApproximateNumberOfMessagesVisible` and `ApproximateAgeOfOldestMessage` via the CloudWatch exporter. Message *age* is the best SLI.

## 10. Exercises

1. Scale consumers with `docker compose --profile mq up -d --scale mq-consumer=3` (remove `container_name` first). Does lag drain 3× faster? (It's capped by the 3 partitions.)
2. Add an alert: time to drain > 30 min, severity critical.
3. Add a panel with the lag of only the hottest partition (`topk(1, ...)`).
