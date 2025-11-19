"""Prometheus metrics helpers for workflow & export observability.

Metrics taxonomy:
Workflow lifecycle:
    - workflow_runs_completed_total
    - workflow_runs_failed_total
    - workflow_runs_partial_total
    - workflow_run_latency_seconds
Artifact persistence:
    - artifact_persist_seconds
    - artifact_persist_failures_total
Export operations:
    - export_generation_seconds
    - export_r2_store_seconds
    - export_r2_failures_total
    - export_requests_total (label format)
    - export_bytes_total (counter of bytes delivered/stored)
"""
from prometheus_client import Counter, Histogram

# Counters
WORKFLOW_RUNS_COMPLETED = Counter(
    "workflow_runs_completed_total",
    "Total number of workflow runs completed successfully",
)

WORKFLOW_RUNS_FAILED = Counter(
    "workflow_runs_failed_total",
    "Total number of workflow runs that failed validation or processing",
)

WORKFLOW_RUNS_PARTIAL = Counter(
    "workflow_runs_partial_total",
    "Total number of workflow runs that produced partial artifacts",
)

# Latency histogram in seconds
WORKFLOW_LATENCY_SECONDS = Histogram(
    "workflow_run_latency_seconds",
    "Histogram of workflow run latency in seconds",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

# Artifact persistence
ARTIFACT_PERSIST_SECONDS = Histogram(
    "artifact_persist_seconds",
    "Time to persist workflow artifact (storage or inline)",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5)
)
ARTIFACT_PERSIST_FAILURES = Counter(
    "artifact_persist_failures_total",
    "Total artifact persistence failures"
)

# Export generation timing (conversion JSON->format bytes)
EXPORT_GENERATION_SECONDS = Histogram(
    "export_generation_seconds",
    "Time to generate export file (markdown/docx/xlsx/pdf)",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5)
)
EXPORT_R2_STORE_SECONDS = Histogram(
    "export_r2_store_seconds",
    "Time to store generated export file in R2",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5)
)
EXPORT_R2_FAILURES = Counter(
    "export_r2_failures_total",
    "Total failures storing export file in R2"
)
EXPORT_REQUESTS = Counter(
    "export_requests_total",
    "Total export requests",
    ["format", "delivery"]
)
EXPORT_BYTES_TOTAL = Counter(
    "export_bytes_total",
    "Total bytes generated for exports (streamed or stored)"
)

__all__ = [
    "WORKFLOW_RUNS_COMPLETED",
    "WORKFLOW_RUNS_FAILED",
    "WORKFLOW_RUNS_PARTIAL",
    "WORKFLOW_LATENCY_SECONDS",
    "ARTIFACT_PERSIST_SECONDS",
    "ARTIFACT_PERSIST_FAILURES",
    "EXPORT_GENERATION_SECONDS",
    "EXPORT_R2_STORE_SECONDS",
    "EXPORT_R2_FAILURES",
    "EXPORT_REQUESTS",
    "EXPORT_BYTES_TOTAL",
]
