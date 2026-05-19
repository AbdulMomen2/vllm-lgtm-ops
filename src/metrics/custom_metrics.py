from prometheus_client import Counter, Histogram, Gauge

# Task 2.5: User Billing Metric
TOKEN_USAGE_COUNTER = Counter(
    "llm_user_token_usage_total",
    "Total tokens consumed by user",
    ["team_name", "model"]
)

# Task 3.5: Cache Hit Metric
CACHE_HIT_COUNTER = Counter(
    "llm_cache_hits_total",
    "Total cache hits and misses",
    ["team_name", "status"]  # status = 'hit' or 'miss'
)

# Task 3.6: Queue Wait Time Metric
QUEUE_WAIT_TIME = Histogram(
    "llm_queue_wait_seconds",
    "Time spent in the pending queue in seconds",
    ["team_name"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, float("inf"))
)

# Task 4.5: Worker/vLLM Error Rate Metric
WORKER_ERROR_COUNTER = Counter(
    "llm_worker_errors_total",
    "Total number of worker execution errors",
    ["team_name", "error_type"]
)

# Task 4.10: Active Worker Threads Metric
ACTIVE_WORKERS_GAUGE = Gauge(
    "llm_active_worker_threads",
    "Number of active worker threads processing jobs",
    ["worker_id"]
)