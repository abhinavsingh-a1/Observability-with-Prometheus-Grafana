# 10 · Host CPU, Memory & Load

> **Is the machine under all the containers healthy?**

| | |
|---|---|
| **Layer** | Infrastructure (host / VM / Kubernetes node) |
| **Method** | USE: Utilization, Saturation, Errors (Brendan Gregg) |
| **Data source** | node_exporter (`node_*`) |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Time** | ~20 min |

## 1. Why this matters

Every container shares the host's CPU, memory, disk, and network. When the host is saturated, *every* service on it degrades at once. That's the "everything is slow" incident. Host metrics answer:

- **Is it us or the machine?** One service slow points to the app. Everything slow points to the host.
- **Capacity:** do we need bigger or more nodes?
- **Noisy neighbours:** `steal` time on cloud VMs means another tenant is using "your" CPU.

The **USE method** asks three questions for every resource:

| | CPU | Memory |
|---|---|---|
| **Utilization** | % busy | % used (excluding cache) |
| **Saturation** | load average / cores, PSI | swapping, PSI, OOM kills |
| **Errors** | (rare) | OOM kills, ECC errors |

## 2. How it works

node_exporter reads `/proc` and `/sys` and exposes about 1,000 host metrics. In the lab it runs with `network_mode: host`, `pid: host`, and `/` mounted at `/host`, so it sees the real machine. Prometheus scrapes it through `host.docker.internal:9100`.

On **Docker Desktop** (Mac/Windows), "the host" is Docker's Linux VM. The numbers are real, but for that VM, not your laptop.

## 3. Key metrics

| Metric | Meaning |
|---|---|
| `node_cpu_seconds_total{cpu,mode}` | CPU time per core per mode (user, system, iowait, steal, idle...) |
| `node_load1/5/15` | Runnable + uninterruptible tasks (compare with the core count) |
| `node_memory_MemTotal_bytes`, `MemAvailable_bytes` | Total, and what can be allocated without swapping |
| `node_memory_SwapTotal_bytes` / `SwapFree_bytes` | Swap |
| `node_pressure_{cpu,memory,io}_waiting_seconds_total` | PSI: time stalled waiting for the resource |
| `node_vmstat_oom_kill` | Kernel OOM kills |
| `node_boot_time_seconds` | Reboot detection |

## 4. PromQL cookbook

```promql
# CPU utilization (all cores)
1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m]))

# Breakdown by mode (stacked graph)
avg by (instance, mode) (rate(node_cpu_seconds_total{mode!="idle"}[5m]))

# Memory utilization - use MemAvailable, NOT MemFree (Linux uses free RAM as cache)
1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes

# Load per core (>1 = more work than cores)
node_load5 / on (instance) count by (instance) (node_cpu_seconds_total{mode="idle"})

# PSI: share of time some task waited for memory
rate(node_pressure_memory_waiting_seconds_total[5m])

# Uptime
time() - node_boot_time_seconds
```

`count by (instance) (node_cpu_seconds_total{mode="idle"})` is the standard trick to get the **number of cores**: one idle series per core.

## 5. Alerts (`alerts.yml`)

| Alert | Condition | Severity |
|---|---|---|
| `HostHighCpu` | > 85% busy for 5m | warning |
| `HostHighIowait` | > 20% iowait for 10m | warning |
| `HostMemoryLow` | < 15% available for 2m (lab; production is often 10%) | warning |
| `HostHighLoad` | load5 > 2× cores for 10m | warning |
| `HostMemoryPressure` | PSI memory > 10% for 5m | warning |
| `HostOomKillDetected` | kernel OOM kill in 5m | warning |
| `HostRebooted` | uptime < 10 min | info |

## 6. Dashboard

- **Stats:** CPU %, memory %, load per core, and uptime.
- **Graphs:** CPU by mode (stacked), memory (used, available, cache, swap), load vs cores, PSI, and OOM kills.

## 7. Hands-on lab

This really loads your machine (CPU test: 12 minutes, memory test: 5 minutes). Close heavy apps first.

```bash
./projects/10-node-cpu-memory/trigger.sh cpu
./projects/10-node-cpu-memory/trigger.sh memory 90   # 90% of AVAILABLE memory
./projects/10-node-cpu-memory/trigger.sh reset
```

During the CPU test, look at project 03. Latency of the demo apps rises even though nothing changed in them. That's the host-saturation pattern.

## 8. Runbook

**HostHighCpu / HostHighLoad**

1. **Which mode?**

   | Mode | Points to |
   |---|---|
   | `user` | Application work |
   | `system` | Kernel work (network, syscalls) |
   | `iowait` | Disk (project 11) |
   | `steal` | The hypervisor is taking CPU (cloud neighbour) |

2. **Which process or container?** Check project 06's CPU panels, then `top` or `docker stats` on the host.
3. Is it expected (a batch job or deploy) or new? Scale, move workloads, or fix the hot code path.

**HostMemoryLow / MemoryPressure / OOM kill**

1. Find the biggest consumers (project 06 or `docker stats`).
2. Remember that `MemAvailable` already accounts for reclaimable cache. If it's low, the pressure is real.
3. Rising PSI memory stall means slowdown has already started. OOM kills come next.

## 9. Production tips & pitfalls

- **Load average** includes processes waiting on disk (D state) on Linux. High load with low CPU usually means I/O.
- On Kubernetes, node_exporter runs as a DaemonSet. kube-prometheus-stack includes it and its alerts (`NodeCPUHighUsage`, `NodeMemoryHighUtilization`...).
- PSI is the most accurate saturation signal available. It needs Linux 4.20+ and is enabled on most modern distributions.

## 10. Exercises

1. Add a `HostHighSteal` alert (steal > 10% for 10m).
2. Add a panel showing CPU per **core** (without `avg`). When does one hot core matter?
3. Compare `node_memory_MemFree_bytes` with `MemAvailable_bytes` on your machine. Why is "free" misleading?
