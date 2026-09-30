# 09 · Deployment & Replica Health (Kubernetes)

> **Do workloads run the number of replicas we asked for, and are rollouts progressing?**

| | |
|---|---|
| **Layer** | Kubernetes controllers (Deployment, StatefulSet, DaemonSet, HPA) |
| **Method** | Desired state vs actual state |
| **Data source** | kube-state-metrics (`kube_deployment_*`, `kube_pod_status_*`, `kube_horizontalpodautoscaler_*`) |
| **Files** | `dashboard.json` · `trigger.sh` · rules in `k8s/lab-rules.yaml` (group `09-deployment-health`) |
| **Prerequisite** | `./k8s/install.sh` |
| **Time** | ~20 min |

## 1. Why this matters

Kubernetes is declarative: you say "3 replicas" and controllers try to make it true. Monitoring the **gap between desired and actual** catches:

- **Bad rollouts:** a new version never becomes ready (bad image, failing readiness, crash). Capacity silently drops to `replicas - maxUnavailable`.
- **Pending pods:** there's no node with enough CPU or memory, or taints, affinity, or PVC problems prevent scheduling. This is common after scaling up.
- **Autoscaler at max:** the HPA wants more pods but has hit `maxReplicas`. The next traffic spike will hurt.
- **Stuck controllers:** the spec changed but the controller hasn't reacted.

## 2. How it works

A Deployment reports its desired count (`spec.replicas`) and status counters (available, unavailable, updated). It also reports a **Progressing** condition, which flips to `False` with reason `ProgressDeadlineExceeded` if a rollout makes no progress within `progressDeadlineSeconds` (60s in the lab, 600s by default). kube-state-metrics exposes all of this.

## 3. Key metrics

| Metric | Meaning |
|---|---|
| `kube_deployment_spec_replicas` | Desired |
| `kube_deployment_status_replicas_available` | Ready for at least `minReadySeconds` |
| `kube_deployment_status_replicas_unavailable` | Missing |
| `kube_deployment_status_condition{condition,status}` | Progressing / Available conditions |
| `kube_deployment_metadata_generation` / `status_observed_generation` | Spec changes vs what the controller has seen |
| `kube_pod_status_phase{phase}` | Pending / Running / Succeeded / Failed / Unknown |
| `kube_pod_status_unschedulable` | Scheduler couldn't place the pod |
| `kube_horizontalpodautoscaler_status_current_replicas`, `_spec_max_replicas` | HPA headroom |
| `kube_statefulset_status_replicas_ready`, `kube_daemonset_status_number_unavailable` | Same idea for other controllers |

## 4. PromQL cookbook

```promql
# Deployments not at desired replicas
kube_deployment_spec_replicas != kube_deployment_status_replicas_available

# Rollouts that exceeded their progress deadline
kube_deployment_status_condition{condition="Progressing", status="false"} == 1

# Pending pods
sum by (namespace, pod) (kube_pod_status_phase{phase="Pending"}) == 1

# HPA at its ceiling
kube_horizontalpodautoscaler_status_current_replicas >= kube_horizontalpodautoscaler_spec_max_replicas

# StatefulSet / DaemonSet equivalents
kube_statefulset_status_replicas_ready != kube_statefulset_replicas
kube_daemonset_status_number_unavailable > 0
```

## 5. Alerts (`k8s/lab-rules.yaml`, group `09-deployment-health`)

| Alert | Condition | Severity |
|---|---|---|
| `LabDeploymentReplicasMismatch` | desired ≠ available for 3m | warning |
| `LabDeploymentRolloutStuck` | Progressing=false for 1m | critical |
| `LabDeploymentGenerationMismatch` | generation not observed for 10m | warning |
| `LabPodPending` | Pending for 3m | warning |
| `LabPodUnschedulable` | Unschedulable for 2m | warning |
| `LabHpaMaxedOut` | at max replicas for 15m | info |

## 6. Dashboard

- **Stats:** deployments missing replicas, stuck rollouts, pending pods, and unschedulable pods.
- **Graphs:** desired vs available replicas, unavailable replicas, pods by phase, and HPA current vs max.

## 7. Hands-on lab

```bash
./projects/09-deployment-health/trigger.sh deploy        # healthy: 3/3
./projects/09-deployment-health/trigger.sh bad-rollout   # broken image tag
kubectl -n lab rollout status deploy/web                 # "exceeded its progress deadline"
# -> LabDeploymentReplicasMismatch + LabDeploymentRolloutStuck
./projects/09-deployment-health/trigger.sh rollback      # recovers

./projects/09-deployment-health/trigger.sh pending       # 64-CPU request
kubectl -n lab describe pod -l app=too-big | grep -A3 Events   # "Insufficient cpu"
./projects/09-deployment-health/trigger.sh reset
```

`LabHpaMaxedOut` fires after 15 minutes of `deploy`, because the lab HPA sets min = max = 3 on purpose.

## 8. Runbook

**Rollout stuck / replicas mismatch**

1. Run `kubectl -n <ns> rollout status deploy/<name>` and `kubectl get rs -n <ns>`. Is the new ReplicaSet not becoming ready?
2. `describe` a new pod and check its events and container state (projects 08 and 06).
3. If users are affected, **roll back first** (`kubectl rollout undo`), then debug.

**Pending / Unschedulable**

1. Look for the `FailedScheduling` event in `describe pod`. The reason tells you everything: insufficient cpu or memory, taints, node affinity, or an unbound PVC.
2. Fix it: lower requests, add nodes (or check the cluster autoscaler), or fix selectors or tolerations.

**HPA maxed out:** raise `maxReplicas` or add capacity, and check whether the HPA target metric is sensible.

## 9. Production tips & pitfalls

- During normal rollouts, desired ≠ available for a short time. That's why the alert has `for: 3m`.
- Scale-to-zero deployments legitimately have 0 replicas. The mismatch alert handles this correctly (0 = 0).
- Pair these alerts with **deployment annotations** in Grafana, so graphs show exactly when a release happened.

## 10. Exercises

1. Break readiness instead of the image: `kubectl -n lab patch deploy web --type=json -p='[{"op":"replace","path":"/spec/template/spec/containers/0/readinessProbe/httpGet/path","value":"/nope"}]'`
2. Add a StatefulSet (for example `redis`) and an alert for `kube_statefulset_status_replicas_ready != kube_statefulset_replicas`.
3. Change the HPA to min 1 / max 5 and generate load to see it scale.
