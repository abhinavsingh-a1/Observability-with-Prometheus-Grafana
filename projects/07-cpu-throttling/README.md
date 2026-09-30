# 07 · CPU Throttling

> **Is a container slow because the kernel keeps pausing it?**

| | |
|---|---|
| **Layer** | Container |
| **Method** | USE: **S**aturation |
| **Data source** | cAdvisor CFS metrics (`container_cpu_cfs_*`) |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` · k8s manifest `k8s/manifests/07-throttle.yaml` |
| **Time** | ~15 min |

## 1. Why this matters

CPU throttling is one of the most common **hidden** causes of latency in Kubernetes:

- The pod shows 40% average CPU, has no errors and no restarts, yet p99 latency is terrible.
- The reason is the Linux **CFS quota**. A limit of `0.5` CPU means 50 ms of CPU time per 100 ms period. A multi-threaded app (JVM GC threads, Go runtime, Node worker threads) can burn those 50 ms in the first 15 ms of the period. It is then **frozen for the remaining 85 ms**, and every request in flight waits.
- Averages hide this completely. Only the throttling counters show it.

## 2. How it works

Every 100 ms period the kernel records:

- `container_cpu_cfs_periods_total`: periods in which the container wanted CPU
- `container_cpu_cfs_throttled_periods_total`: periods in which it hit the quota and was paused
- `container_cpu_cfs_throttled_seconds_total`: total time spent paused

**Throttle ratio = throttled periods ÷ periods.** Above 25% is the common alert threshold (the same as the kube-prometheus `CPUThrottlingHigh` rule).

The demo app deliberately runs 2 busy threads when you call `/chaos/burn`, against a 0.5 CPU limit. Real requests to `orders-api` then have to wait for the next period.

## 3. Key metrics

| Metric | Meaning |
|---|---|
| `container_cpu_cfs_periods_total` | Enforcement periods |
| `container_cpu_cfs_throttled_periods_total` | Periods that hit the limit |
| `container_cpu_cfs_throttled_seconds_total` | Seconds spent paused |
| `container_spec_cpu_quota` / `_period` | The limit |

## 4. PromQL cookbook

```promql
# Throttle ratio per container
sum by (name) (rate(container_cpu_cfs_throttled_periods_total{name=~"lab-.+"}[5m]))
  / sum by (name) (rate(container_cpu_cfs_periods_total{name=~"lab-.+"}[5m]))

# Seconds paused per second (0.3 = paused 30% of wall-clock time)
sum by (name) (rate(container_cpu_cfs_throttled_seconds_total[5m]))

# Kubernetes
sum by (namespace, pod, container) (rate(container_cpu_cfs_throttled_periods_total{container!=""}[5m]))
  / sum by (namespace, pod, container) (rate(container_cpu_cfs_periods_total{container!=""}[5m]))
```

## 5. Alerts (`alerts.yml`)

| Alert | Condition | Severity |
|---|---|---|
| `ContainerCpuThrottlingHigh` | throttle ratio > 25% for 5m | warning |
| `ThrottlingHurtsLatency` | orders-api throttled > 25% **and** p95 > 300 ms | warning |

The second alert is a **correlation alert**. It combines a cause (throttling) and a symptom (latency) with `and on ()`, so the notification already names the root cause.

## 6. Dashboard

- **Bar gauges:** throttled % and CPU % of limit per container.
- **Graphs:** throttle ratio, throttled seconds, orders-api p95 latency, and orders-api CPU vs limit.

Put the p95 and throttling panels side by side and trigger `app`. The correlation is obvious.

## 7. Hands-on lab

```bash
./projects/07-cpu-throttling/trigger.sh hog     # a separate container, 0.2 CPU limit
./projects/07-cpu-throttling/trigger.sh app     # orders-api itself -> latency impact
./projects/07-cpu-throttling/trigger.sh reset
```

Kubernetes variant:

```bash
kubectl apply -f k8s/manifests/07-throttle.yaml   # LabPodCpuThrottling fires in ~6 min
kubectl delete -f k8s/manifests/07-throttle.yaml
```

## 8. Runbook

**ContainerCpuThrottlingHigh**

1. Check user impact: did latency (03) move at the same time? If not, it may be a batch job and acceptable.
2. **Options**, from simplest:
   - Raise the CPU limit.
   - Remove the CPU limit and keep only the request. Many teams do this for latency-sensitive services. Requests still guarantee the fair share.
   - Tune the runtime thread count (`-XX:ActiveProcessorCount`, `GOMAXPROCS` via automaxprocs, Node's `UV_THREADPOOL_SIZE`).
   - Reduce CPU work per request.
3. Re-check after the change that throttling is below 5–10%.

## 9. Production tips & pitfalls

- High throttling with **low average CPU** is normal for bursty apps. That's exactly the trap.
- Go and the JVM historically sized thread pools by *host* cores, not the container limit. That makes throttling worse.
- Kernels before 4.19/5.4 had a CFS bug that over-throttled. Upgrade old nodes.
- cgroup v2 exposes the same counters, and cAdvisor maps them to the same metric names.

## 10. Exercises

1. Change `orders-api` to `cpus: 1.0` in `docker-compose.yml`, re-run `trigger.sh app`, and compare.
2. Build a panel: "top 5 most throttled containers" (`topk(5, ...)`).
3. Why does `ThrottlingHurtsLatency` use `and on ()`? What happens without it?
