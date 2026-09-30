# 08 · Pod Restarts, CrashLoopBackOff & OOMKilled (Kubernetes)

> **Which pods are unstable, and why do they keep restarting?**

| | |
|---|---|
| **Layer** | Kubernetes workloads |
| **Method** | State monitoring (desired vs actual) |
| **Data source** | **kube-state-metrics** (`kube_pod_container_status_*`) |
| **Files** | `dashboard.json` · `trigger.sh` · rules in `k8s/lab-rules.yaml` (group `08-pod-restarts`) |
| **Prerequisite** | `./k8s/install.sh` (see `k8s/README.md`) |
| **Time** | ~20 min |

## 1. Why this matters

Kubernetes "self-heals" by restarting containers. That's great for availability and terrible for visibility. A pod can crash 500 times a day while `kubectl get deploy` still shows it as available. Restarts mean dropped requests, cold caches, and hidden bugs.

| State | Meaning | Typical cause |
|---|---|---|
| **CrashLoopBackOff** | Container keeps exiting; kubelet waits longer between restarts (10s → 5min) | Bad config, missing secret, failing dependency at startup, bug |
| **OOMKilled** | Killed for exceeding the memory limit (exit 137) | Leak, limit too low, runtime not container-aware |
| **ImagePullBackOff / ErrImagePull** | Image can't be pulled | Typo in tag, missing registry credentials, rate limits |
| **CreateContainerConfigError** | Referenced ConfigMap or Secret is missing | Deploy ordering, typo |

## 2. How it works

**kube-state-metrics (KSM)** watches the Kubernetes API and turns object *state* into metrics. It doesn't measure resource usage; that's cAdvisor. Metrics with a `reason` label are "info-style": value `1` for the current reason, otherwise `0` or absent.

## 3. Key metrics

| Metric | Meaning |
|---|---|
| `kube_pod_container_status_restarts_total` | Restart counter per container |
| `kube_pod_container_status_waiting_reason{reason}` | Why a container is waiting (CrashLoopBackOff, ImagePullBackOff...) |
| `kube_pod_container_status_last_terminated_reason{reason}` | Why it last died (OOMKilled, Error, Completed) |
| `kube_pod_container_status_ready` | Readiness probe passing |
| `container_memory_working_set_bytes` | Memory (cAdvisor), for OOM context |

## 4. PromQL cookbook

```promql
# Restarts in the last 15 minutes (increase handles the counter)
increase(kube_pod_container_status_restarts_total{namespace="lab"}[15m]) > 0

# Containers in CrashLoopBackOff right now
kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"} == 1

# Containers whose LAST death was an OOM kill AND that restarted recently
kube_pod_container_status_last_terminated_reason{reason="OOMKilled"} == 1
and on (namespace, pod, container)
increase(kube_pod_container_status_restarts_total[15m]) > 0

# Top 10 restarting containers cluster-wide in 24h
topk(10, increase(kube_pod_container_status_restarts_total[24h]))
```

`last_terminated_reason` stays `OOMKilled` until the container dies for another reason. Combining it with a recent restart prevents alerting forever on an old event.

## 5. Alerts (`k8s/lab-rules.yaml`, group `08-pod-restarts`)

| Alert | Condition | Severity |
|---|---|---|
| `LabPodCrashLooping` | waiting reason CrashLoopBackOff for 2m | critical |
| `LabPodRestartingOften` | > 3 restarts in 15m | warning |
| `LabContainerOOMKilled` | last reason OOMKilled + restarted in 15m | critical |
| `LabContainerWaiting` | ImagePull, ConfigError, etc. for 3m | warning |

kube-prometheus-stack ships production versions of these (`KubePodCrashLooping`, `KubeContainerWaiting`). Compare them in Prometheus → Alerts.

## 6. Dashboard (Grafana on :30000 → folder "Observability Lab")

- **Stats:** CrashLoopBackOff count, OOMKilled count, restarts in the last hour, and image pull problems.
- **Graphs:** restarts per container, waiting reasons (stacked), last termination reasons, and memory % of limit.

## 7. Hands-on lab

```bash
./projects/08-pod-restarts-crashloop/trigger.sh crashloop
./projects/08-pod-restarts-crashloop/trigger.sh oom
./projects/08-pod-restarts-crashloop/trigger.sh imagepull
kubectl -n lab get pods -w            # watch RESTARTS and STATUS columns
```

The investigation commands that go with every alert:

```bash
kubectl -n lab describe pod <pod>                 # Events + "Last State: Terminated, Reason: OOMKilled, Exit Code: 137"
kubectl -n lab logs <pod> --previous              # logs of the crashed run (the current run may be empty)
kubectl get events -n lab --sort-by=.lastTimestamp
```

Clean up with `./projects/08-pod-restarts-crashloop/trigger.sh reset`.

## 8. Runbook

**CrashLoopBackOff**

1. Run `kubectl logs --previous`. The answer is usually in the last 20 lines.
2. Check the exit code in `describe`:

   | Exit code | Meaning |
   |---|---|
   | 1 | Application error |
   | 137 | SIGKILL: OOM or liveness probe failure |
   | 143 | SIGTERM |

3. Did a ConfigMap, Secret, or image change recently? Roll back with `kubectl rollout undo`.
4. Is a liveness probe too aggressive (a slow start killed by the probe)? Add a `startupProbe`.

**OOMKilled:** see project 06's runbook (leak vs limit, container-aware runtime settings).

**ImagePullBackOff:** check the image name and tag, `imagePullSecrets`, and registry rate limits. `describe pod` shows the exact error.

## 9. Production tips & pitfalls

- Alert on restart **rate**, not the absolute counter. Counters grow forever.
- Jobs and CronJobs legitimately terminate. Exclude them or use `kube_job_status_failed` instead.
- Watch **liveness probe** misconfiguration. It causes restart loops that look like app bugs.

## 10. Exercises

1. Add a `startupProbe` to the crashloop demo. Does it change anything? Why not?
2. Write an alert for `kube_pod_container_status_ready == 0` for 5m on running pods.
3. Filter the dashboard to exclude pods owned by Jobs (hint: `kube_pod_owner{owner_kind="Job"}`).
