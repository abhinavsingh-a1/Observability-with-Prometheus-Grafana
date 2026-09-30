# 01 · Request Rate (Traffic)

> **How much traffic does each service receive, and is that normal?**

| | |
|---|---|
| **Layer** | Application |
| **Method** | RED: **R**ate |
| **Data source** | `http_requests_total` counter exposed by the app (`/metrics`) |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Time** | ~20 min (TrafficDrop needs 30 min of history first) |

## 1. Why this matters

Traffic is the first signal you look at during an incident. Its shape tells you what kind of problem you have:

- **A drop to near zero** almost never means "users went home". It means something *in front of* the service broke: DNS, the load balancer, an ingress, an expired certificate, or a bad deploy of the client app.
- **A sudden spike** means a marketing campaign, a retry storm (clients hammering a failing service), a bot, or a DDoS.
- **A slow trend** drives capacity planning.

Every other RED signal needs rate as its denominator. An error rate of 50% on 2 requests matters much less than 50% on 2,000.

## 2. How it works

```
loadgen ──HTTP──▶ orders-api / payments-api ──/metrics──▶ Prometheus ──▶ Grafana
                  counter: http_requests_total{service,method,route,status}
```

The app increments one **counter** per request. Prometheus stores the running total. PromQL's `rate()` turns that total into "requests per second". Counters survive scrapes being missed, and `rate()` handles process restarts (counter resets) automatically.

**Label design rule:** `route` is the **template** (`/api/orders/<int:order_id>`), never the raw URL. Raw URLs create one time series per order id, a *cardinality explosion* that can take Prometheus down.

## 3. Key metrics

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | counter | `service`, `method`, `route`, `status` |
| `orders_created_total` | counter | `service` (business throughput) |

## 4. PromQL cookbook

```promql
# Requests per second, per service
sum by (service) (rate(http_requests_total{route!="/healthz"}[5m]))

# Per endpoint
sum by (service, method, route) (rate(http_requests_total[5m]))

# By status class (2xx/4xx/5xx) - label_replace builds a new label from a regex
sum by (class) (label_replace(rate(http_requests_total[5m]), "class", "${1}xx", "status", "(.).."))

# Compare with the same time yesterday
sum(rate(http_requests_total[5m])) / sum(rate(http_requests_total[5m] offset 1d))

# Total requests in the last hour
sum(increase(http_requests_total[1h]))
```

Rules of thumb:

- Always `rate()` a counter before you `sum()` it. Never sum raw counters.
- The range (`[5m]`) should be at least 4× the scrape interval. In Grafana, use `$__rate_interval`.
- Exclude health checks (`route!="/healthz"`). Probes are not users.

## 5. Alerts (`alerts.yml`)

| Alert | Condition | Severity | Why this threshold |
|---|---|---|---|
| `TrafficDrop` | 2m rate < 50% of 30m average (and baseline > 1 rps) | warning | Relative thresholds work at any traffic level. The baseline guard avoids noise at night. |
| `TrafficSpike` | 2m rate > 2× 30m average (and > 5 rps) | warning | Early warning before saturation. |
| `NoTraffic` | rate == 0 for 5m | critical | Something upstream is certainly broken. |

In production, compare against `offset 1w` (same hour last week) to respect daily and weekly seasonality.

## 6. Dashboard

Grafana → folder **01-request-rate**. Panels:

- **Top row:** total RPS, requests in the last hour, now vs the 30m average, orders per minute.
- **Graphs:** by service, by route, by status class (stacked), and today vs yesterday.

## 7. Hands-on lab

```bash
make up                              # if not running yet
# wait ~30 minutes so the 30m baseline exists, then:
./projects/01-request-rate/trigger.sh spike    # +40 rps
./projects/01-request-rate/trigger.sh reset
./projects/01-request-rate/trigger.sh drop     # stop all traffic
./projects/01-request-rate/trigger.sh reset
```

Observe:

1. The dashboard's "Now vs 30m average" stat moves above 200% or below 50%.
2. Prometheus → **Alerts** (http://localhost:9090/alerts): the alert goes *pending*, then *firing*.
3. `docker logs -f lab-alert-logger` shows the notification.

## 8. Runbook

**TrafficDrop / NoTraffic**

1. Is the service itself up? Check `up{job="apps"}` and project 15's probes.
2. Did anything deploy in the last 30 minutes (service, ingress, client app)?
3. Check the load balancer or ingress metrics and DNS resolution.
4. Did the drop hit one route or all of them? One route points to a client-side bug.

**TrafficSpike**

1. Look at 5xx at the same time. Spike plus errors usually means a **retry storm** (clients retrying failures).
2. Check the top routes and, if logged, source IPs or user agents. Rate-limit if it's abuse.
3. Check saturation (projects 03, 06, 07). Scale out if it's legitimate.

## 9. Production tips & pitfalls

- **Cardinality.** Never put user IDs, raw paths, or query strings in labels.
- Use **recording rules** (`service:http_requests:rate5m`) when many dashboards run the same expensive query.
- `irate()` shows the last two samples. It's good for spiky zoomed-in graphs and bad for alerts. Use `rate()` for alerts.
- Traffic alone rarely pages anyone. It's context for other alerts.

## 10. Exercises

1. Change `TrafficDrop` to use `offset 1d` instead of the 30m average. What's the trade-off?
2. Add a panel for "top 5 routes by traffic" using `topk(5, ...)`.
3. Write a recording rule `service_route:http_requests:rate5m` and switch a panel to it.
