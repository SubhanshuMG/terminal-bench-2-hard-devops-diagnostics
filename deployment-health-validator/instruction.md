# Deployment Health Validator — Debug Task

You are a DevOps engineer onboarding to a microservices team. The previous engineer left behind a deployment health validation tool that is **broken**. Your job is to fix it so the deployment pipeline works correctly.

## Context

The production stack has five services with dependencies between them. Before any deployment, a validator checks all services are healthy and computes a readiness report.

The following files exist in `/app/`:

- **`/app/deployment_manifest.yaml`** — Defines all services, their ports, health endpoints, dependencies, and criticality levels.
- **`/app/mock_services.py`** — Simulates the five service health endpoints (already running in the background).
- **`/app/validator.py`** — The main validation script. **It is currently broken and needs to be fixed.**

The mock services are already running. You can verify them manually with `curl`, for example:

```
curl http://localhost:8081/health
```

## Objective

Fix `/app/validator.py` so that running:

```
python /app/validator.py
```

produces a correct report at `/app/deployment_report.json`.

## Expected Report Schema

```json
{
  "deployment_name": "production-stack",
  "overall_status": "healthy|degraded|critical|not_ready",
  "readiness_score": 0.0,
  "service_statuses": {
    "service-name": {
      "status": "healthy|unhealthy",
      "http_status": 200,
      "criticality": "high|medium|low"
    }
  },
  "startup_order": ["service-name", "..."],
  "critical_services_healthy": true,
  "timestamp": "2024-01-01T00:00:00+00:00"
}
```

## Definitions

**`overall_status`**:
- `healthy` — all high-criticality services healthy AND readiness_score >= 0.95
- `degraded` — all high-criticality services healthy AND readiness_score < 0.95
- `critical` — one or more **high**-criticality services are unhealthy
- `not_ready` — readiness_score < 0.70 (regardless of criticality)

**`readiness_score`** — weighted fraction of healthy services:
- `high` criticality → weight **3**
- `medium` criticality → weight **2**
- `low` criticality → weight **1**
- Formula: `sum(weight for healthy services) / sum(weight for all services)`

**`startup_order`** — topologically sorted service names; every dependency must appear **before** its dependent in the list.

**`critical_services_healthy`** — `true` if and only if every service with criticality `"high"` is currently healthy.

## Notes

- Each service uses its own health endpoint (not always `/health`) — check the manifest.
- Use `curl` to probe each endpoint and verify the actual response bodies — compare what each service returns against what the validator reads from that response.
- Fix only `/app/validator.py`. Do not modify `mock_services.py` or `deployment_manifest.yaml`.
- The report must be written to `/app/deployment_report.json`.
