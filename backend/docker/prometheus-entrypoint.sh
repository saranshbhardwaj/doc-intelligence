#!/bin/sh
set -e

# Substitute env vars into the Prometheus template config, then start Prometheus.
# Required env vars:
#   GRAFANA_CLOUD_REMOTE_WRITE_URL
#   GRAFANA_CLOUD_METRICS_USER_ID
#   GRAFANA_CLOUD_API_KEY

envsubst < /etc/prometheus/prometheus.template.yml > /etc/prometheus/prometheus.yml

exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --storage.tsdb.retention.time=2h \
  "$@"
