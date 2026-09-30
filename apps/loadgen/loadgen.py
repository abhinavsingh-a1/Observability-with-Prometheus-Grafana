"""
Constant-rate traffic generator (stdlib only).

Env:
  TARGETS  comma separated base URLs
  RPS      total requests per second across all targets (default 10)

Requests are fired from a thread pool so slow responses do not reduce the
arrival rate - exactly like real users who don't wait for each other.
"""
import os
import random
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

TARGETS = [t.strip() for t in os.getenv("TARGETS", "http://localhost:8080").split(",") if t.strip()]
RPS = float(os.getenv("RPS", "10"))

# (weight, method, path) - a realistic mix incl. some 404s
MIX = [
    (50, "GET", "/api/orders"),
    (20, "GET", "/api/orders/{id}"),   # id 1..130 -> ~23 % are 404
    (20, "POST", "/api/orders"),
    (10, "POST", "/api/payments"),
]
WEIGHTS = [m[0] for m in MIX]


def fire():
    _, method, path = random.choices(MIX, weights=WEIGHTS)[0]
    url = random.choice(TARGETS) + path.replace("{id}", str(random.randint(1, 130)))
    req = urllib.request.Request(url, method=method, data=b"{}" if method == "POST" else None,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception:
        pass  # errors are expected (chaos) - the server-side metrics record them


def main():
    print(f"loadgen: {RPS} rps -> {TARGETS}")
    interval = 1.0 / RPS
    next_t = time.perf_counter()
    with ThreadPoolExecutor(max_workers=100) as pool:
        while True:
            pool.submit(fire)
            next_t += interval
            time.sleep(max(0.0, next_t - time.perf_counter()))


if __name__ == "__main__":
    main()
