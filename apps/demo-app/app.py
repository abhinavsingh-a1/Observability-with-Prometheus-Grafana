"""
Demo microservice instrumented with the Prometheus Python client.

It exposes everything the lab projects need:
  * RED metrics  (http_requests_total, http_request_duration_seconds)  -> projects 1, 2, 3, 5
  * runtime metrics (process_*, python_gc_*)                           -> project 4
  * business metrics (orders_created_total, payments_failed_total)
  * chaos endpoints to *cause* the problems each project detects        -> all projects

Chaos API (POST, query string or JSON body):
  /chaos?error_rate=0.3            fraction of /api requests returning 500
  /chaos?latency_ms=800            extra latency added to /api requests
  /chaos?healthy=false             /healthz returns 503
  /chaos/leak?mb=20                allocate and keep 20 MB (memory leak)
  /chaos/burn?seconds=120          burn CPU for N seconds (throttling demo)
  /chaos/reset                     back to normal (frees leaked memory, stops CPU burn)
  GET /chaos                       show current chaos state
"""
import os
import random
import threading
import time

from flask import Flask, Response, g, jsonify, request
from prometheus_client import (CONTENT_TYPE_LATEST, Counter, Gauge, Histogram,
                               Info, generate_latest)
from waitress import serve

SERVICE = os.getenv("SERVICE_NAME", "demo-app")
VERSION = os.getenv("APP_VERSION", "1.0.0")
BASELINE_ERROR_RATE = float(os.getenv("BASELINE_ERROR_RATE", "0.0005"))  # 0.05 %

app = Flask(__name__)

# ---------------------------------------------------------------- metrics
# Label design: `route` is the URL *template* (/api/orders/<int:order_id>),
# never the raw path, otherwise every order id creates a new time series.
REQUESTS = Counter("http_requests_total", "Total HTTP requests",
                   ["service", "method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency in seconds",
                    ["service", "method", "route"],
                    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
IN_FLIGHT = Gauge("http_requests_in_flight", "Requests currently being served", ["service"])
ORDERS = Counter("orders_created_total", "Orders successfully created", ["service"])
PAYMENTS_FAILED = Counter("payments_failed_total", "Business-level payment failures",
                          ["service", "reason"])
LEAKED = Gauge("demo_leaked_bytes", "Memory intentionally leaked via /chaos/leak", ["service"])
CHAOS = Gauge("demo_chaos_setting", "Current chaos settings (for dashboards)", ["service", "setting"])
Info("app", "Application build information").info({"service": SERVICE, "version": VERSION})

# ------------------------------------------------------------ chaos state
state = {"error_rate": BASELINE_ERROR_RATE, "latency_ms": 0.0, "healthy": True}
leak = []
lock = threading.Lock()
burn_stop = threading.Event()  # set by /chaos/reset to stop CPU burners


def publish_chaos():
    CHAOS.labels(SERVICE, "error_rate").set(state["error_rate"])
    CHAOS.labels(SERVICE, "latency_ms").set(state["latency_ms"])
    CHAOS.labels(SERVICE, "healthy").set(1 if state["healthy"] else 0)


publish_chaos()


# -------------------------------------------------------- instrumentation
@app.before_request
def start_timer():
    g.start = time.perf_counter()
    IN_FLIGHT.labels(SERVICE).inc()
    if request.path.startswith("/api/"):
        # realistic base latency 5-60 ms + injected latency (+-50 % jitter)
        extra = state["latency_ms"] * random.uniform(0.5, 1.5)
        time.sleep((random.uniform(5, 60) + extra) / 1000)
        if random.random() < state["error_rate"]:
            return jsonify(error="injected failure"), 500
    return None


@app.after_request
def record(response):
    IN_FLIGHT.labels(SERVICE).dec()
    if request.path == "/metrics":
        return response
    route = request.url_rule.rule if request.url_rule else "unmatched"
    REQUESTS.labels(SERVICE, request.method, route, str(response.status_code)).inc()
    LATENCY.labels(SERVICE, request.method, route).observe(time.perf_counter() - g.start)
    return response


# ------------------------------------------------------------- endpoints
ORDER_DB = {i: {"id": i, "item": f"item-{i}"} for i in range(1, 101)}


@app.get("/api/orders")
def list_orders():
    return jsonify(list(ORDER_DB.values())[:20])


@app.get("/api/orders/<int:order_id>")
def get_order(order_id):
    order = ORDER_DB.get(order_id)
    return (jsonify(order), 200) if order else (jsonify(error="not found"), 404)


@app.post("/api/orders")
def create_order():
    ORDERS.labels(SERVICE).inc()
    return jsonify(status="created"), 201


@app.post("/api/payments")
def pay():
    if random.random() < 0.03:  # business failure, still HTTP 200-level semantics
        PAYMENTS_FAILED.labels(SERVICE, random.choice(["card_declined", "insufficient_funds"])).inc()
        return jsonify(status="declined"), 402
    return jsonify(status="paid"), 200


@app.get("/healthz")
def healthz():
    return ("ok", 200) if state["healthy"] else ("unhealthy", 503)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


# ------------------------------------------------------------ chaos API
def _params():
    data = dict(request.args)
    if request.is_json:
        data.update(request.get_json(silent=True) or {})
    return data


@app.route("/chaos", methods=["GET", "POST"])
def chaos():
    if request.method == "POST":
        p = _params()
        with lock:
            if "error_rate" in p:
                state["error_rate"] = max(0.0, min(1.0, float(p["error_rate"])))
            if "latency_ms" in p:
                state["latency_ms"] = max(0.0, float(p["latency_ms"]))
            if "healthy" in p:
                state["healthy"] = str(p["healthy"]).lower() in ("1", "true", "yes")
        publish_chaos()
    return jsonify(service=SERVICE, leaked_mb=sum(map(len, leak)) // 2**20, **state)


@app.post("/chaos/leak")
def chaos_leak():
    mb = int(_params().get("mb", 10))
    with lock:
        leak.append(b"x" * (mb * 2**20))  # bytes are really written -> counts in RSS
        LEAKED.labels(SERVICE).set(sum(map(len, leak)))
    return jsonify(leaked_mb=sum(map(len, leak)) // 2**20)


@app.post("/chaos/burn")
def chaos_burn():
    seconds = float(_params().get("seconds", 60))

    burn_stop.clear()

    def burn():
        end = time.time() + seconds
        while time.time() < end and not burn_stop.is_set():
            sum(i * i for i in range(10_000))

    for _ in range(2):  # two busy threads = more than the 0.5 CPU limit
        threading.Thread(target=burn, daemon=True).start()
    return jsonify(burning_seconds=seconds)


@app.post("/chaos/reset")
def chaos_reset():
    with lock:
        state.update(error_rate=BASELINE_ERROR_RATE, latency_ms=0.0, healthy=True)
        leak.clear()
        burn_stop.set()
        LEAKED.labels(SERVICE).set(0)
    publish_chaos()
    return jsonify(status="reset", **state)


if __name__ == "__main__":
    print(f"{SERVICE} v{VERSION} listening on :8080")
    serve(app, host="0.0.0.0", port=8080, threads=16)
