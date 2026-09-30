# Kubernetes track (projects 06-k8s, 07-k8s, 08, 09)

Projects 08 and 09 only make sense on Kubernetes. This folder gives you a
disposable local cluster with the de-facto standard monitoring stack.

## What gets installed

| Component | Purpose |
|---|---|
| **kind** cluster `obs-lab` (1 control plane + 2 workers) | Kubernetes in Docker |
| **kube-prometheus-stack** (Helm) | Prometheus Operator, Prometheus, Alertmanager, Grafana, node-exporter, **kube-state-metrics** |
| `lab-rules.yaml` | `PrometheusRule` with the Lab* alerts for 06/07/08/09 |
| Dashboards 08 & 09 | ConfigMaps picked up by the Grafana sidecar |

Where the metrics come from:

- `kube_*` metrics come from **kube-state-metrics**. It reports the *desired and actual state* of Kubernetes objects: pods, deployments, HPAs.
- `container_*` metrics come from **cAdvisor inside the kubelet**. They report *resource usage*.

## Prerequisites

Docker, [kind](https://kind.sigs.k8s.io/), kubectl, and helm. Give Docker at least 4 CPUs and 6 GB RAM.

## Install / uninstall

```bash
./k8s/install.sh        # 3-6 minutes
./k8s/uninstall.sh      # deletes the whole cluster
```

| URL | Credentials |
|---|---|
| Grafana: http://localhost:30000 | admin / admin |
| Prometheus: http://localhost:30090 | none |

## Scenario manifests

| File | Breaks what | Project |
|---|---|---|
| `manifests/08-crashloop.yaml` | exits with code 1 → CrashLoopBackOff | 08 |
| `manifests/08-oomkill.yaml` | 150M in a 64Mi limit → OOMKilled | 08 (and 06-k8s) |
| `manifests/08-imagepull.yaml` | non-existent tag → ImagePullBackOff | 08 |
| `manifests/07-throttle.yaml` | 2 CPUs of work, 100m limit → throttling | 07-k8s |
| `manifests/09-web.yaml` | healthy 3-replica deployment + HPA | 09 |
| `manifests/09-pending.yaml` | requests 64 CPUs → Pending/Unschedulable | 09 |

Clean everything: `kubectl delete ns lab && kubectl apply -f k8s/manifests/00-namespace.yaml`

## Troubleshooting

- **Rules not visible in Prometheus → Alerts.** Run `kubectl -n monitoring get prometheusrules`, then check the operator logs: `kubectl -n monitoring logs deploy/monitoring-kube-prometheus-operator`.
- **Dashboards missing.** Run `kubectl -n monitoring get cm -l grafana_dashboard=1`, then re-run `./k8s/load-dashboards.sh`.
- **Port 30000 or 30090 already used.** Change the `hostPort` in `kind-config.yaml` and recreate the cluster.
