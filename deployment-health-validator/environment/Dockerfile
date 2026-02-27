FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir flask==3.0.3 requests==2.32.3 pyyaml==6.0.2

COPY * /app/

# Start mock services in the background, then busy-wait until auth-service
# responds before entering sleep infinity.  This guarantees all five mock
# services are bound and ready before harbor execs the agent or oracle.
CMD ["/bin/bash", "-c", \
     "python /app/mock_services.py > /tmp/mock_services.log 2>&1 & \
      until curl -sf http://localhost:8081/health > /dev/null 2>&1; do sleep 1; done && \
      sleep infinity"]
