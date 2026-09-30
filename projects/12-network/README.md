# 12 · Network Throughput, Errors & TCP Health

> **Is the network moving data, and moving it cleanly?**

| | |
|---|---|
| **Layer** | Infrastructure (host) and container |
| **Method** | USE for network interfaces, plus TCP health |
| **Data source** | node_exporter (netdev, netstat, sockstat, conntrack) and cAdvisor (per-container traffic) |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Time** | ~15 min |

## 1. Why this matters

Network problems rarely show up as "network down". They show up as **latency and timeouts** in applications:

| Symptom | Real cause |
|---|---|
| Random slow requests, p99 spikes | Packet loss → TCP retransmits (each costs ≥ 200 ms) |
| New connections randomly fail under load | **conntrack table full** (a classic on Kubernetes nodes and NAT gateways) |
| "Connection refused", port exhaustion | Too many `TIME_WAIT` sockets from not reusing connections |
| Container suddenly uploading GB | Runaway job, backup misconfiguration, or data exfiltration |
| Interface errors | Bad NIC, cable, driver, or MTU mismatch (common with VPNs and overlay networks) |

## 2. How it works

- **Host level:** node_exporter reads `/proc/net/dev` (per-interface bytes, packets, errors, drops), `/proc/net/snmp` (TCP counters such as retransmits), sockstat, and the conntrack table size. It must run in the host network namespace (`network_mode: host`), otherwise it only sees its own container's interface.
- **Container level:** cAdvisor reports `container_network_*` per container.

Virtual interfaces (`veth*`, `docker0`, `br-*`, `cali*`...) are excluded from host totals so traffic isn't counted twice.

## 3. Key metrics

| Metric | Meaning |
|---|---|
| `node_network_receive_bytes_total` / `transmit_bytes_total` | Bytes per interface |
| `node_network_receive_errs_total` / `_drop_total` | Errors and drops (also for transmit) |
| `node_netstat_Tcp_RetransSegs`, `node_netstat_Tcp_OutSegs` | Retransmitted vs sent segments |
| `node_netstat_Tcp_CurrEstab` | Established TCP connections |
| `node_sockstat_TCP_tw` | Sockets in TIME_WAIT |
| `node_nf_conntrack_entries` / `_limit` | Connection tracking table |
| `container_network_receive_bytes_total` / `transmit_bytes_total` | Per-container traffic |

## 4. PromQL cookbook

```promql
# Bits per second per interface (x8 for bits - network people think in bits)
rate(node_network_receive_bytes_total{device!~"lo|veth.*|docker.*|br-.*"}[5m]) * 8

# Packet error ratio
(rate(node_network_receive_errs_total[5m]) + rate(node_network_transmit_errs_total[5m]))
/ (rate(node_network_receive_packets_total[5m]) + rate(node_network_transmit_packets_total[5m]))

# TCP retransmit ratio (> 1-2% is bad)
rate(node_netstat_Tcp_RetransSegs[5m]) / rate(node_netstat_Tcp_OutSegs[5m])

# Conntrack usage
node_nf_conntrack_entries / node_nf_conntrack_entries_limit

# Top talkers (containers)
topk(5, sum by (name) (rate(container_network_transmit_bytes_total[5m])))
```

Dashboard trick: graph **tx as negative** (`-rate(...)`). Receive and transmit then mirror each other around zero instead of overlapping.

## 5. Alerts (`alerts.yml`)

| Alert | Condition | Severity |
|---|---|---|
| `HostNetworkErrors` | > 1% of packets with errors for 5m | warning |
| `HostTcpRetransmitsHigh` | > 2% retransmits (with > 100 segments/s) for 5m | warning |
| `HostConntrackNearLimit` | > 80% of the conntrack table | critical |
| `ContainerUnusualEgress` | a container sends > 50 MB/s for 2m | warning |

## 6. Dashboard

- **Stats:** host rx, host tx, retransmit ratio, and conntrack usage.
- **Graphs:** traffic per interface (mirrored), errors and drops, TCP connection states, retransmit ratio, and per-container traffic.

## 7. Hands-on lab

```bash
./projects/12-network/trigger.sh traffic   # 800 Mbit/s between two containers for 5 min
./projects/12-network/trigger.sh reset
```

Traffic between two containers on one host goes through the Docker bridge. It shows up in the **container traffic** panel (`lab-iperf-*`) and fires `ContainerUnusualEgress`.

Packet loss is harder to simulate safely. On Linux you can use `tc` inside a container you own. For example, `docker run --cap-add NET_ADMIN ...` then `tc qdisc add dev eth0 root netem loss 5%` makes retransmits visible.

## 8. Runbook

**Retransmits high:** check whether it's one host or all. One host points to a NIC or cable problem; all hosts point to the network path or an overloaded switch or firewall. Look at interface errors and drops at the same time, and at MTU on overlay or VPN networks.

**Conntrack near limit:** check the count with `conntrack -C`. Short-term, raise `net.netfilter.nf_conntrack_max`. Long-term, reduce short-lived connections: keep-alive, connection pooling, and avoiding UDP DNS storms (NodeLocal DNSCache on Kubernetes).

**Unusual egress:** identify the container and its destination (`ss -tnp`, flow logs). If it's unexpected, isolate it first, then investigate.

## 9. Production tips & pitfalls

- Interface speed (`node_network_speed_bytes`) is `-1` or wrong on most virtual NICs. Don't rely on "% of link speed" in clouds.
- Cloud instances have **bandwidth and packets-per-second limits** that you only see in the provider's metrics.
- On Kubernetes, `container_network_*` is reported per **pod** (a shared network namespace). Aggregate by pod, not container.

## 10. Exercises

1. Add an alert for more than 20,000 `TIME_WAIT` sockets.
2. Build a "top 5 containers by egress" bar gauge with `topk`.
3. Use `tc netem` to add 5% loss to a test container and watch the retransmit panel.
