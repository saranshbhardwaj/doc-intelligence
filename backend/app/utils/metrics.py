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
LLM observability:
    - llm_cache_hits_total
    - llm_cache_misses_total
    - llm_requests_total (label: model)
    - llm_token_usage_total (labels: model, token_type)
    - llm_cost_usd_total (label: model)
Template fills:
    - template_fills_completed_total
    - template_fills_failed_total
Chat:
    - chat_messages_total
Extractions:
    - extractions_completed_total
    - extractions_failed_total
"""
from prometheus_client import Counter, Histogram

# Counters
WORKFLOW_RUNS_COMPLETED = Counter(
    "workflow_runs_completed_total",
    "Total number of workflow runs completed successfully",
    ["org_id", "workflow_name"]
)

WORKFLOW_RUNS_FAILED = Counter(
    "workflow_runs_failed_total",
    "Total number of workflow runs that failed validation or processing",
    ["org_id", "workflow_name"]
)

WORKFLOW_RUNS_PARTIAL = Counter(
    "workflow_runs_partial_total",
    "Total number of workflow runs that produced partial artifacts",
)

# Latency histogram in seconds
WORKFLOW_LATENCY_SECONDS = Histogram(
    "workflow_run_latency_seconds",
    "Histogram of workflow run latency in seconds",
    ["workflow_name"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

CHAT_LATENCY_SECONDS = Histogram(
    "chat_latency_seconds",
    "Histogram of chat response latency in seconds",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

TEMPLATE_FILL_LATENCY_SECONDS = Histogram(
    "template_fill_latency_seconds",
    "Template fill execution latency in seconds",
    ["org_id"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

EXTRACTION_LATENCY_SECONDS = Histogram(
    "extraction_latency_seconds",
    "Extraction execution latency in seconds",
    ["org_id"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

TEMPLATE_FILLS_COMPLETED = Counter(
    "template_fills_completed_total",
    "Total completed template fills",
    ["org_id"]
)

TEMPLATE_FILLS_FAILED = Counter(
    "template_fills_failed_total",
    "Total failed template fills",
    ["org_id"]
)

# Chat metrics (NEW - for dashboard)
CHAT_MESSAGES_TOTAL = Counter(
    "chat_messages_total",
    "Total chat messages",
    ["role", "org_id"]
)

# Extraction metrics (NEW - for dashboard)
EXTRACTIONS_COMPLETED = Counter(
    "extractions_completed_total",
    "Total completed extractions",
    ["org_id"]
)

EXTRACTIONS_FAILED = Counter(
    "extractions_failed_total",
    "Total failed extractions",
    ["org_id"]
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

# LLM observability metrics
LLM_CACHE_HITS = Counter(
    "llm_cache_hits_total",
    "Total number of LLM cache hits (prompt caching)"
)

LLM_CACHE_MISSES = Counter(
    "llm_cache_misses_total",
    "Total number of LLM cache misses"
)

LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "Total number of LLM API requests",
    ["model"]
)

LLM_TOKEN_USAGE = Counter(
    "llm_token_usage_total",
    "Total LLM tokens used by model and type",
    ["model", "token_type"]  # token_type: input, output, cache_read, cache_write
)

LLM_COST_USD = Counter(
    "llm_cost_usd_total",
    "Total LLM cost in USD",
    ["model"]
)

# Security metrics
HTTP_REQUESTS_RATE_LIMITED = Counter(
    "http_requests_rate_limited_total",
    "Total requests blocked due to rate limiting",
    ["client_ip", "path"]
)

HTTP_SUSPICIOUS_REQUESTS = Counter(
    "http_suspicious_requests_total",
    "Total suspicious requests detected (XSS, scans, etc.)",
    ["client_ip", "pattern"]
)

__all__ = [
    "WORKFLOW_RUNS_COMPLETED",
    "WORKFLOW_RUNS_FAILED",
    "WORKFLOW_RUNS_PARTIAL",
    "WORKFLOW_LATENCY_SECONDS",
    "CHAT_LATENCY_SECONDS",
    "TEMPLATE_FILL_LATENCY_SECONDS",
    "EXTRACTION_LATENCY_SECONDS",
    "TEMPLATE_FILLS_COMPLETED",
    "TEMPLATE_FILLS_FAILED",
    "CHAT_MESSAGES_TOTAL",
    "EXTRACTIONS_COMPLETED",
    "EXTRACTIONS_FAILED",
    "ARTIFACT_PERSIST_SECONDS",
    "ARTIFACT_PERSIST_FAILURES",
    "EXPORT_GENERATION_SECONDS",
    "EXPORT_R2_STORE_SECONDS",
    "EXPORT_R2_FAILURES",
    "EXPORT_REQUESTS",
    "EXPORT_BYTES_TOTAL",
    "LLM_CACHE_HITS",
    "LLM_CACHE_MISSES",
    "LLM_REQUESTS_TOTAL",
    "LLM_TOKEN_USAGE",
    "LLM_COST_USD",
    "HTTP_REQUESTS_RATE_LIMITED",
    "HTTP_SUSPICIOUS_REQUESTS",
]
