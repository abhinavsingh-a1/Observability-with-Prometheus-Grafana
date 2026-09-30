# 02 · Error Rate

> **What share of requests fail, and whose fault is it?**

| | |
|---|---|
| **Layer** | Application |
| **Method** | RED: **E**rrors |
| **Data source** | `http_requests_total{status}` and `payments_failed_total` |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Time** | ~15 min |

## 1. Why this matters

Error rate is the most direct measure of user pain. Almost every on-call rotation's first page is an error-rate alert.

The key skill is telling error types apart:

| Type | Meaning | Action |
|---|---|---|
| **5xx** | The server failed (bug, dependency down, timeout) | **Alert / page** |
| **4xx** | The client sent something wrong (404, 401, 400) | Watch trends; alert only on unusual ratios |
| **Business errors** | HTTP 200/402 but "payment declined" or "out of stock" | Separate business counters |

Always alert on a **ratio**, not a count. 10 errors per second is terrible at 20 rps and irrelevant at 100,000 rps.

## 2. How it works

The same counter as project 01, filtered by the `status` label. The demo app can inject failures:

```
POST /chaos?error_rate=0.3   -> 30% of /api/* requests return HTTP 500
```

`payments_failed_total{reason}` counts business failures (about 3% of payments are "declined" by design).

## 3. Key metrics

| Metric | Use |
|---|---|
| `http_requests_total{status=~"5.."}` | Server errors |
| `http_requests_total{status=~"4.."}` | Client errors |
| `payments_failed_total{reason}` | Business errors |
| `demo_chaos_setting{setting="error_rate"}` | Lab only: what is being injected |

## 4. PromQL cookbook

```promql
# 5xx ratio per service  (the most important query in this project)
  sum by (service) (rate(http_requests_total{status=~"5..",route!="/healthz"}[5m]))
/ sum by (service) (rate(http_requests_total{route!="/healthz"}[5m]))

# Which route is failing?
topk(5, sum by (service, route) (rate(http_requests_total{status=~"5.."}[5m])))

# All status codes (stacked graph)
sum by (status) (rate(http_requests_total[5m]))

# Business failures per minute by reason
sum by (reason) (rate(payments_failed_total[5m])) * 60
```

Pitfall: when traffic is 0, the ratio is `0/0 = NaN` and the series disappears. That's fine for alerting, but project 01's `NoTraffic` covers the "no requests at all" case.

## 5. Alerts (`alerts.yml`)

| Alert | Condition | for | Severity |
|---|---|---|---|
| `HighErrorRate` | 5xx ratio > 5% | 2m | warning |
| `VeryHighErrorRate` | 5xx ratio > 20% | 2m | critical |
| `HighClientErrorRate` | 4xx ratio > 40% | 10m | info |
| `PaymentFailuresHigh` | > 5 business failures/min | 5m | warning |

Alertmanager's `inhibit_rules` suppresses the warning when the critical alert fires for the same service, so on-call gets one notification, not two.

These are simple threshold alerts. Project 05 shows the more mature approach: **SLO burn-rate alerts**.

## 6. Dashboard

- **Top row:** 5xx ratio, 5xx/s, 4xx ratio, payment failures/min.
- **Graphs:** 5xx ratio by service (with threshold lines), 5xx by route, all status codes stacked, and payment failures by reason.
- **Lab panel:** the injected chaos error rate, so you can compare "injected" with "measured".

## 7. Hands-on lab

```bash
./projects/02-error-rate/trigger.sh warn          # orders-api 10% errors
./projects/02-error-rate/trigger.sh critical      # orders-api 35% errors
./projects/02-error-rate/trigger.sh warn payments-api
./projects/02-error-rate/trigger.sh reset
./projects/02-error-rate/trigger.sh reset payments-api
```

Watch the alert go *inactive → pending → firing*. When you trigger `critical`, the warning notification is inhibited. Check `docker logs -f lab-alert-logger`.

## 8. Runbook

**HighErrorRate / VeryHighErrorRate**

1. **Scope.** Is it one service or all of them? One route or all? (Use the dashboard's by-route panel.)
2. **Change.** Was there a deploy or config change in the last hour? If so, roll back first and investigate after.
3. **Dependencies.** Check the database (13), queue (14), and downstream services. One broken dependency usually shows up as 5xx on many routes.
4. **Saturation.** Check latency (03), CPU throttling (07), and memory (06). Overloaded services start timing out.
5. **Logs.** Filter logs by the failing route and time window. In production, link Grafana to Loki.

## 9. Production tips & pitfalls

- Count errors at the **edge** (ingress or load balancer) as well. An app that crashes can't count its own failures.
- Decide explicitly whether `429 Too Many Requests` and `499 Client Closed` are "errors".
- Timeouts at the client often never reach server metrics. That's another reason for probes (project 15).
- Use `for:` to avoid flapping, but keep it short for critical alerts.

## 10. Exercises

1. Make `HighErrorRate` ignore services with fewer than 1 rps (hint: `and sum by (service) (rate(...)) > 1`).
2. Add an alert for a single route with > 50% errors.
3. Route `severity=critical` to a second webhook receiver in `alertmanager/alertmanager.yml`.
