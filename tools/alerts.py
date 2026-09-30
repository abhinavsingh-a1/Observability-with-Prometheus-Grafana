#!/usr/bin/env python3
"""Print pending/firing Prometheus alerts:  python3 tools/alerts.py [prometheus-url]"""
import json
import sys
import urllib.request

url = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9090") + "/api/v1/alerts"
alerts = json.load(urllib.request.urlopen(url, timeout=5))["data"]["alerts"]
if not alerts:
    print("no pending or firing alerts")
for a in sorted(alerts, key=lambda a: (a["labels"].get("project", ""), a["labels"]["alertname"])):
    lbl = a["labels"]
    target = lbl.get("service") or lbl.get("name") or lbl.get("instance") or ""
    print(f'{a["state"]:8} {lbl.get("severity", ""):8} project={lbl.get("project", "-"):3} '
          f'{lbl["alertname"]:32} {target}')
