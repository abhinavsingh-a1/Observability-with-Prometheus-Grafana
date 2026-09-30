#!/usr/bin/env python3
"""
Generates projects/*/dashboard.json for all 15 projects.

Why a generator? 15 dashboards share the same layout conventions (header,
alert counter, units, legends). Editing Python is far easier to review than
thousands of lines of JSON.

    python3 tools/build_dashboards.py        # regenerate every dashboard

You can still edit dashboards in the Grafana UI - export the JSON and drop it
into the project folder if you prefer hand-made ones.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DS = {"type": "prometheus", "uid": "prometheus"}


# ------------------------------------------------------------ panel helpers
def _targets(queries, fmt=None):
    out = []
    for i, q in enumerate(queries):
        expr, legend = (q, "") if isinstance(q, str) else q
        t = {"refId": chr(65 + i), "datasource": DS, "expr": expr, "legendFormat": legend}
        if fmt:
            t["format"] = fmt
        out.append(t)
    return out


def _thresholds(steps):
    return {"mode": "absolute",
            "steps": [{"color": c, "value": v} for v, c in steps]}


GYR = lambda warn, crit: [(None, "green"), (warn, "orange"), (crit, "red")]


def ts(title, queries, unit="short", desc="", w=12, h=8, stack=False,
       min=None, max=None, th=None, th_line=False):
    custom = {"lineWidth": 2, "fillOpacity": 25 if stack else 8, "showPoints": "never",
              "stacking": {"mode": "normal" if stack else "none"}}
    if th and th_line:
        custom["thresholdsStyle"] = {"mode": "line+area"}
    d = {"unit": unit, "custom": custom}
    if min is not None:
        d["min"] = min
    if max is not None:
        d["max"] = max
    if th:
        d["thresholds"] = _thresholds(th)
    return {"type": "timeseries", "title": title, "description": desc, "w": w, "h": h,
            "targets": _targets(queries), "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"legend": {"displayMode": "table", "placement": "bottom",
                                   "calcs": ["lastNotNull", "max"]},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def stat(title, expr, unit="short", desc="", w=6, h=4, th=None, legend="", decimals=None):
    d = {"unit": unit, "thresholds": _thresholds(th or [(None, "blue")]),
         "color": {"mode": "thresholds"}}
    if decimals is not None:
        d["decimals"] = decimals
    return {"type": "stat", "title": title, "description": desc, "w": w, "h": h,
            "targets": _targets([(expr, legend)]),
            "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "colorMode": "background", "graphMode": "area", "textMode": "auto"}}


def bar(title, queries, unit="percentunit", desc="", w=12, h=8, th=None, max=1):
    d = {"unit": unit, "min": 0, "thresholds": _thresholds(th or GYR(0.8, 0.9)),
         "color": {"mode": "thresholds"}}
    if max is not None:
        d["max"] = max
    return {"type": "bargauge", "title": title, "description": desc, "w": w, "h": h,
            "targets": _targets(queries), "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"orientation": "horizontal", "displayMode": "gradient",
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}}


def heatmap(title, expr, desc="", w=12, h=8):
    return {"type": "heatmap", "title": title, "description": desc, "w": w, "h": h,
            "targets": _targets([(expr, "{{le}}")], fmt="heatmap"),
            "fieldConfig": {"defaults": {}, "overrides": []},
            "options": {"calculate": False, "yAxis": {"unit": "s"},
                        "color": {"scheme": "Oranges", "mode": "scheme"},
                        "cellGap": 1, "tooltip": {"show": True, "yHistogram": True}}}


def timeline(title, queries, desc="", w=24, h=8):
    mappings = [{"type": "value", "options": {
        "0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}}}]
    return {"type": "state-timeline", "title": title, "description": desc, "w": w, "h": h,
            "targets": _targets(queries),
            "fieldConfig": {"defaults": {"mappings": mappings, "color": {"mode": "thresholds"},
                                         "thresholds": _thresholds([(None, "red"), (1, "green")])},
                            "overrides": []},
            "options": {"showValue": "never", "mergeValues": True, "rowHeight": 0.8}}


def text(md, w=18, h=4):
    return {"type": "text", "title": "", "w": w, "h": h,
            "options": {"mode": "markdown", "content": md}}


def var(name, label, query):
    return {"name": name, "label": label, "type": "query", "datasource": DS,
            "query": {"query": query, "refId": "v"}, "definition": query,
            "refresh": 2, "includeAll": True, "multi": True, "sort": 1,
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]}}


def dashboard(folder, title, about, panels, variables=(), time_from="now-30m"):
    num = folder.split("-")[0]
    header = [
        text(f"### {title}\n{about}\n\n📖 Full guide: `projects/{folder}/README.md`"),
        stat("Firing alerts (this project)",
             f'count(ALERTS{{alertstate="firing", project="{num}"}}) or vector(0)',
             th=[(None, "green"), (1, "red")],
             desc="Prometheus alerts from this project's alerts.yml that are firing right now."),
    ]
    x = y = row_h = 0
    out = []
    for i, p in enumerate(header + list(panels), start=1):
        w, h = p.pop("w"), p.pop("h")
        if x + w > 24:
            x, y, row_h = 0, y + row_h, 0
        p.update(id=i, gridPos={"x": x, "y": y, "w": w, "h": h}, datasource=DS)
        if p["type"] == "text":
            p.pop("datasource")
        out.append(p)
        x += w
        row_h = max(row_h, h)
    return {
        "uid": f"lab-{num}", "title": f"{num} · {title}", "tags": ["observability-lab", f"project-{num}"],
        "timezone": "browser", "schemaVersion": 39, "version": 1, "editable": True,
        "refresh": "10s", "time": {"from": time_from, "to": "now"},
        "templating": {"list": list(variables)}, "annotations": {"list": []}, "panels": out,
    }


# ------------------------------------------------------------ shared bits
S = 'service=~"$service"'
SVC_VAR = var("service", "Service", "label_values(http_requests_total, service)")
C = 'name=~"$container"'
CONT_VAR = var("container", "Container", 'label_values(container_memory_working_set_bytes{name=~"lab-.+"}, name)')
NS = 'namespace=~"$namespace"'
NS_VAR = var("namespace", "Namespace", "label_values(kube_pod_info, namespace)")
NOHEALTH = 'route!="/healthz"'
FS = 'fstype!~"tmpfs|overlay|squashfs|nsfs|fuse.*|ramfs"'
NIC = 'device!~"lo|veth.*|docker.*|br-.*|cali.*|flannel.*|cni.*"'
RI = "$__rate_interval"

D = {}

# ------------------------------------------------------------ 01 traffic
D["01-request-rate"] = dashboard("01-request-rate", "Request Rate (Traffic)",
    "How much traffic each service receives - the **R** in RED. Sudden drops usually mean an upstream outage; spikes mean load or abuse.",
    [
        stat("Total request rate", f"sum(rate(http_requests_total{{{S},{NOHEALTH}}}[{RI}]))", "reqps"),
        stat("Requests in the last hour", f"sum(increase(http_requests_total{{{S},{NOHEALTH}}}[1h]))", "short"),
        stat("Now vs 30m average", f"sum(rate(http_requests_total{{{S},{NOHEALTH}}}[2m])) / sum(rate(http_requests_total{{{S},{NOHEALTH}}}[30m]))",
             "percentunit", th=[(None, "red"), (0.5, "green"), (2, "orange")],
             desc="100% = normal. <50% fires TrafficDrop, >200% fires TrafficSpike."),
        stat("Orders created / min", f"sum(rate(orders_created_total{{{S}}}[5m])) * 60", "short", desc="Business throughput."),
        ts("Request rate by service", [(f"sum by (service) (rate(http_requests_total{{{S},{NOHEALTH}}}[{RI}]))", "{{service}}")], "reqps"),
        ts("Request rate by route", [(f"sum by (service, method, route) (rate(http_requests_total{{{S},{NOHEALTH}}}[{RI}]))", "{{service}} {{method}} {{route}}")], "reqps"),
        ts("Request rate by status class", [(f'sum by (class) (label_replace(rate(http_requests_total{{{S},{NOHEALTH}}}[{RI}]), "class", "${{1}}xx", "status", "(.).."))', "{{class}}")], "reqps", stack=True),
        ts("Today vs same time yesterday", [(f"sum(rate(http_requests_total{{{S},{NOHEALTH}}}[5m]))", "now"),
                                              (f"sum(rate(http_requests_total{{{S},{NOHEALTH}}}[5m] offset 1d))", "1 day ago")], "reqps",
           desc="Week-over-week / day-over-day comparison is how teams spot slow traffic trends."),
    ], [SVC_VAR])

# ------------------------------------------------------------ 02 errors
ERR = lambda by="", rng=RI: (f"sum{by} (rate(http_requests_total{{{S},{NOHEALTH},status=~\"5..\"}}[{rng}])) / "
                             f"sum{by} (rate(http_requests_total{{{S},{NOHEALTH}}}[{rng}]))")
D["02-error-rate"] = dashboard("02-error-rate", "Error Rate",
    "Share of requests that fail - the **E** in RED. 5xx = server's fault (alert on it). 4xx = client's fault (watch, rarely page).",
    [
        stat("5xx error ratio", ERR(), "percentunit", th=GYR(0.05, 0.2), decimals=2),
        stat("5xx per second", f'sum(rate(http_requests_total{{{S},status=~"5.."}}[{RI}]))', "reqps", th=GYR(0.5, 2)),
        stat("4xx ratio", f'sum(rate(http_requests_total{{{S},{NOHEALTH},status=~"4.."}}[{RI}])) / sum(rate(http_requests_total{{{S},{NOHEALTH}}}[{RI}]))',
             "percentunit", th=GYR(0.3, 0.5), decimals=1),
        stat("Payment failures / min", f"sum(rate(payments_failed_total{{{S}}}[5m])) * 60", "short",
             desc="Business errors: the HTTP call worked but the payment did not."),
        ts("5xx ratio by service", [(ERR(" by (service)"), "{{service}}")], "percentunit", min=0,
           th=GYR(0.05, 0.2), th_line=True, desc="Lines = alert thresholds (5% warning, 20% critical)."),
        ts("5xx per second by route", [(f'sum by (service, route) (rate(http_requests_total{{{S},status=~"5.."}}[{RI}]))', "{{service}} {{route}}")], "reqps"),
        ts("Responses by status code", [(f"sum by (status) (rate(http_requests_total{{{S},{NOHEALTH}}}[{RI}]))", "{{status}}")], "reqps", stack=True),
        ts("Payment failures by reason", [(f"sum by (reason) (rate(payments_failed_total{{{S}}}[{RI}]))", "{{reason}}")], "ops"),
        ts("Injected chaos error_rate", [(f'demo_chaos_setting{{{S},setting="error_rate"}}', "{{service}}")], "percentunit", w=24, h=6,
           desc="Lab only: what the chaos endpoint is currently injecting. Compare with the measured ratio above."),
    ], [SVC_VAR])

# ------------------------------------------------------------ 03 latency
Q = lambda q, by="service", rng=RI: (f"histogram_quantile({q}, sum by (le, {by}) "
                                     f"(rate(http_request_duration_seconds_bucket{{{S},{NOHEALTH}}}[{rng}])))")
D["03-latency"] = dashboard("03-latency", "Latency (p50 / p95 / p99)",
    "How long requests take - the **D** (duration) in RED. Always use percentiles: averages hide the slow tail your users feel.",
    [
        stat("p95 (all services)", f"histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{S},{NOHEALTH}}}[5m])))", "s", th=GYR(0.5, 1.5)),
        stat("p99 (all services)", f"histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{{{S},{NOHEALTH}}}[5m])))", "s", th=GYR(1, 2.5)),
        stat("Average", f"sum(rate(http_request_duration_seconds_sum{{{S},{NOHEALTH}}}[5m])) / sum(rate(http_request_duration_seconds_count{{{S},{NOHEALTH}}}[5m]))", "s", th=GYR(0.3, 1)),
        stat("Apdex (T=250ms)",
             f'(sum(rate(http_request_duration_seconds_bucket{{{S},{NOHEALTH},le="0.25"}}[5m])) + sum(rate(http_request_duration_seconds_bucket{{{S},{NOHEALTH},le=~"1(\\\\.0)?"}}[5m]))) / 2 / sum(rate(http_request_duration_seconds_count{{{S},{NOHEALTH}}}[5m]))',
             "percentunit", th=[(None, "red"), (0.7, "orange"), (0.9, "green")], decimals=2,
             desc="Satisfied (<250ms) + half of Tolerating (<1s) / total. 1.0 = perfect."),
        ts("p50 / p95 / p99 by service", [(Q(0.5), "p50 {{service}}"), (Q(0.95), "p95 {{service}}"), (Q(0.99), "p99 {{service}}")], "s",
           th=GYR(0.5, 1.5), th_line=True),
        ts("p95 by route", [(Q(0.95, "service, route"), "{{service}} {{route}}")], "s"),
        heatmap("Latency distribution (heatmap)", f"sum by (le) (increase(http_request_duration_seconds_bucket{{{S},{NOHEALTH}}}[{RI}]))",
                desc="Each column is a histogram. Bimodal patterns (two bands) often mean cache hit vs miss."),
        ts("Share of requests slower than 1s",
           [(f'1 - (sum by (service) (rate(http_request_duration_seconds_bucket{{{S},{NOHEALTH},le=~"1(\\\\.0)?"}}[{RI}])) / sum by (service) (rate(http_request_duration_seconds_count{{{S},{NOHEALTH}}}[{RI}])))', "{{service}}")],
           "percentunit", min=0),
        ts("In-flight requests", [(f"sum by (service) (http_requests_in_flight{{{S}}})", "{{service}}")], "short", w=24, h=6,
           desc="Concurrency. Rising in-flight + rising latency = saturation (Little's law)."),
    ], [SVC_VAR])

# ------------------------------------------------------------ 04 runtime
APP = 'job="apps"'
D["04-runtime-health"] = dashboard("04-runtime-health", "Runtime Health (process / GC / memory)",
    "What happens *inside* the process: memory, CPU, file descriptors, garbage collection. Catches leaks and resource exhaustion before they become outages.",
    [
        stat("Resident memory (max)", f"max(process_resident_memory_bytes{{{APP}}})", "bytes", th=GYR(150e6, 200e6)),
        stat("CPU (max, cores)", f"max(rate(process_cpu_seconds_total{{{APP}}}[5m]))", "short", th=GYR(0.3, 0.45), decimals=2),
        stat("Min uptime", f"min(time() - process_start_time_seconds{{{APP}}})", "s", th=[(None, "red"), (600, "green")],
             desc="Low value = something restarted recently."),
        stat("FD usage (max)", f"max(process_open_fds{{{APP}}} / process_max_fds{{{APP}}})", "percentunit", th=GYR(0.6, 0.8)),
        ts("Resident memory (RSS)", [(f"process_resident_memory_bytes{{{APP}}}", "{{instance}}"),
                                     (f"predict_linear(process_resident_memory_bytes{{{APP}}}[15m], 3600)", "{{instance}} predicted +1h")],
           "bytes", th=GYR(200e6, 256e6), th_line=True, desc="Container limit is 256 MB. A steadily rising line that never drops = leak."),
        ts("CPU usage (cores)", [(f"rate(process_cpu_seconds_total{{{APP}}}[{RI}])", "{{instance}}")], "short", th=GYR(0.4, 0.5), th_line=True),
        ts("GC collections / s by generation", [(f"sum by (instance, generation) (rate(python_gc_collections_total{{{APP}}}[{RI}]))", "{{instance}} gen{{generation}}")], "ops",
           desc="JVM equivalent: jvm_gc_pause_seconds; Go: go_gc_duration_seconds; Node: nodejs_gc_duration_seconds."),
        ts("Open file descriptors", [(f"process_open_fds{{{APP}}}", "{{instance}}")], "short"),
        ts("Leaked memory (chaos)", [(f"demo_leaked_bytes", "{{service}}")], "bytes"),
        ts("Process restarts (last 1h)", [(f"changes(process_start_time_seconds{{{APP}}}[1h])", "{{instance}}")], "short"),
    ])

# ------------------------------------------------------------ 05 SLO
D["05-slo-error-budget"] = dashboard("05-slo-error-budget", "SLO & Error Budget",
    "Availability SLO **99.9 %** over 30 days (≈ 43 min of 'allowed failure'). Burn rate = how fast we spend that budget. 1× = exactly on budget.",
    [
        stat("Availability (30d)", '1 - max(service:sli_errors:ratio_rate30d{service=~"$service"})', "percentunit",
             th=[(None, "red"), (0.999, "green")], decimals=3),
        stat("Error budget remaining", 'min(1 - service:sli_errors:ratio_rate30d{service=~"$service"} / 0.001)', "percentunit",
             th=[(None, "red"), (0.25, "orange"), (0.5, "green")], decimals=1),
        stat("Burn rate (1h)", 'max(service:sli_errors:ratio_rate1h{service=~"$service"}) / 0.001', "short",
             th=[(None, "green"), (1, "orange"), (6, "red")], decimals=1, desc="x times faster than sustainable."),
        stat("Latency SLI: <500ms (1h)", '1 - max(service:sli_latency_bad:ratio_rate1h{service=~"$service"})', "percentunit",
             th=[(None, "red"), (0.99, "green")], decimals=2, desc="Latency SLO: 99% of requests faster than 500 ms."),
        ts("Burn rate by window", [('service:sli_errors:ratio_rate5m{service=~"$service"} / 0.001', "5m {{service}}"),
                                   ('service:sli_errors:ratio_rate1h{service=~"$service"} / 0.001', "1h {{service}}"),
                                   ('service:sli_errors:ratio_rate6h{service=~"$service"} / 0.001', "6h {{service}}")],
           "short", th=[(None, "green"), (6, "orange"), (14.4, "red")], th_line=True,
           desc="Page when BOTH 1h and 5m > 14.4 (2% of monthly budget in 1 hour)."),
        ts("Error budget remaining (30d)", [('1 - service:sli_errors:ratio_rate30d{service=~"$service"} / 0.001', "{{service}}")],
           "percentunit", max=1, th=[(None, "red"), (0.25, "orange"), (0.5, "green")], th_line=True),
        ts("Availability SLI (5m)", [('1 - service:sli_errors:ratio_rate5m{service=~"$service"}', "{{service}}")], "percentunit",
           th=[(None, "red"), (0.999, "green")], th_line=True),
        ts("Latency SLI (share of requests < 500ms)", [('1 - service:sli_latency_bad:ratio_rate5m{service=~"$service"}', "{{service}}")],
           "percentunit", th=[(None, "red"), (0.99, "green")], th_line=True),
    ], [var("service", "Service", "label_values(service:sli_errors:ratio_rate5m, service)")], time_from="now-6h")

# ------------------------------------------------------------ 06 container limits
MEMP = f"sum by (name) (container_memory_working_set_bytes{{{C}}}) / on (name) (sum by (name) (container_spec_memory_limit_bytes{{{C}}}) > 0)"
CPUP = (f"sum by (name) (rate(container_cpu_usage_seconds_total{{{C}}}[{RI}])) / on (name) "
        f"(sum by (name) (container_spec_cpu_quota{{{C}}}) / sum by (name) (container_spec_cpu_period{{{C}}}))")
D["06-container-resources"] = dashboard("06-container-resources", "Container CPU & Memory vs Limits",
    "How close each container is to its limits. Memory at 100% of limit = OOM kill. CPU at 100% of limit = throttling (project 07).",
    [
        bar("Memory used % of limit", [(MEMP, "{{name}}")], th=GYR(0.85, 0.95)),
        bar("CPU used % of limit", [(CPUP, "{{name}}")], th=GYR(0.8, 0.95), max=None),
        ts("Memory working set", [(f"sum by (name) (container_memory_working_set_bytes{{{C}}})", "{{name}}"),
                                  (f"sum by (name) (container_spec_memory_limit_bytes{{{C}}}) > 0", "{{name}} limit")], "bytes",
           desc="working_set is what the kernel OOM-killer looks at (not 'usage', which includes reclaimable cache)."),
        ts("CPU cores used", [(f"sum by (name) (rate(container_cpu_usage_seconds_total{{{C}}}[{RI}]))", "{{name}}"),
                              (f"sum by (name) (container_spec_cpu_quota{{{C}}}) / sum by (name) (container_spec_cpu_period{{{C}}})", "{{name}} limit")], "short"),
        ts("Container restarts (15m)", [(f"changes(container_start_time_seconds{{{C}}}[15m])", "{{name}}")], "short"),
        ts("OOM events (15m)", [(f"increase(container_oom_events_total{{{C}}}[15m])", "{{name}}")], "short",
           desc="Needs cAdvisor >= 0.46 with OOM events enabled. If empty, use the restarts panel."),
    ], [CONT_VAR])

# ------------------------------------------------------------ 07 throttling
THR = (f"sum by (name) (rate(container_cpu_cfs_throttled_periods_total{{{C}}}[{RI}])) / "
       f"sum by (name) (rate(container_cpu_cfs_periods_total{{{C}}}[{RI}]))")
D["07-cpu-throttling"] = dashboard("07-cpu-throttling", "CPU Throttling",
    "A container with a CPU limit gets paused by the kernel once it uses its quota in a 100ms period. It looks 'healthy' but is slow. Correlate with latency.",
    [
        bar("Throttled periods %", [(THR, "{{name}}")], th=GYR(0.1, 0.25)),
        bar("CPU used % of limit", [(CPUP, "{{name}}")], th=GYR(0.8, 0.95), max=None),
        ts("Throttled periods ratio", [(THR, "{{name}}")], "percentunit", min=0, th=GYR(0.1, 0.25), th_line=True,
           desc="Alert fires above 25% for 5 minutes (same as kube-prometheus CPUThrottlingHigh)."),
        ts("Throttled time (seconds per second)", [(f"sum by (name) (rate(container_cpu_cfs_throttled_seconds_total{{{C}}}[{RI}]))", "{{name}}")], "s"),
        ts("orders-api p95 latency (correlation)",
           [('histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="orders-api",route!="/healthz"}[$__rate_interval])))', "p95 orders-api")],
           "s", desc="When orders-api is throttled its latency climbs - the classic hidden cause of 'slow for no reason'."),
        ts("orders-api CPU vs limit",
           [('sum(rate(container_cpu_usage_seconds_total{name="lab-orders-api"}[$__rate_interval]))', "used"),
            ('sum(container_spec_cpu_quota{name="lab-orders-api"}) / sum(container_spec_cpu_period{name="lab-orders-api"})', "limit")], "short"),
    ], [CONT_VAR])

# ------------------------------------------------------------ 08 k8s restarts
D["08-pod-restarts-crashloop"] = dashboard("08-pod-restarts-crashloop", "Pod Restarts, CrashLoopBackOff & OOMKilled (Kubernetes)",
    "Kubernetes track - needs the kind cluster from `k8s/README.md`. Unstable pods: why they restart and how often.",
    [
        stat("Containers in CrashLoopBackOff", f'sum(kube_pod_container_status_waiting_reason{{{NS},reason="CrashLoopBackOff"}}) or vector(0)', th=[(None, "green"), (1, "red")]),
        stat("Last terminated: OOMKilled", f'sum(kube_pod_container_status_last_terminated_reason{{{NS},reason="OOMKilled"}}) or vector(0)', th=[(None, "green"), (1, "red")]),
        stat("Restarts (last 1h)", f"sum(increase(kube_pod_container_status_restarts_total{{{NS}}}[1h])) or vector(0)", th=GYR(1, 5)),
        stat("Image pull problems", f'sum(kube_pod_container_status_waiting_reason{{{NS},reason=~"ImagePullBackOff|ErrImagePull"}}) or vector(0)', th=[(None, "green"), (1, "red")]),
        ts("Restarts in last 15m by container", [(f"increase(kube_pod_container_status_restarts_total{{{NS}}}[15m]) > 0", "{{namespace}}/{{pod}}/{{container}}")], "short"),
        ts("Waiting reasons", [(f"sum by (reason) (kube_pod_container_status_waiting_reason{{{NS}}}) > 0", "{{reason}}")], "short", stack=True),
        ts("Last termination reasons", [(f"sum by (reason) (kube_pod_container_status_last_terminated_reason{{{NS}}}) > 0", "{{reason}}")], "short", stack=True),
        ts("Memory working set vs limit", [(f'sum by (pod, container) (container_memory_working_set_bytes{{{NS},container!="",container!="POD"}}) / on (pod, container) sum by (pod, container) (kube_pod_container_resource_limits{{{NS},resource="memory"}})', "{{pod}}/{{container}}")],
           "percentunit", th=GYR(0.85, 0.95), th_line=True),
    ], [NS_VAR], time_from="now-1h")

# ------------------------------------------------------------ 09 k8s deployments
D["09-deployment-health"] = dashboard("09-deployment-health", "Deployment & Replica Health (Kubernetes)",
    "Kubernetes track. Are workloads running the number of replicas we asked for? Are rollouts progressing? Are pods stuck Pending?",
    [
        stat("Deployments missing replicas", f"count(kube_deployment_spec_replicas{{{NS}}} != kube_deployment_status_replicas_available{{{NS}}}) or vector(0)", th=[(None, "green"), (1, "red")]),
        stat("Stuck rollouts", f'count(kube_deployment_status_condition{{{NS},condition="Progressing",status="false"}} == 1) or vector(0)', th=[(None, "green"), (1, "red")]),
        stat("Pending pods", f'sum(kube_pod_status_phase{{{NS},phase="Pending"}}) or vector(0)', th=[(None, "green"), (1, "orange")]),
        stat("Unschedulable pods", f"sum(kube_pod_status_unschedulable{{{NS}}}) or vector(0)", th=[(None, "green"), (1, "red")]),
        ts("Desired vs available replicas", [(f"kube_deployment_spec_replicas{{{NS}}}", "{{deployment}} desired"),
                                             (f"kube_deployment_status_replicas_available{{{NS}}}", "{{deployment}} available")], "short"),
        ts("Unavailable replicas", [(f"kube_deployment_status_replicas_unavailable{{{NS}}} > 0", "{{namespace}}/{{deployment}}")], "short"),
        ts("Pods by phase", [(f"sum by (phase) (kube_pod_status_phase{{{NS}}}) > 0", "{{phase}}")], "short", stack=True),
        ts("HPA current vs max replicas", [(f"kube_horizontalpodautoscaler_status_current_replicas{{{NS}}}", "{{horizontalpodautoscaler}} current"),
                                           (f"kube_horizontalpodautoscaler_spec_max_replicas{{{NS}}}", "{{horizontalpodautoscaler}} max")], "short"),
    ], [NS_VAR], time_from="now-1h")

# ------------------------------------------------------------ 10 node
NODE = 'job="node"'
D["10-node-cpu-memory"] = dashboard("10-node-cpu-memory", "Host CPU, Memory & Load",
    "The machine under your containers (USE method: **U**tilization, **S**aturation, **E**rrors). On Docker Desktop this is the Docker VM.",
    [
        stat("CPU busy", f'1 - avg(rate(node_cpu_seconds_total{{{NODE},mode="idle"}}[5m]))', "percentunit", th=GYR(0.7, 0.85), decimals=1),
        stat("Memory used", f"1 - node_memory_MemAvailable_bytes{{{NODE}}} / node_memory_MemTotal_bytes{{{NODE}}}", "percentunit", th=GYR(0.8, 0.85), decimals=1),
        stat("Load (5m) per core", f'node_load5{{{NODE}}} / count(node_cpu_seconds_total{{{NODE},mode="idle"}})', "short", th=GYR(1, 2), decimals=2),
        stat("Uptime", f"time() - node_boot_time_seconds{{{NODE}}}", "s"),
        ts("CPU by mode", [(f'avg by (mode) (rate(node_cpu_seconds_total{{{NODE},mode!="idle"}}[{RI}]))', "{{mode}}")], "percentunit", stack=True, max=1,
           desc="High iowait = waiting on disk. High steal = noisy neighbour on a VM. High system = kernel work (network, syscalls)."),
        ts("Memory", [(f"node_memory_MemTotal_bytes{{{NODE}}} - node_memory_MemAvailable_bytes{{{NODE}}}", "used"),
                      (f"node_memory_MemAvailable_bytes{{{NODE}}}", "available"),
                      (f"node_memory_Cached_bytes{{{NODE}}} + node_memory_Buffers_bytes{{{NODE}}}", "cache+buffers"),
                      (f"node_memory_SwapTotal_bytes{{{NODE}}} - node_memory_SwapFree_bytes{{{NODE}}}", "swap used")], "bytes"),
        ts("Load average vs cores", [(f"node_load1{{{NODE}}}", "load1"), (f"node_load5{{{NODE}}}", "load5"), (f"node_load15{{{NODE}}}", "load15"),
                                     (f'count(node_cpu_seconds_total{{{NODE},mode="idle"}})', "cores")], "short"),
        ts("Pressure stall (PSI) - % of time waiting", [(f"rate(node_pressure_cpu_waiting_seconds_total{{{NODE}}}[{RI}])", "cpu"),
                                                        (f"rate(node_pressure_memory_waiting_seconds_total{{{NODE}}}[{RI}])", "memory"),
                                                        (f"rate(node_pressure_io_waiting_seconds_total{{{NODE}}}[{RI}])", "io")], "percentunit",
           desc="PSI (Linux 4.20+) is the best saturation signal: share of time tasks were stalled waiting for the resource."),
        ts("Kernel OOM kills", [(f"increase(node_vmstat_oom_kill{{{NODE}}}[5m])", "oom kills / 5m")], "short", w=24, h=6),
    ], time_from="now-1h")

# ------------------------------------------------------------ 11 disk
D["11-disk-space-io"] = dashboard("11-disk-space-io", "Disk Space, Fill Prediction & I/O",
    "The #1 'silent killer': disks fill up slowly, then everything breaks at once. Predict it, don't just threshold it.",
    [
        bar("Filesystem used %", [(f"1 - node_filesystem_avail_bytes{{{NODE},{FS}}} / node_filesystem_size_bytes{{{NODE},{FS}}}", "{{mountpoint}}")], th=GYR(0.8, 0.9), w=12),
        bar("Inodes used %", [(f"1 - node_filesystem_files_free{{{NODE},{FS}}} / node_filesystem_files{{{NODE},{FS}}}", "{{mountpoint}}")], th=GYR(0.8, 0.9), w=12),
        ts("Available space", [(f"node_filesystem_avail_bytes{{{NODE},{FS}}}", "{{mountpoint}}")], "bytes"),
        ts("Predicted available space in 4h (linear)", [(f"predict_linear(node_filesystem_avail_bytes{{{NODE},{FS}}}[1h], 4 * 3600)", "{{mountpoint}}")], "bytes",
           th=[(None, "red"), (0, "green")], th_line=True, desc="Below zero = disk will be full within 4 hours at the current fill rate."),
        ts("Disk utilization (busy time)", [(f"rate(node_disk_io_time_seconds_total{{{NODE}}}[{RI}])", "{{device}}")], "percentunit", max=1, th=GYR(0.8, 0.9), th_line=True),
        ts("Throughput", [(f"rate(node_disk_read_bytes_total{{{NODE}}}[{RI}])", "{{device}} read"),
                          (f"rate(node_disk_written_bytes_total{{{NODE}}}[{RI}])", "{{device}} write")], "Bps"),
        ts("Average I/O latency", [(f"rate(node_disk_read_time_seconds_total{{{NODE}}}[{RI}]) / rate(node_disk_reads_completed_total{{{NODE}}}[{RI}])", "{{device}} read"),
                                   (f"rate(node_disk_write_time_seconds_total{{{NODE}}}[{RI}]) / rate(node_disk_writes_completed_total{{{NODE}}}[{RI}])", "{{device}} write")], "s", w=24),
    ], time_from="now-1h")

# ------------------------------------------------------------ 12 network
D["12-network"] = dashboard("12-network", "Network Throughput, Errors & TCP",
    "Bandwidth, packet errors/drops, TCP health and per-container traffic. Network problems often show up first as retransmits and latency.",
    [
        stat("Host receive", f"sum(rate(node_network_receive_bytes_total{{{NODE},{NIC}}}[5m])) * 8", "bps"),
        stat("Host transmit", f"sum(rate(node_network_transmit_bytes_total{{{NODE},{NIC}}}[5m])) * 8", "bps"),
        stat("TCP retransmit ratio", f"rate(node_netstat_Tcp_RetransSegs{{{NODE}}}[5m]) / rate(node_netstat_Tcp_OutSegs{{{NODE}}}[5m])", "percentunit", th=GYR(0.01, 0.02), decimals=2),
        stat("Conntrack table used", f"node_nf_conntrack_entries{{{NODE}}} / node_nf_conntrack_entries_limit{{{NODE}}}", "percentunit", th=GYR(0.7, 0.8), decimals=1),
        ts("Host traffic by interface", [(f"rate(node_network_receive_bytes_total{{{NODE},{NIC}}}[{RI}]) * 8", "{{device}} rx"),
                                          (f"-rate(node_network_transmit_bytes_total{{{NODE},{NIC}}}[{RI}]) * 8", "{{device}} tx")], "bps",
           desc="tx is drawn negative so rx and tx don't overlap."),
        ts("Errors & drops", [(f"rate(node_network_receive_errs_total{{{NODE}}}[{RI}]) > 0", "{{device}} rx errs"),
                              (f"rate(node_network_transmit_errs_total{{{NODE}}}[{RI}]) > 0", "{{device}} tx errs"),
                              (f"rate(node_network_receive_drop_total{{{NODE}}}[{RI}]) > 0", "{{device}} rx drop"),
                              (f"rate(node_network_transmit_drop_total{{{NODE}}}[{RI}]) > 0", "{{device}} tx drop")], "pps"),
        ts("TCP connections", [(f"node_netstat_Tcp_CurrEstab{{{NODE}}}", "established"), (f"node_sockstat_TCP_tw{{{NODE}}}", "time_wait"),
                               (f"node_sockstat_TCP_inuse{{{NODE}}}", "in use")], "short"),
        ts("TCP retransmit ratio", [(f"rate(node_netstat_Tcp_RetransSegs{{{NODE}}}[{RI}]) / rate(node_netstat_Tcp_OutSegs{{{NODE}}}[{RI}])", "retransmits")],
           "percentunit", th=GYR(0.01, 0.02), th_line=True),
        ts("Container traffic", [(f"sum by (name) (rate(container_network_receive_bytes_total{{{C}}}[{RI}])) * 8", "{{name}} rx"),
                                 (f"-sum by (name) (rate(container_network_transmit_bytes_total{{{C}}}[{RI}])) * 8", "{{name}} tx")], "bps", w=24),
    ], [CONT_VAR], time_from="now-1h")

# ------------------------------------------------------------ 13 databases
D["13-databases"] = dashboard("13-databases", "Databases: PostgreSQL & Redis",
    "Start with `make db-on`. Connections, long transactions, cache efficiency, deadlocks (Postgres) and memory, evictions, hit ratio (Redis).",
    [
        stat("PostgreSQL up", "max(pg_up) or vector(0)", th=[(None, "red"), (1, "green")]),
        stat("PG connections used", "sum(pg_stat_activity_count) / max(pg_settings_max_connections)", "percentunit", th=GYR(0.7, 0.8), decimals=1),
        stat("Redis up", "max(redis_up) or vector(0)", th=[(None, "red"), (1, "green")]),
        stat("Redis memory used", "max(redis_memory_used_bytes / (redis_memory_max_bytes > 0))", "percentunit", th=GYR(0.8, 0.9), decimals=1),
        ts("PG connections by state", [("sum by (state) (pg_stat_activity_count)", "{{state}}"), ("max(pg_settings_max_connections)", "max_connections")], "short"),
        ts("PG longest running transaction", [("max by (datname, state) (pg_stat_activity_max_tx_duration) > 0", "{{datname}} {{state}}")], "s",
           th=GYR(60, 300), th_line=True, desc="Long transactions block VACUUM and hold locks."),
        ts("PG buffer cache hit ratio", [('sum by (datname) (rate(pg_stat_database_blks_hit{datname!~"template.*"}[$__rate_interval])) / (sum by (datname) (rate(pg_stat_database_blks_hit{datname!~"template.*"}[$__rate_interval])) + sum by (datname) (rate(pg_stat_database_blks_read{datname!~"template.*"}[$__rate_interval])))', "{{datname}}")],
           "percentunit", max=1),
        ts("PG transactions / s", [('sum by (datname) (rate(pg_stat_database_xact_commit{datname!~"template.*"}[$__rate_interval]))', "{{datname}} commit"),
                                   ('sum by (datname) (rate(pg_stat_database_xact_rollback{datname!~"template.*"}[$__rate_interval]))', "{{datname}} rollback"),
                                   ('sum by (datname) (increase(pg_stat_database_deadlocks[5m])) > 0', "{{datname}} deadlocks/5m")], "ops"),
        ts("Redis memory", [("redis_memory_used_bytes", "used"), ("redis_memory_max_bytes > 0", "maxmemory")], "bytes"),
        ts("Redis hit ratio", [("rate(redis_keyspace_hits_total[$__rate_interval]) / (rate(redis_keyspace_hits_total[$__rate_interval]) + rate(redis_keyspace_misses_total[$__rate_interval]))", "hit ratio")],
           "percentunit", max=1),
        ts("Redis ops & evictions", [("rate(redis_commands_processed_total[$__rate_interval])", "commands/s"), ("rate(redis_evicted_keys_total[$__rate_interval])", "evictions/s")], "ops"),
        ts("Redis clients", [("redis_connected_clients", "connected"), ("redis_blocked_clients", "blocked")], "short"),
    ], time_from="now-1h")

# ------------------------------------------------------------ 14 kafka
D["14-message-queue-lag"] = dashboard("14-message-queue-lag", "Message Queue: Kafka Consumer Lag",
    "Start with `make mq-on`. Lag = messages produced but not yet processed. Growing lag = consumers can't keep up; your 'async' work is getting late.",
    [
        stat("Total consumer lag", "sum(kafka_consumergroup_lag_sum) or vector(0)", th=GYR(500, 1000)),
        stat("Estimated time to drain", "sum(kafka_consumergroup_lag_sum) / sum(rate(kafka_consumergroup_current_offset_sum[5m]))", "s",
             th=GYR(60, 300), desc="lag ÷ consumption rate. How long until consumers catch up if producers stopped."),
        stat("Consumer group members", "sum(kafka_consumergroup_members) or vector(0)", th=[(None, "red"), (1, "green")]),
        stat("Brokers", "max(kafka_brokers) or vector(0)", th=[(None, "red"), (1, "green")]),
        ts("Lag by consumer group / topic", [('sum by (consumergroup, topic) (kafka_consumergroup_lag_sum)', "{{consumergroup}} → {{topic}}")], "short",
           th=GYR(500, 1000), th_line=True),
        ts("Lag by partition", [('kafka_consumergroup_lag', "{{topic}}/{{partition}}")], "short",
           desc="One hot partition lagging = key skew or a stuck consumer instance."),
        ts("Produce vs consume rate", [('sum by (topic) (rate(kafka_topic_partition_current_offset{topic!~"__.*"}[$__rate_interval]))', "produced {{topic}}"),
                                       ('sum by (topic) (rate(kafka_consumergroup_current_offset_sum[$__rate_interval]))', "consumed {{topic}}")], "ops"),
        ts("Consumer group members", [("kafka_consumergroup_members", "{{consumergroup}}")], "short"),
    ], time_from="now-30m")

# ------------------------------------------------------------ 15 availability
D["15-availability-probes"] = dashboard("15-availability-probes", "Availability: Targets, Synthetic Probes & TLS",
    "Outside-in monitoring. `up` = can Prometheus scrape it? `probe_success` = does it answer like a user expects? Plus certificate expiry.",
    [
        stat("Scrape targets down", 'count(up == 0) or vector(0)', th=[(None, "green"), (1, "red")]),
        stat("Probes failing", 'count(probe_success{job!="blackbox-cert"} == 0) or vector(0)', th=[(None, "green"), (1, "red")]),
        stat("Soonest cert expiry", '(min(probe_ssl_earliest_cert_expiry{job="blackbox-http"}) - time()) / 86400', "d",
             th=[(None, "red"), (14, "orange"), (30, "green")], decimals=0),
        stat("Slowest probe", 'max(probe_duration_seconds{job="blackbox-http"})', "s", th=GYR(1, 3)),
        timeline("Scrape target health (up)", [("up", "{{job}} {{instance}}")], h=10),
        timeline("Probe success", [('probe_success{job!="blackbox-cert"}', "{{job}} {{instance}}")], h=8),
        ts("HTTP probe duration by phase", [('sum by (instance) (probe_http_duration_seconds{job="blackbox-http"})', "{{instance}}")], "s"),
        ts("HTTP status code", [('probe_http_status_code{job="blackbox-http"}', "{{instance}}")], "short"),
        ts("TLS certificate days left", [("(probe_ssl_earliest_cert_expiry - time()) / 86400", "{{instance}}")], "d",
           th=[(None, "red"), (0, "orange"), (14, "green")], th_line=True, desc="expired.badssl.com is deliberately expired (negative)."),
        ts("DNS lookup & ICMP round-trip", [('probe_dns_lookup_time_seconds{job="blackbox-dns"}', "dns via {{instance}}"),
                                            ('probe_icmp_duration_seconds{job="blackbox-icmp",phase="rtt"}', "ping {{instance}}")], "s"),
    ], time_from="now-1h")


if __name__ == "__main__":
    for folder, dash in D.items():
        path = ROOT / "projects" / folder / "dashboard.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dash, indent=2) + "\n")
        print(f"wrote {path.relative_to(ROOT)}  ({len(dash['panels'])} panels)")
