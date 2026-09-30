# 04 · Runtime Health (process, memory, GC, file descriptors)

> **Is the process itself healthy, or slowly dying from a leak?**

| | |
|---|---|
| **Layer** | Application runtime |
| **Method** | USE for the process (utilization, saturation) |
| **Data source** | Default collectors of the Prometheus client library (`process_*`, `python_gc_*`) |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Time** | ~15 min |

## 1. Why this matters

RED metrics (01–03) tell you that users suffer. Runtime metrics often tell you **why**, and they warn you **hours before** a crash:

- **Memory leak:** RSS grows for hours, then the container is OOM-killed (project 06). Classic "it restarts every night".
- **GC pressure:** the runtime spends time collecting garbage instead of serving, and p99 latency spikes.
- **File descriptor leak:** unclosed sockets or files lead to "too many open files" and every new connection failing.
- **Unexpected restarts:** these hide bugs, because the service "looks fine" in a 5-minute window.

## 2. How it works

Every official Prometheus client library exposes runtime metrics **for free** when you mount `/metrics`. Names differ by language:

| Concern | Python (this lab) | Java / JVM (Micrometer or JMX exporter) | Go | Node.js (prom-client) |
|---|---|---|---|---|
| Memory | `process_resident_memory_bytes` | `jvm_memory_used_bytes{area="heap"}` | `go_memstats_heap_inuse_bytes` | `nodejs_heap_size_used_bytes` |
| GC | `python_gc_collections_total` | `jvm_gc_pause_seconds_*` | `go_gc_duration_seconds` | `nodejs_gc_duration_seconds` |
| Threads / concurrency | `http_requests_in_flight` (custom) | `jvm_threads_live_threads` | `go_goroutines` | `nodejs_eventloop_lag_seconds` |
| CPU | `process_cpu_seconds_total` | `process_cpu_usage` | `process_cpu_seconds_total` | `process_cpu_seconds_total` |
| File descriptors | `process_open_fds` / `process_max_fds` | same | same | same |
| Start time | `process_start_time_seconds` | same | same | same |

The PromQL and alerts below transfer directly. Only the metric names change.

## 3. Key metrics

| Metric | Type | Meaning |
|---|---|---|
| `process_resident_memory_bytes` | gauge | RAM actually used (RSS) |
| `process_cpu_seconds_total` | counter | CPU time used; `rate()` gives cores |
| `process_open_fds` / `process_max_fds` | gauge | File descriptor usage and limit |
| `process_start_time_seconds` | gauge | Unix time the process started |
| `python_gc_collections_total{generation}` | counter | GC runs per generation |
| `demo_leaked_bytes` | gauge | Lab only: injected leak size |

## 4. PromQL cookbook

```promql
# Memory per instance
process_resident_memory_bytes{job="apps"}

# Where will memory be in 1 hour? (linear regression over the last 15m)
predict_linear(process_resident_memory_bytes{job="apps"}[15m], 3600)

# Growth rate in bytes per second
deriv(process_resident_memory_bytes{job="apps"}[15m])

# CPU cores used
rate(process_cpu_seconds_total{job="apps"}[5m])

# FD usage ratio
process_open_fds / process_max_fds

# Uptime and restart detection
time() - process_start_time_seconds
changes(process_start_time_seconds[1h])
```

Two functions to know:

- **`predict_linear`** answers "when will it break?"
- **`deriv`** answers "is it growing at all?"

Used together, they catch leaks without false alarms on stable, high-memory services.

## 5. Alerts (`alerts.yml`)

| Alert | Condition | Severity |
|---|---|---|
| `ProcessMemoryHigh` | RSS > 200 MiB (limit 256 MiB) for 2m | warning |
| `ProcessMemoryLeakSuspected` | predicted RSS in 1h > 256 MiB **and** growing, for 5m | warning |
| `ProcessHighCpu` | > 0.4 cores (limit 0.5) for 5m | warning |
| `FileDescriptorsExhausting` | > 80% of max fds | critical |
| `ProcessRestarted` | start time changed in 15m | info |

## 6. Dashboard

- **Stats:** max RSS, max CPU, minimum uptime, and FD usage.
- **Graphs:** RSS with a +1h prediction line, CPU, GC collections per generation, open FDs, injected leak, and restarts.

## 7. Hands-on lab

```bash
./projects/04-runtime-health/trigger.sh leak    # ~6 min, adds 190 MB
# watch: RSS climbs in steps (to ~230 MB), the prediction line crosses 256 MB,
#        ProcessMemoryLeakSuspected then ProcessMemoryHigh fire
./projects/04-runtime-health/trigger.sh reset

./projects/04-runtime-health/trigger.sh cpu     # 12 min of CPU burn, alert after ~9 min
./projects/04-runtime-health/trigger.sh reset
```

If you want to see the OOM kill itself, continue in project 06.

## 8. Runbook

**Memory leak suspected / memory high**

1. Correlate the start of growth with a deploy (compare with the `app_info{version}` change).
2. Check whether growth follows traffic (normal caching) or time (a leak).
3. Take a heap profile: Java `jmap` or a heap dump; Go `pprof`; Node `--inspect` snapshots; Python `tracemalloc`.
4. Short term, restart or scale out. Long term, fix the leak. Don't just raise the limit.

**File descriptors exhausting:** run `ls /proc/<pid>/fd | wc -l` and `lsof -p <pid>`. Usually it's HTTP clients or DB connections not being closed or reused.

**Process restarted:** check container logs from the *previous* run and the exit code. Exit code 137 means OOM kill or SIGKILL.

## 9. Production tips & pitfalls

- For the JVM, watch **heap after GC** (the old gen floor), not raw heap usage. Heap always saw-tooths.
- Managed runtimes often don't return memory to the OS, so RSS can stay high after a leak is freed. That's normal.
- `process_*` metrics describe the process, not the container. Compare with cAdvisor (06) when they disagree.

## 10. Exercises

1. Add an alert: GC runs more than 50 times per second for 5m.
2. Change `ProcessMemoryLeakSuspected` to predict 4 hours ahead with a 1h window. What gets better, and what gets worse?
3. Add an "uptime < 10 min" panel per instance using `time() - process_start_time_seconds`.
