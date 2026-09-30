# 06 · Container CPU & Memory vs Limits

> **How close is each container to being OOM-killed or throttled?**

| | |
|---|---|
| **Layer** | Container |
| **Method** | USE (utilization relative to the configured **limit**) |
| **Data source** | cAdvisor (`container_*`). On Kubernetes, the kubelet's cAdvisor plus kube-state-metrics. |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` · k8s rules in `k8s/lab-rules.yaml` |
| **Time** | ~15 min |

## 1. Why this matters

Containers run with limits (`mem_limit`, `cpus`, or Kubernetes `resources.limits`). The two limits fail very differently:

| Resource | What happens at the limit | Visible as |
|---|---|---|
| **Memory** | The kernel **kills** the process (OOMKilled, exit code 137) | Restarts, lost in-flight requests, 5xx |
| **CPU** | The kernel **pauses** the process until the next 100 ms period (throttling) | Latency. No errors, no restarts. |

Host-level metrics (project 10) can show a half-idle machine while one container is dying at its limit. **Percent of limit** is the number that matters.

## 2. How it works

cAdvisor reads cgroup statistics for every container and labels them with `name` (the container name). The lab names every container `lab-*`.

| Setting (docker-compose) | Metric |
|---|---|
| `mem_limit: 256m` | `container_spec_memory_limit_bytes` |
| `cpus: 0.5` | `container_spec_cpu_quota / container_spec_cpu_period` = 0.5 |

### Why `working_set` and not `usage`?

`container_memory_usage_bytes` includes page cache, which the kernel can reclaim. `container_memory_working_set_bytes` (usage minus inactive file cache) is what the **OOM killer and Kubernetes eviction** look at. Always alert on working_set.

## 3. Key metrics

| Metric | Meaning |
|---|---|
| `container_memory_working_set_bytes` | Memory that counts toward OOM |
| `container_spec_memory_limit_bytes` | Limit (0 = unlimited) |
| `container_cpu_usage_seconds_total` | CPU time; `rate()` gives cores |
| `container_spec_cpu_quota` / `_period` | CPU limit in cores |
| `container_start_time_seconds` | Changes when the container restarts |
| `container_oom_events_total` | OOM events (depends on cAdvisor version and config) |

## 4. PromQL cookbook

Docker / cAdvisor:

```promql
# Memory % of limit (containers without a limit are filtered by "> 0")
sum by (name) (container_memory_working_set_bytes{name=~"lab-.+"})
  / on (name) (sum by (name) (container_spec_memory_limit_bytes{name=~"lab-.+"}) > 0)

# CPU % of limit
sum by (name) (rate(container_cpu_usage_seconds_total{name=~"lab-.+"}[5m]))
  / on (name) (sum by (name) (container_spec_cpu_quota{name=~"lab-.+"})
               / sum by (name) (container_spec_cpu_period{name=~"lab-.+"}))

# Restarts
changes(container_start_time_seconds{name=~"lab-.+"}[15m])
```

Kubernetes (the limit comes from kube-state-metrics):

```promql
sum by (namespace, pod, container) (container_memory_working_set_bytes{container!="", container!="POD"})
  / on (namespace, pod, container)
sum by (namespace, pod, container) (kube_pod_container_resource_limits{resource="memory"})

sum by (namespace, pod, container) (rate(container_cpu_usage_seconds_total{container!=""}[5m]))
  / on (namespace, pod, container)
sum by (namespace, pod, container) (kube_pod_container_resource_limits{resource="cpu"})

# Requests vs actual usage (right-sizing / cost)
sum by (namespace) (kube_pod_container_resource_requests{resource="cpu"})
  - sum by (namespace) (rate(container_cpu_usage_seconds_total{container!=""}[5m]))
```

`sum by (...) / on (...)` makes both sides carry identical labels, so the division matches.

## 5. Alerts (`alerts.yml`)

| Alert | Condition | Severity |
|---|---|---|
| `ContainerMemoryNearLimit` | > 85% of limit for 2m | warning |
| `ContainerMemoryCritical` | > 95% of limit for 1m | critical |
| `ContainerCpuNearLimit` | > 90% of CPU limit for 5m | warning |
| `ContainerRestarted` | start time changed in 15m | warning |
| `ContainerOOMKilled` | OOM event counter increased | critical |

The Kubernetes variant (`LabPodMemoryNearLimit`) is in `k8s/lab-rules.yaml`.

## 6. Dashboard

- **Bar gauges:** memory % and CPU % of limit for every container. It's a one-glance "who is in danger" view.
- **Graphs:** working set with the limit line, CPU with the limit line, restarts, and OOM events.
- Use the **Container** dropdown to focus on one container.

## 7. Hands-on lab

```bash
./projects/06-container-resources/trigger.sh memory   # to ~88% -> warning
./projects/06-container-resources/trigger.sh reset

./projects/06-container-resources/trigger.sh oom      # past the limit -> killed
docker inspect lab-orders-api --format '{{.State.OOMKilled}} restarts={{.RestartCount}}'
./projects/06-container-resources/trigger.sh cpu      # CPU at limit
./projects/06-container-resources/trigger.sh reset
```

After the OOM, notice:

- The working-set line drops to near zero and restarts at baseline.
- `ContainerRestarted` fires.
- Project 04's `ProcessRestarted` fires as well.
- Project 01/02 dashboards show a short gap and errors.

Kubernetes version: `kubectl apply -f k8s/manifests/08-oomkill.yaml` (see project 08).

## 8. Runbook

**Memory near limit / OOMKilled**

1. Is it a leak (steady growth) or a spike (load-related)? Check the working set over 24h and project 04.
2. If it's a leak, profile and fix it. Restarts only buy time.
3. If it's legitimate growth, raise the limit **and** the request (on Kubernetes, request = limit for memory is common practice).
4. For JVM, Node, and Go, make the runtime **container-aware**: set heap to about 75% of the limit (`-XX:MaxRAMPercentage=75`, `--max-old-space-size`, `GOMEMLIMIT`).

**CPU near limit:** see project 07. The consequence is throttling.

## 9. Production tips & pitfalls

- A container without limits reports a limit of 0 or a huge number. The `> 0` filter prevents division nonsense.
- On Kubernetes, `container!=""` removes the pod-level cgroup series, and `container!="POD"` removes the pause container. Forget these and everything is double-counted.
- Also compare **usage vs requests**. Requests drive scheduling and cost, so over-requested pods waste money.

## 10. Exercises

1. Add `payments-api` to the OOM trigger via a parameter.
2. Create a panel: "memory headroom in MB" (limit minus working set) sorted with `bottomk`.
3. Write a k8s rule that finds pods using less than 20% of their CPU request for 24h (over-provisioned).
