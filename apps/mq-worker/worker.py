"""
Kafka producer / consumer used by project 14.

MODE=producer  RATE=20          messages per second to topic `orders`
MODE=consumer  PROCESS_MS=5     simulated processing time per message
                                (capacity = 1000 / PROCESS_MS msg/s)

Lag appears when producer rate > consumer capacity.
"""
import json
import os
import time

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable

BOOTSTRAP = os.getenv("BOOTSTRAP", "kafka:9092")
TOPIC = os.getenv("TOPIC", "orders")
GROUP = os.getenv("GROUP", "order-processor")


def connect(factory):
    while True:
        try:
            return factory()
        except NoBrokersAvailable:
            print("waiting for kafka ...")
            time.sleep(3)


def producer():
    rate = float(os.getenv("RATE", "20"))
    p = connect(lambda: KafkaProducer(bootstrap_servers=BOOTSTRAP,
                                      value_serializer=lambda v: json.dumps(v).encode()))
    print(f"producer: {rate} msg/s -> {TOPIC}")
    i = 0
    while True:
        p.send(TOPIC, {"order_id": i, "ts": time.time()})
        i += 1
        time.sleep(1 / rate)


def consumer():
    delay = float(os.getenv("PROCESS_MS", "5")) / 1000
    c = connect(lambda: KafkaConsumer(TOPIC, bootstrap_servers=BOOTSTRAP, group_id=GROUP,
                                      auto_offset_reset="earliest", enable_auto_commit=True,
                                      auto_commit_interval_ms=1000, max_poll_records=20))
    print(f"consumer: group={GROUP} {delay * 1000:.0f} ms/message")
    for _ in c:
        time.sleep(delay)


if __name__ == "__main__":
    producer() if os.getenv("MODE", "producer") == "producer" else consumer()
