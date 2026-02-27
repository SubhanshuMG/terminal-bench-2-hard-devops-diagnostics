#!/bin/bash
set -e

# Ensure mock services are running (they should be from Docker CMD, but be safe)
if ! curl -sf http://localhost:8081/health > /dev/null 2>&1; then
    echo "[solve] Starting mock services..."
    python /app/mock_services.py > /tmp/mock_services.log 2>&1 &
    sleep 3
fi

# Write the fully corrected validator to a temp location and run it.
# All five bugs from the original /app/validator.py are fixed here.
cat > /tmp/validator_fixed.py << 'PYEOF'
#!/usr/bin/env python3
"""
Deployment Health Validator — FIXED version.
"""

import json
import yaml
import requests
from datetime import datetime, timezone
from collections import deque


def load_services(manifest_path: str) -> list:
    with open(manifest_path) as f:
        config = yaml.safe_load(f)
    # FIX-1: correct key path — services live under config['deployment']['services']
    return config["deployment"]["services"]


def check_health(service: dict) -> dict:
    # FIX-2: wrong field name "health_status" → should be "status".
    # The buggy code uses body.get("health_status", "ok") which always returns
    # the default "ok" because no service sends a "health_status" field.
    # This silently marks worker-service ({"status":"degraded"}) as healthy.
    # Fix: use the correct field name "status".
    url = f"http://127.0.0.1:{service['port']}{service['health_endpoint']}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return {
                "status": "unhealthy",
                "http_status": resp.status_code,
                "criticality": service["criticality"],
            }
        try:
            body = resp.json()
            status_ok = body.get("status", "ok") in ("ok", "up", "healthy")
        except ValueError:
            status_ok = True  # Non-JSON (e.g. "pong") — HTTP 200 is enough.
        return {
            "status": "healthy" if status_ok else "unhealthy",
            "http_status": resp.status_code,
            "criticality": service["criticality"],
        }
    except requests.exceptions.RequestException:
        return {
            "status": "unhealthy",
            "http_status": 0,
            "criticality": service["criticality"],
        }


def compute_startup_order(services: list) -> list:
    names = [s["name"] for s in services]
    deps_map = {s["name"]: s.get("dependencies", []) for s in services}

    graph = {n: [] for n in names}
    in_degree = {n: 0 for n in names}

    for svc, deps in deps_map.items():
        for dep in deps:
            # FIX-3: correct edge direction — dep must start before svc,
            # so the edge goes dep -> svc and in_degree[svc] increments.
            graph[dep].append(svc)
            in_degree[svc] += 1

    queue = deque(n for n in names if in_degree[n] == 0)
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    return order


def compute_readiness_score(services: list, statuses: dict) -> float:
    # FIX-4: correct criticality weights — high=3, medium=2, low=1
    weight_map = {"high": 3, "medium": 2, "low": 1}

    total = sum(weight_map[s["criticality"]] for s in services)
    healthy = sum(
        weight_map[s["criticality"]]
        for s in services
        if statuses[s["name"]]["status"] == "healthy"
    )
    return round(healthy / total, 4) if total else 0.0


def determine_status(services: list, statuses: dict, score: float):
    # FIX-5: only check services whose criticality is 'high'
    critical_ok = all(
        statuses[s["name"]]["status"] == "healthy"
        for s in services
        if s["criticality"] == "high"
    )

    if not critical_ok:
        return "critical", critical_ok
    if score >= 0.95:
        return "healthy", critical_ok
    if score >= 0.70:
        return "degraded", critical_ok
    return "not_ready", critical_ok


def main():
    manifest_path = "/app/deployment_manifest.yaml"
    output_path   = "/app/deployment_report.json"

    services = load_services(manifest_path)

    statuses = {}
    for svc in services:
        result = check_health(svc)
        statuses[svc["name"]] = result

    startup_order = compute_startup_order(services)
    score = compute_readiness_score(services, statuses)
    overall_status, critical_ok = determine_status(services, statuses, score)

    report = {
        "deployment_name":           "production-stack",
        "overall_status":            overall_status,
        "readiness_score":           score,
        "service_statuses":          statuses,
        "startup_order":             startup_order,
        "critical_services_healthy": critical_ok,
        "timestamp":                 datetime.now(timezone.utc).isoformat(),
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Report written to {output_path}")
    print(f"Overall status : {overall_status}")
    print(f"Readiness score: {score}")


if __name__ == "__main__":
    main()
PYEOF

echo "[solve] Running fixed validator..."
python /tmp/validator_fixed.py
