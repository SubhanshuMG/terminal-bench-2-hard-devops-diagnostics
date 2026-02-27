"""
Test suite for the Deployment Health Validator task.

Verifies that /app/deployment_report.json is correct after the agent
(or solve.sh) has fixed /app/validator.py and executed it.
"""

import json
import os
import pytest

REPORT_PATH = "/app/deployment_report.json"

# ── helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def report():
    assert os.path.exists(REPORT_PATH), (
        f"Report file not found at {REPORT_PATH}. "
        "Did you run 'python /app/validator.py'?"
    )
    with open(REPORT_PATH) as f:
        return json.load(f)


# ── schema / existence tests ──────────────────────────────────────────────────

def test_report_file_exists():
    """The report JSON must exist at /app/deployment_report.json."""
    assert os.path.exists(REPORT_PATH)


def test_report_top_level_keys(report):
    """Report must contain all required top-level keys."""
    required = {
        "deployment_name",
        "overall_status",
        "readiness_score",
        "service_statuses",
        "startup_order",
        "critical_services_healthy",
        "timestamp",
    }
    missing = required - set(report.keys())
    assert not missing, f"Missing keys: {missing}"


def test_deployment_name(report):
    """deployment_name must match the manifest."""
    assert report["deployment_name"] == "production-stack"


def test_timestamp_format(report):
    """timestamp must be a valid ISO 8601 datetime string with UTC timezone offset."""
    from datetime import datetime
    ts = report["timestamp"]
    assert isinstance(ts, str), "timestamp must be a string"
    # Must parse as a valid datetime and include timezone info
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        raise AssertionError(f"timestamp '{ts}' is not a valid ISO 8601 datetime")
    assert dt.tzinfo is not None, (
        f"timestamp '{ts}' must include timezone info (e.g. '+00:00')"
    )


# ── service status tests ──────────────────────────────────────────────────────

def test_all_five_services_present(report):
    """service_statuses must contain all five services."""
    expected = {
        "auth-service",
        "api-gateway",
        "cache-service",
        "worker-service",
        "notification-service",
    }
    assert set(report["service_statuses"].keys()) == expected


def test_auth_service_healthy(report):
    """auth-service should return 200 and be reported healthy."""
    svc = report["service_statuses"]["auth-service"]
    assert svc["status"] == "healthy"
    assert svc["http_status"] == 200


def test_api_gateway_healthy(report):
    """api-gateway should return 200 and be reported healthy."""
    svc = report["service_statuses"]["api-gateway"]
    assert svc["status"] == "healthy"
    assert svc["http_status"] == 200


def test_cache_service_healthy(report):
    """cache-service uses /ping (not /health) and must be reported healthy (HTTP 200)."""
    svc = report["service_statuses"]["cache-service"]
    assert svc["status"] == "healthy", (
        "cache-service should be healthy. Its endpoint is /ping, not /health."
    )
    assert svc["http_status"] == 200


def test_worker_service_unhealthy(report):
    """worker-service returns HTTP 200 but with status='degraded' in body; must be reported unhealthy."""
    svc = report["service_statuses"]["worker-service"]
    assert svc["status"] == "unhealthy", (
        "worker-service reports {'status': 'degraded'} in its JSON body. "
        "Despite HTTP 200, a 'degraded' body status means the service is unhealthy."
    )
    assert svc["http_status"] == 200


def test_notification_service_healthy(report):
    """notification-service should return 200 and be reported healthy."""
    svc = report["service_statuses"]["notification-service"]
    assert svc["status"] == "healthy"
    assert svc["http_status"] == 200


def test_service_criticality_values(report):
    """Criticality values in the report must match the manifest."""
    expected_criticality = {
        "auth-service":          "high",
        "api-gateway":           "high",
        "cache-service":         "medium",
        "worker-service":        "low",
        "notification-service":  "low",
    }
    for name, crit in expected_criticality.items():
        assert report["service_statuses"][name]["criticality"] == crit, (
            f"{name}: expected criticality '{crit}', "
            f"got '{report['service_statuses'][name]['criticality']}'"
        )


# ── readiness score test ──────────────────────────────────────────────────────

def test_readiness_score(report):
    """
    Weighted score with high=3, medium=2, low=1:
      healthy:  auth(3) + api-gateway(3) + cache(2) + notification(1) = 9
      total:    9 + worker(1) = 10
      score:    9/10 = 0.9
    """
    assert abs(report["readiness_score"] - 0.9) < 0.001, (
        f"Expected readiness_score ~0.9, got {report['readiness_score']}. "
        "Check criticality weights: high=3, medium=2, low=1."
    )


# ── critical services test ────────────────────────────────────────────────────

def test_critical_services_healthy(report):
    """
    Both high-criticality services (auth-service, api-gateway) are healthy,
    so critical_services_healthy must be True.
    Worker-service (low criticality) being unhealthy should NOT affect this flag.
    """
    assert report["critical_services_healthy"] is True, (
        "critical_services_healthy should be True because all 'high' criticality "
        "services are healthy. Only 'high' criticality services should be checked."
    )


# ── overall status test ───────────────────────────────────────────────────────

def test_overall_status_degraded(report):
    """
    All high-criticality services are healthy but score (0.9) < 0.95,
    so overall_status must be 'degraded'.
    """
    assert report["overall_status"] == "degraded", (
        f"Expected overall_status='degraded', got '{report['overall_status']}'. "
        "Rules: critical_services_healthy=True + score<0.95 -> 'degraded'."
    )


# ── startup order tests ───────────────────────────────────────────────────────

def test_startup_order_has_all_services(report):
    """startup_order must list all five services exactly once."""
    order = report["startup_order"]
    assert len(order) == 5
    assert set(order) == {
        "auth-service", "api-gateway", "cache-service",
        "worker-service", "notification-service",
    }


def test_startup_order_auth_before_gateway(report):
    """auth-service is a dependency of api-gateway, so it must start first."""
    order = report["startup_order"]
    assert order.index("auth-service") < order.index("api-gateway"), (
        "auth-service must appear before api-gateway in startup_order."
    )


def test_startup_order_cache_before_gateway(report):
    """cache-service is a dependency of api-gateway, so it must start first."""
    order = report["startup_order"]
    assert order.index("cache-service") < order.index("api-gateway"), (
        "cache-service must appear before api-gateway in startup_order."
    )


def test_startup_order_gateway_before_worker(report):
    """api-gateway is a dependency of worker-service, so it must start first."""
    order = report["startup_order"]
    assert order.index("api-gateway") < order.index("worker-service"), (
        "api-gateway must appear before worker-service in startup_order."
    )


def test_startup_order_worker_before_notification(report):
    """worker-service is a dependency of notification-service, so it must start first."""
    order = report["startup_order"]
    assert order.index("worker-service") < order.index("notification-service"), (
        "worker-service must appear before notification-service in startup_order."
    )
