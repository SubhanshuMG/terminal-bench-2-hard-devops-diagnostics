#!/usr/bin/env python3
"""
Mock service health endpoints for the deployment stack.

Services:
  auth-service        -> port 8081  /health  -> 200  {"status": "ok"}
  api-gateway         -> port 8082  /health  -> 200  {"status": "healthy"}
  cache-service       -> port 8083  /ping    -> 200  "pong"
  worker-service      -> port 8084  /status  -> 200  {"status": "degraded"}  (overloaded)
  notification-service-> port 8085  /health  -> 200  {"status": "ok"}
"""

import threading
from flask import Flask, jsonify

import logging
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

# ── auth-service ──────────────────────────────────────────────────────────────
auth_app = Flask("auth-service")

@auth_app.route("/health")
def auth_health():
    return jsonify({"status": "ok", "version": "2.1.0"}), 200


# ── api-gateway ───────────────────────────────────────────────────────────────
gateway_app = Flask("api-gateway")

@gateway_app.route("/health")
def gateway_health():
    return jsonify({"status": "healthy", "uptime_seconds": 3601}), 200


# ── cache-service  (uses /ping, NOT /health) ──────────────────────────────────
cache_app = Flask("cache-service")

@cache_app.route("/ping")
def cache_ping():
    return "pong", 200


# ── worker-service  (uses /status — HTTP 200 but queue overloaded/degraded) ───
worker_app = Flask("worker-service")

@worker_app.route("/status")
def worker_status():
    return jsonify({"status": "degraded", "queue_depth": 1482}), 200


# ── notification-service ──────────────────────────────────────────────────────
notif_app = Flask("notification-service")

@notif_app.route("/health")
def notif_health():
    return jsonify({"status": "ok", "pending_notifications": 0}), 200


# ── runner ────────────────────────────────────────────────────────────────────
def _run(app, port):
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    specs = [
        (auth_app,    8081, "auth-service         /health"),
        (gateway_app, 8082, "api-gateway          /health"),
        (cache_app,   8083, "cache-service        /ping  "),
        (worker_app,  8084, "worker-service       /status"),
        (notif_app,   8085, "notification-service /health"),
    ]

    threads = []
    for app, port, label in specs:
        t = threading.Thread(target=_run, args=(app, port), daemon=True)
        t.start()
        threads.append(t)
        print(f"  started  {label}  -> http://0.0.0.0:{port}")

    print("All mock services running. Ctrl-C to stop.")
    for t in threads:
        t.join()
