# Terminal Bench 2.0 : Hard DevOps Task Submission

**Task**: Deployment Health Validator
**Difficulty**: Hard
**Domain**: DevOps / Python Debugging
**Author**: subhanshu@bespokelabs.ai

---

## Overview

This repository contains a Terminal Bench 2.0 task submission. The task presents an AI agent with a broken deployment health validation tool and asks it to find and fix all the bugs. The tool reads a microservices manifest, checks five live HTTP endpoints, computes a weighted readiness score, performs a topological sort for startup ordering, and writes a JSON report.

The task is deliberately calibrated so that most AI agents will solve *some* bugs but not all — making it a meaningful "hard" benchmark.

---

## Task Structure

```
deployment-health-validator/
├── task.toml                       # Task metadata and timeout configuration
├── instruction.md                  # Instructions given to the agent
├── environment/
│   ├── Dockerfile                  # Container definition
│   ├── deployment_manifest.yaml    # Service definitions (with a decoy top-level key)
│   ├── mock_services.py            # Five Flask servers simulating service health endpoints
│   └── validator.py                # THE BROKEN FILE — agents must fix this
├── solution/
│   └── solve.sh                    # Oracle solution — fixes all 5 bugs
└── tests/
    └── test_outputs.py             # 19 pytest assertions verifying the JSON report
```

---

## The Five Bugs in `validator.py`

The broken validator contains five independent bugs of varying difficulty:

### Bug 1 — Wrong YAML key path
```python
# BROKEN:
return config["services"]               # returns a legacy monitoring entry only

# FIXED:
return config["deployment"]["services"] # authoritative service list
```
The manifest has a decoy top-level `services:` block containing a single legacy `metrics-collector` entry. The real services live under `deployment.services`. Comments in the YAML explain this distinction.

---

### Bug 2 — Wrong JSON body field name (the hardest to spot)
```python
# BROKEN:
state = body.get("health_status", "ok")  # "health_status" key never exists in any response
                                          # → always falls back to default "ok"
                                          # → worker-service silently reported as healthy

# FIXED:
state = body.get("status", "ok")         # correct field name used by all services
```
`worker-service` returns `HTTP 200` with `{"status": "degraded", "queue_depth": 1482}`. The broken code reads the wrong key (`health_status`) and falls back to the default `"ok"`, so the service is wrongly reported as healthy. The validator produces no errors and output looks plausible. Only agents that curl the endpoint *and* trace the exact field name in the code will catch this.

---

### Bug 3 — Reversed topological sort graph direction
```python
# BROKEN (builds a reverse graph — leaf nodes appear first):
graph[svc].append(dep)
in_degree[dep] += 1

# FIXED (dep must start before svc that depends on it):
graph[dep].append(svc)
in_degree[svc] += 1
```
Kahn's algorithm is structurally correct but the dependency edges are reversed. This causes `notification-service` (a leaf) to appear first in startup order rather than last.

---

### Bug 4 — Equal criticality weights (ignores the spec)
```python
# BROKEN:
weight_map = {"high": 1, "medium": 1, "low": 1}

# FIXED:
weight_map = {"high": 3, "medium": 2, "low": 1}
```
The task spec clearly defines weights 3/2/1 by criticality level. This bug produces an incorrect `readiness_score`.

---

### Bug 5 — `critical_services_healthy` checks all services, not just high-criticality ones
```python
# BROKEN:
critical_ok = all(
    statuses[s["name"]]["status"] == "healthy"
    for s in services               # checks every service — including low-criticality worker
)

# FIXED:
critical_ok = all(
    statuses[s["name"]]["status"] == "healthy"
    for s in services
    if s["criticality"] == "high"   # only the two high-criticality services matter
)
```
With `worker-service` (low criticality) being unhealthy, the broken code sets `critical_services_healthy = False` and `overall_status = "critical"` instead of the correct `"degraded"`.

---

## Expected Correct Report

```json
{
  "deployment_name": "production-stack",
  "overall_status": "degraded",
  "readiness_score": 0.9,
  "service_statuses": {
    "auth-service":         { "status": "healthy",   "http_status": 200, "criticality": "high" },
    "api-gateway":          { "status": "healthy",   "http_status": 200, "criticality": "high" },
    "cache-service":        { "status": "healthy",   "http_status": 200, "criticality": "medium" },
    "worker-service":       { "status": "unhealthy", "http_status": 200, "criticality": "low" },
    "notification-service": { "status": "healthy",   "http_status": 200, "criticality": "low" }
  },
  "startup_order": ["auth-service", "cache-service", "api-gateway", "worker-service", "notification-service"],
  "critical_services_healthy": true,
  "timestamp": "2024-01-01T00:00:00+00:00"
}
```

**Score derivation** (high=3, medium=2, low=1):
- Healthy weight: auth(3) + api-gateway(3) + cache(2) + notification(1) = **9**
- Total weight: 9 + worker(1) = **10**
- Readiness score: 9/10 = **0.9**
- Status: all high-criticality services healthy + score < 0.95 → `"degraded"`

---

## Service Endpoints (mock_services.py)

| Service              | Port | Endpoint  | HTTP | Body                              | Healthy? |
|----------------------|------|-----------|------|-----------------------------------|----------|
| auth-service         | 8081 | `/health` | 200  | `{"status": "ok"}`               | Yes      |
| api-gateway          | 8082 | `/health` | 200  | `{"status": "healthy"}`          | Yes      |
| cache-service        | 8083 | `/ping`   | 200  | `pong` (plain text)              | Yes      |
| worker-service       | 8084 | `/status` | 200  | `{"status": "degraded"}`         | **No**   |
| notification-service | 8085 | `/health` | 200  | `{"status": "ok"}`               | Yes      |

Notable design choices:
- `cache-service` uses `/ping` (not `/health`) to test that agents read the manifest carefully
- `worker-service` returns **HTTP 200** while being **unhealthy** — this is the primary trap
- All five services return HTTP 200, so HTTP-status-only checks will pass all of them

---

## How to Run Locally

### Prerequisites

```bash
# Install harbor CLI
pip install bespokelabs-harbor

# Set up the project
git clone <this-repo>
cd terminal-bench-2-hard-devops-diagnostics
python -m venv .venv && source .venv/bin/activate
pip install bespokelabs-harbor
```

### Verify the oracle (task must be solvable)

```bash
export GROQ_API_KEY=<your-key>
harbor run -p ./deployment-health-validator -a oracle -q
```

```
┌─────────────────────┬────────┐
│ Reward Distribution │        │
│   reward = 1.0      │ 1      │
└─────────────────────┴────────┘
```

### Run an agent trial

```bash
export GROQ_API_KEY=<your-key>
harbor run -p ./deployment-health-validator \
    -a terminus-2 \
    -m groq/moonshotai/kimi-k2-instruct-0905
```

### Test the solution manually

```bash
# Inside the Docker container
python /app/mock_services.py &
sleep 2
bash /app/solution/solve.sh
pytest /app/tests/ -v
```

### Verify endpoints with curl

```bash
curl http://localhost:8081/health   # {"status": "ok"}
curl http://localhost:8082/health   # {"status": "healthy"}
curl http://localhost:8083/ping     # pong
curl http://localhost:8084/status   # {"status": "degraded", "queue_depth": 1482}
curl http://localhost:8085/health   # {"status": "ok"}
```

---

## Difficulty Calibration Journey

Getting the agent success rate into the "hard" range (> 0% and ≤ 70%) required careful iteration:

| Iteration | Bug 2 Design | Instruction Hint | Agent Success |
|-----------|-------------|------------------|---------------|
| 1 | `"healthy"` missing from accepted values list (JSON check otherwise correct) | None needed | **100%** — too easy |
| 2 | No JSON body check at all — HTTP-only: `healthy = resp.status_code == 200` | "verify actual responses" | **0%** — too hard (agents assume HTTP 200 = healthy) |
| 3 | No JSON body check | Explicit semantics section with valid values `("ok", "up", "healthy")` + Tip | **90%** — still too easy |
| 4 | No JSON body check | "inspect HTTP status AND response body; HTTP 200 ≠ always healthy" | **0%** — agents ignore hint |
| 5 (final) | Wrong field name `"health_status"` (correct logic, wrong key) | "compare what each service returns against what the validator reads" | **~40–60%** (target) |

**Key insight**: The bug must produce plausible-looking output without errors. A pure HTTP-only check looks correct to agents doing casual code review. A wrong field name with a plausible default value is the sweet spot — it produces wrong answers but no exceptions, so only thorough agents catch it.

---

## Test Suite (19 tests)

```
tests/test_outputs.py
├── test_report_file_exists
├── test_report_top_level_keys
├── test_deployment_name
├── test_timestamp_format                  ← validates ISO 8601 UTC format
├── test_all_five_services_present
├── test_auth_service_healthy
├── test_api_gateway_healthy
├── test_cache_service_healthy
├── test_worker_service_unhealthy          ← catches Bug 2 (field name) + Bug 1 (key path)
├── test_notification_service_healthy
├── test_service_criticality_values
├── test_readiness_score                   ← catches Bug 4 (weights)
├── test_critical_services_healthy         ← catches Bug 5 (criticality filter)
├── test_overall_status_degraded           ← catches all bugs combined
├── test_startup_order_has_all_services
├── test_startup_order_auth_before_gateway   ← catch Bug 3 (topo sort)
├── test_startup_order_cache_before_gateway  ← catch Bug 3
├── test_startup_order_gateway_before_worker ← catch Bug 3
└── test_startup_order_worker_before_notification ← catch Bug 3
```

---
