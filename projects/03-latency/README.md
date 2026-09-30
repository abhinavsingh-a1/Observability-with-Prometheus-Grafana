# 03 · Latency (p50 / p95 / p99)

> **How long do requests take, especially the slowest ones?**

| | |
|---|---|
| **Layer** | Application |
| **Method** | RED: **D**uration |
| **Data source** | `http_request_duration_seconds` histogram |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Time** | ~15 min |

## 1. Why this matters

Users rarely complain that something is broken. They say it's *slow*. Latency usually degrades **before** errors appear, because queues fill, then timeouts start, then 5xx follows.

**Why percentiles, not averages?** Take 99 requests at 50ms and 1 request at 10s. The average is about 150ms and looks fine. The p99 is 10s, and that one user left. A single page load often makes dozens of calls, so most users hit your p99 regularly.

| Percentile | Reads as |
|---|---|
| p50 (median) | The typical experience |
| p95 | 1 in 20 requests is slower than this. The usual SLO metric. |
| p99 | The tail. Shows GC pauses, lock contention, cold caches. |

## 2. How it works: histograms

The app records every request duration into **buckets**:

```
le="0.005" le="0.01" le="0.025" le="0.05" le="0.1" le="0.25" le="0.5" le="1" le="2.5" le="5" le="10" le="+Inf"
```

Each bucket is a counter of "requests ≤ that many seconds". `histogram_quantile()` estimates a percentile by interpolating between buckets.

- **Accuracy depends on the buckets.** Place boundaries around your SLO (here 0.25s, 0.5s, and 1s).
- Histograms from many instances can be **aggregated** (`sum by (le)`). Summaries (client-side quantiles) cannot, which is why histograms are the standard.

The files also expose `_sum` and `_count`. `_sum / _count` gives the average.

## 3. Key metrics

| Series | Meaning |
|---|---|
| `http_request_duration_seconds_bucket{le}` | Cumulative bucket counters |
| `http_request_duration_seconds_sum` | Total seconds spent |
| `http_request_duration_seconds_count` | Number of requests |
| `http_requests_in_flight` | Concurrency (gauge) |

## 4. PromQL cookbook

```promql
# p95 per service - ALWAYS keep `le` in the `by` clause
histogram_quantile(0.95,
  sum by (le, service) (rate(http_request_duration_seconds_bucket{route!="/healthz"}[5m])))

# p99 per route
histogram_quantile(0.99, sum by (le, service, route) (rate(http_request_duration_seconds_bucket[5m])))

# Average latency
sum(rate(http_request_duration_seconds_sum[5m])) / sum(rate(http_request_duration_seconds_count[5m]))

# Share of requests slower than 1s (exact from a bucket - no interpolation)
1 - sum(rate(http_request_duration_seconds_bucket{le=~"1(\\.0)?"}[5m]))
  / sum(rate(http_request_duration_seconds_count[5m]))

# Apdex with T = 250ms: (satisfied + tolerating/2) / total
( sum(rate(http_request_duration_seconds_bucket{le="0.25"}[5m]))
+ sum(rate(http_request_duration_seconds_bucket{le=~"1(\\.0)?"}[5m])) ) / 2
/ sum(rate(http_request_duration_seconds_count[5m]))
```

**`le="1"` vs `le="1.0"`:** Prometheus 3 normalises bucket labels to `1`, while Prometheus 2 kept the client's `1.0`. The regex `1(\\.0)?` works on both.

## 5. Alerts (`alerts.yml`)

| Alert | Condition | for | Severity |
|---|---|---|---|
| `HighLatencyP95` | p95 > 500ms | 3m | warning |
| `HighLatencyP99` | p99 > 1.5s | 3m | critical |
| `ManySlowRequests` | > 5% of requests slower than 1s | 5m | warning |

`ManySlowRequests` reads a bucket boundary directly, so it's **exact**. Percentile alerts are estimates. Many teams prefer the bucket form for alerting.

## 6. Dashboard

- **Top row:** p95, p99, average, and Apdex.
- **Graphs:** p50/p95/p99 per service, p95 per route, a **heatmap** of the full distribution, the share of requests slower than 1s, and in-flight requests.

The heatmap is the most revealing view. Two separate bands usually mean two populations, such as cache hits vs misses.

## 7. Hands-on lab

```bash
./projects/03-latency/trigger.sh slow        # +600 ms on orders-api
./projects/03-latency/trigger.sh very-slow   # +1500 ms
./projects/03-latency/trigger.sh reset
```

Things to notice:

- The average rises much less than p95 and p99.
- In-flight requests grow when latency grows, because the load generator keeps sending (Little's law: concurrency = rate × latency).
- Project 07 shows that CPU throttling also raises latency without any injected delay.

## 8. Runbook

**HighLatencyP95 / P99**

1. **Scope.** One route or all of them? One route points to a slow query or dependency.
2. **Saturation.** Check in-flight requests, CPU throttling (07), memory and GC (04), and host iowait (10).
3. **Dependencies.** Check DB long transactions and connection saturation (13), and queue lag (14).
4. **Traffic.** Is it a spike (01)? Scale out.
5. **Deploy.** Did a new version add a slow code path? Compare p95 by `version` if you expose it (`app_info`).

## 9. Production tips & pitfalls

- Never average percentiles (`avg(p95)` is meaningless). Aggregate the buckets first, then take the quantile.
- Measure at the client or edge too. Server time excludes the network and queueing in front of the app.
- Too many buckets × labels = cardinality. About 10–15 buckets is typical.
- **Native histograms** (Prometheus 2.40+, stable in 3.x) remove bucket choice entirely. Worth learning next.

## 10. Exercises

1. Add a `2` bucket to the app and an alert for "more than 1% slower than 2s".
2. Build a panel comparing p95 of `GET /api/orders` vs `POST /api/orders`.
3. Correlate: run `trigger.sh slow` and watch project 05's latency SLI drop.
