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
Anthropic Admin API (ground truth):
    - anthropic_reported_tokens (gauge: latest Anthropic-reported token usage)
    - anthropic_reported_cost_usd (gauge: latest Anthropic-reported cost)
    - anthropic_usage_last_sync_timestamp (gauge: unix timestamp of last sync)
Template fills:
    - template_fills_completed_total
    - template_fills_failed_total
Chat:
    - chat_messages_total
Extractions:
    - extractions_completed_total
    - extractions_failed_total
External APIs (OpenAI Embeddings):
    - embedding_requests_total
    - embedding_failures_total
    - embedding_retries_total
    - embedding_latency_seconds
    - embedding_token_usage_total
External APIs (Azure Document Intelligence):
    - azure_di_requests_total
    - azure_di_failures_total
    - azure_di_retries_total
    - azure_di_latency_seconds
    - azure_di_pages_processed_total
    - azure_di_cost_usd_total
"""
from prometheus_client import Counter, Histogram, Gauge

# Counters
WORKFLOW_RUNS_COMPLETED = Counter(
    "workflow_runs_completed_total",
    "Total number of workflow runs completed successfully",
    ["workflow_name"]
)

WORKFLOW_RUNS_FAILED = Counter(
    "workflow_runs_failed_total",
    "Total number of workflow runs that failed validation or processing",
    ["workflow_name"]
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
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

EXTRACTION_LATENCY_SECONDS = Histogram(
    "extraction_latency_seconds",
    "Extraction execution latency in seconds",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

TEMPLATE_FILLS_COMPLETED = Counter(
    "template_fills_completed_total",
    "Total completed template fills",
)

TEMPLATE_FILLS_FAILED = Counter(
    "template_fills_failed_total",
    "Total failed template fills",
)

# Chat metrics
CHAT_MESSAGES_TOTAL = Counter(
    "chat_messages_total",
    "Total chat messages",
    ["role"]
)

# Extraction metrics
EXTRACTIONS_COMPLETED = Counter(
    "extractions_completed_total",
    "Total completed extractions",
)

EXTRACTIONS_FAILED = Counter(
    "extractions_failed_total",
    "Total failed extractions",
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

# Document cache metrics
DOC_CACHE_HITS = Counter(
    "doc_cache_hits_total",
    "Total document cache hits",
    ["cache_type"]  # redis, file
)

DOC_CACHE_MISSES = Counter(
    "doc_cache_misses_total",
    "Total document cache misses",
    ["cache_type"]  # redis, file
)

# Conversation summary cache metrics
SUMMARY_CACHE_HITS = Counter(
    "summary_cache_hits_total",
    "Conversation summary cache hits"
)

SUMMARY_CACHE_MISSES = Counter(
    "summary_cache_misses_total",
    "Conversation summary cache misses"
)

# --- External API observability: OpenAI Embeddings ---
EMBEDDING_REQUESTS_TOTAL = Counter(
    "embedding_requests_total",
    "Total OpenAI embedding API requests",
    ["model"],
)

EMBEDDING_FAILURES_TOTAL = Counter(
    "embedding_failures_total",
    "Total OpenAI embedding API failures",
    ["model", "error_type"],  # error_type: rate_limit, overload, timeout, other
)

EMBEDDING_RETRIES_TOTAL = Counter(
    "embedding_retries_total",
    "Total OpenAI embedding API retries",
    ["model"],
)

EMBEDDING_LATENCY_SECONDS = Histogram(
    "embedding_latency_seconds",
    "OpenAI embedding API call latency in seconds",
    ["model"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

EMBEDDING_TOKEN_USAGE = Counter(
    "embedding_token_usage_total",
    "Total tokens used by OpenAI embedding API",
    ["model"],
)

# --- External API observability: Azure Document Intelligence ---
AZURE_DI_REQUESTS_TOTAL = Counter(
    "azure_di_requests_total",
    "Total Azure Document Intelligence API requests",
    ["model"],
)

AZURE_DI_FAILURES_TOTAL = Counter(
    "azure_di_failures_total",
    "Total Azure Document Intelligence API failures",
    ["model", "error_type"],  # error_type: rate_limit, timeout, azure_error, other
)

AZURE_DI_RETRIES_TOTAL = Counter(
    "azure_di_retries_total",
    "Total Azure Document Intelligence API retries",
    ["model"],
)

AZURE_DI_LATENCY_SECONDS = Histogram(
    "azure_di_latency_seconds",
    "Azure Document Intelligence API call latency in seconds",
    ["model"],
    buckets=(1, 2, 5, 10, 30, 60, 120, 300),
)

AZURE_DI_PAGES_PROCESSED = Counter(
    "azure_di_pages_processed_total",
    "Total pages processed by Azure Document Intelligence",
    ["model"],
)

AZURE_DI_COST_USD = Counter(
    "azure_di_cost_usd_total",
    "Total Azure Document Intelligence cost in USD",
    ["model"],
)

# Security metrics
HTTP_REQUESTS_RATE_LIMITED = Counter(
    "http_requests_rate_limited_total",
    "Total requests blocked due to rate limiting",
    ["path"]
)

HTTP_SUSPICIOUS_REQUESTS = Counter(
    "http_suspicious_requests_total",
    "Total suspicious requests detected (XSS, scans, etc.)",
    ["pattern"]
)

# Anthropic Admin API metrics (ground truth data from billing system)
ANTHROPIC_REPORTED_TOKENS = Gauge(
    "anthropic_reported_tokens",
    "Token usage as reported by Anthropic Admin API (latest snapshot)",
    ["model", "token_type"],  # token_type: input, output, cache_read, cache_write
    multiprocess_mode='max'
)

ANTHROPIC_REPORTED_COST_USD = Gauge(
    "anthropic_reported_cost_usd",
    "Cost in USD as reported by Anthropic Admin API (latest snapshot)",
    ["model"],
    multiprocess_mode='max'
)

ANTHROPIC_USAGE_LAST_SYNC = Gauge(
    "anthropic_usage_last_sync_timestamp",
    "Unix timestamp of last successful Anthropic usage sync",
    multiprocess_mode='max'
)

def init_labeled_metrics():
    """Pre-register labeled metrics so they appear in /metrics before first use.

    Prometheus labeled counters only produce time series after .labels() is called.
    Calling .labels(...) with initial values creates the series at 0.0.
    """
    WORKFLOW_RUNS_COMPLETED.labels(workflow_name="unknown")
    WORKFLOW_RUNS_FAILED.labels(workflow_name="unknown")
    CHAT_MESSAGES_TOTAL.labels(role="user")
    CHAT_MESSAGES_TOTAL.labels(role="assistant")
    LLM_REQUESTS_TOTAL.labels(model="unknown")
    LLM_TOKEN_USAGE.labels(model="unknown", token_type="input")
    LLM_COST_USD.labels(model="unknown")
    EXPORT_REQUESTS.labels(format="unknown", delivery="unknown")
    DOC_CACHE_HITS.labels(cache_type="redis")
    DOC_CACHE_MISSES.labels(cache_type="redis")
    HTTP_REQUESTS_RATE_LIMITED.labels(path="unknown")
    HTTP_SUSPICIOUS_REQUESTS.labels(pattern="unknown")
    # External API metrics pre-registration
    EMBEDDING_REQUESTS_TOTAL.labels(model="text-embedding-3-small")
    EMBEDDING_FAILURES_TOTAL.labels(model="text-embedding-3-small", error_type="other")
    EMBEDDING_RETRIES_TOTAL.labels(model="text-embedding-3-small")
    EMBEDDING_LATENCY_SECONDS.labels(model="text-embedding-3-small")
    EMBEDDING_TOKEN_USAGE.labels(model="text-embedding-3-small")
    AZURE_DI_REQUESTS_TOTAL.labels(model="prebuilt-layout")
    AZURE_DI_FAILURES_TOTAL.labels(model="prebuilt-layout", error_type="other")
    AZURE_DI_RETRIES_TOTAL.labels(model="prebuilt-layout")
    AZURE_DI_LATENCY_SECONDS.labels(model="prebuilt-layout")
    AZURE_DI_PAGES_PROCESSED.labels(model="prebuilt-layout")
    AZURE_DI_COST_USD.labels(model="prebuilt-layout")


__all__ = [
    "WORKFLOW_RUNS_COMPLETED",
    "WORKFLOW_RUNS_FAILED",
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
    "DOC_CACHE_HITS",
    "DOC_CACHE_MISSES",
    "SUMMARY_CACHE_HITS",
    "SUMMARY_CACHE_MISSES",
    "HTTP_REQUESTS_RATE_LIMITED",
    "HTTP_SUSPICIOUS_REQUESTS",
    "EMBEDDING_REQUESTS_TOTAL",
    "EMBEDDING_FAILURES_TOTAL",
    "EMBEDDING_RETRIES_TOTAL",
    "EMBEDDING_LATENCY_SECONDS",
    "EMBEDDING_TOKEN_USAGE",
    "AZURE_DI_REQUESTS_TOTAL",
    "AZURE_DI_FAILURES_TOTAL",
    "AZURE_DI_RETRIES_TOTAL",
    "AZURE_DI_LATENCY_SECONDS",
    "AZURE_DI_PAGES_PROCESSED",
    "AZURE_DI_COST_USD",
    "ANTHROPIC_REPORTED_TOKENS",
    "ANTHROPIC_REPORTED_COST_USD",
    "ANTHROPIC_USAGE_LAST_SYNC",
    "init_labeled_metrics",
]
