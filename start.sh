#!/bin/sh
set -e

# Apply database migrations first when asked to. Prefer running `alembic upgrade head`
# as a one-off release / pre-deploy step instead if several instances start at once.
if [ "$RUN_MIGRATIONS" = "true" ]; then
    alembic upgrade head
fi

# --proxy-headers: trust X-Forwarded-For from the host's load balancer, so rate limits see real client IPs
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-5000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
