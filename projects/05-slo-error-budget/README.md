# 05 · SLOs, Error Budgets & Burn-Rate Alerts

> **Are we reliable *enough*, and how fast are we spending our allowance for failure?**

| | |
|---|---|
| **Layer** | Service / business |
| **Method** | Google SRE: SLI → SLO → error budget → multi-window burn-rate alerts |
| **Data source** | Recording rules (`recording.yml`) built on `http_requests_total` and the latency histogram |
| **Files** | `recording.yml` · `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Time** | ~30 min (plus optional overnight run) |

## 1. Why this matters

Threshold alerts (project 02: "> 5% errors") have two problems:

- They page for short blips that don't matter.
- They stay silent for low-level errors that slowly ruin the month.

SLOs fix both by asking one question: **at this rate, will we break our promise?** This is how Google, most large SaaS companies, and increasingly every mature platform team do alerting.

| Term | In this lab |
|---|---|
| **SLI** (indicator) | Share of non-`/healthz` requests that are **not** 5xx |
| **SLO** (objective) | 99.9% over 30 days |
| **Error budget** | 0.1% of requests may fail, about 43 minutes of total outage per month |
| **Burn rate** | Error ratio ÷ 0.001. 1× means you use exactly the budget in 30 days; 14.4× means gone in about 2 days. |

A second SLO covers **latency**: 99% of requests faster than 500 ms.

## 2. How it works

`recording.yml` pre-computes the error ratio over **8 windows** (5m, 30m, 1h, 2h, 6h, 1d, 3d, 30d) every 30 seconds:

```
service:sli_errors:ratio_rate5m   ...   service:sli_errors:ratio_rate30d
service:sli_latency_bad:ratio_rate5m, ...1h
```

The naming convention is `level:metric:operation` (the Prometheus best practice).

`alerts.yml` then uses **multi-window, multi-burn-rate** alerts:

| Burn | Long window | Short window | Budget used | Severity |
|---|---|---|---|---|
| 14.4× | 1h | 5m | 2% | page |
| 6× | 6h | 30m | 5% | page |
| 3× | 1d | 2h | 10% | ticket |
| 1× | 3d | 6h | 10% | ticket |

- The **long window** proves the problem is significant, so blips don't page.
- The **short window** proves it's still happening, so the alert resolves quickly after a fix.

## 3. Key series

| Series | Meaning |
|---|---|
| `service:sli_errors:ratio_rate<window>` | Error ratio over the window |
| `service:sli_latency_bad:ratio_rate<window>` | Share of requests slower than 500 ms |
| `1 - service:sli_errors:ratio_rate30d` | Availability this month |
| `1 - ratio_rate30d / 0.001` | Error budget remaining (100% → 0%, can go negative) |

## 4. PromQL cookbook

```promql
# Current burn rate (1h)
service:sli_errors:ratio_rate1h / 0.001

# Budget remaining this month
1 - service:sli_errors:ratio_rate30d / 0.001

# Minutes of "full outage" left this month
(0.001 - service:sli_errors:ratio_rate30d) * 30 * 24 * 60

# Fast-burn condition, as used in the alert
service:sli_errors:ratio_rate1h > 14.4 * 0.001 and service:sli_errors:ratio_rate5m > 14.4 * 0.001
```

## 5. Alerts (`alerts.yml`)

| Alert | Fires when | Severity |
|---|---|---|
| `SLOErrorBudgetBurnFast` | 14.4× over 1h and 5m | critical |
| `SLOErrorBudgetBurnMedium` | 6× over 6h and 30m | critical |
| `SLOErrorBudgetBurnSlow` | 3× over 1d and 2h | warning |
| `SLOErrorBudgetBurnVerySlow` | 1× over 3d and 6h | warning |
| `SLOErrorBudgetExhausted` | 30d error ratio > 0.1% | warning |
| `SLOLatencyBudgetBurnFast` | latency SLO at 14.4× | critical |

## 6. Dashboard (default range: 6h)

- **Stats:** 30-day availability, budget remaining, 1h burn rate, and the latency SLI.
- **Graphs:** burn rates per window (with 6× and 14.4× lines), budget remaining over time, the availability SLI, and the latency SLI.

## 7. Hands-on lab

```bash
./projects/05-slo-error-budget/trigger.sh fast-burn
# t+0:  5m burn rate jumps to ~250x
# t+~6: 1h ratio crosses 1.44%, alert pending -> firing after 2m
./projects/05-slo-error-budget/trigger.sh reset
# the alert RESOLVES within minutes (the 5m window drops) even though the 1h window is still high

./projects/05-slo-error-budget/trigger.sh latency   # the latency SLO version
./projects/05-slo-error-budget/trigger.sh reset
```

Notice how much budget a single 10-minute incident consumes. That's the conversation SLOs enable: "we can afford about 4 such incidents per month".

Baseline: the demo apps fail 0.05% of requests on purpose (burn rate about 0.5×). That keeps the budget graph realistic.

## 8. Runbook

**Burn-rate alerts** are symptom alerts. Use projects 02, 03, and 06–15 to find the cause.

1. **Fast burn (page):** treat it as an incident. Mitigate first: roll back, fail over, or shed load.
2. **Slow burn (ticket):** there's no emergency, but schedule a fix this sprint.
3. **Budget exhausted:** apply your **error budget policy**. Typical policy: freeze feature releases and prioritise reliability work until the budget recovers.

## 9. Production tips & pitfalls

- Pick SLOs with product owners. 99.9% vs 99.99% is a business decision; each extra 9 costs roughly 10× effort.
- Low-traffic services make ratios noisy. Add a minimum-traffic condition or use synthetic probes (15).
- The 30-day window here needs 30 days of retention (`--storage.tsdb.retention.time=30d` is set).
- Tools such as **Sloth** or **Pyrra** generate these rules from a short SLO spec. Learn the raw version first (this project), then use a generator.

## 10. Exercises

1. Change the SLO to 99.5%. Which numbers in `alerts.yml` change? (Hint: every `0.001`.)
2. Add a `payments-api`-only SLO of 99.95% with its own recording rules.
3. Add a stat panel: "Minutes of outage left this month".
