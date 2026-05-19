# 🚀 Production-Grade vLLM RTX 4090 Telemetry Stack (`vllm-lgtm-ops`)

An industrial-grade, single-node LLMOps telemetry, queue, and worker architecture designed specifically to extract maximum performance from a single **NVIDIA RTX 4090 (24GB VRAM)** GPU (e.g., deployed on **RunPod**).

This stack implements a fully comprehensive **LGTM Lite monitoring suite** (Loki, Grafana, Promtail, Prometheus) to ensure hardware safety, key-based token billing, and end-to-end tracing without enterprise bloat.

---

## 🏛️ In-Depth Architecture & Request Lifecycle

Below is the detailed flow of a chat completion request through the entire system:

```
               [ User Client ]
                      │
                      │ 1. POST /v1/chat (with API Key)
                      ▼
             [ FastAPI Gateway ]
             (src/gateway.py)
                      │
                      ├─► [ 2. API Key Authentication ] (src/core/security.py)
                      ├─► [ 3. Tiktoken Token Estimation ] (src/services/token_service.py)
                      ├─► [ 4. Redis Rate-Limiter (Token Bucket) ] (src/services/rate_limiter.py)
                      │
                      ▼
             [ 5. Exact Match Cache ] ◄──► [ Redis DB (0) ]
             (src/api/v1/chat.py)
                      │
                      ├─► (Cache Hit) ──► [ Return Cached Response Instantly ]
                      │
                      └─► (Cache Miss)
                               │
                               │ 6. Push to reliable queue: jobs:pending
                               ▼
                        [ Redis Queue ] (BRPOPLPUSH)
                               │
            ┌──────────────────┴──────────────────┐
            │ 7. BRPOPLPUSH jobs:pending -> processing
            ▼                                     ▼
     [ worker-1.py ]                       [ worker-2.py ]
    (src/worker.py)                       (src/worker.py)
            │                                     │
            ├─► [ 8. Track active threads ]       ├─► [ 8. Track active threads ]
            ├─► [ 9. Measure queue wait-time ]    ├─► [ 9. Measure queue wait-time ]
            ├─► [ 10. OpenTelemetry Span ]        ├─► [ 10. OpenTelemetry Span ]
            │                                     │
            ▼                                     ▼
    [ Real GPU vLLM ] ◄─── (Auto-Detect) ───► [ Mock Engine ]
     (Port 8000)                               (Port 8000)
            │                                     │
            └──────────────────┬──────────────────┘
                               │ 11. Write result to redis & clean processing list
                               ▼
                       [ Return Output ] ──► [ Langfuse / Prometheus Logs ]
```

---

## 📂 Detailed Component Directory Layout

Every module corresponds to a clean, decoupled implementation file:

```
vllm-lgtm-ops/
├── docker-compose.yml       # Base core services (Redis, Gateway, Worker, Prometheus, Loki, Grafana)
├── docker-compose.gpu.yml   # NVIDIA Exporter & GPU capability hardware reservations
├── prometheus.yml           # Scraper configs for all endpoints (Gateway, Worker, Redis, GPU, cAdvisor)
├── promtail-config.yaml     # Promtail log pipeline configuration (injects container names to Loki)
├── entrypoint.sh            # Smart bootstrapper (autodetects GPU presence & boots real/mock engine)
├── requirements.txt         # Pinned production dependencies (FastAPI, Redis, Tiktoken, Langfuse, Httpx)
│
├── src/
│   ├── gateway.py           # Core Gateway API service exposing Prometheus Metrics Instrumentator
│   │
│   ├── api/v1/
│   │   └── chat.py          # OpenAI-compatible completions router (Rate Limiting, Cache Hits, Queueing)
│   │
│   ├── core/
│   │   ├── config.py        # Pydantic Settings class with validation & fallback definitions
│   │   ├── security.py      # Hardened API Key database and bearer verification logic
│   │   └── models.py        # Pydantic request/response model definitions
│   │
│   ├── metrics/
│   │   └── custom_metrics.py# Unified custom Prometheus Counter, Gauge, and Histogram registers
│   │
│   ├── services/
│   │   ├── rate_limiter.py  # Redis Token Bucket sliding window algorithm for individual teams
│   │   └── token_service.py # Tiktoken model counting services supporting Mistral encoders
│   │
│   ├── engine_sim.py        # CPU Mock OpenAI-compatible server (used as local fallback)
│   ├── warmup.py            # Model pre-warming script to prevent Cold Starts / TTFT lag
│   └── worker.py            # Reliable BRPOPLPUSH Worker with OpenTelemetry spans & JSON Logging
│
└── grafana/
    └── provisioning/        # Automated Grafana Datasource & Dashboard auto-loaders
        ├── datasources/
        │   └── datasource.yml
        └── dashboards/
            ├── dashboard_provisioning.yml
            └── llmops_dashboard.json
```

---

## 🎨 In-Depth Telemetry Specs & Custom Metrics

Our system exposes deep observability metrics scraped by Prometheus every **5 seconds**:

### 1. Application-Level Metrics (`gateway` & `worker`)

| Metric Name | Type | Labels | Description |
| :--- | :--- | :--- | :--- |
| `llm_cache_hits_total` | **Counter** | `status` (hit/miss), `team_name` | Measures database savings and GPU-time bypasses. |
| `llm_user_token_usage_total` | **Counter** | `team_name` | Tracks Tiktoken consumption per user API key for billing. |
| `llm_gateway_throttled_requests_total` | **Counter** | `team_name` | Measures the volume of throttled requests (429s). |
| `llm_queue_wait_seconds` | **Histogram**| `team_name` | Custom-bucketed tracking of request latency inside the FIFO queue. |
| `llm_active_worker_threads` | **Gauge** | *None* | Tracks real-time worker capacity utilization (should never exceed 4). |
| `llm_worker_errors_total` | **Counter** | `team_name`, `error_type`| Classifies and logs inference failures. |

### 2. Infrastructure Exporter Metrics
* **NVIDIA DCGM Exporter (`gpu-exporter:9400`):**
  * `DCGM_FI_DEV_GPU_TEMP`: GPU Core Temperature (°C).
  * `DCGM_FI_DEV_POWER_USAGE`: Real-time wattage draw (W).
  * `DCGM_FI_DEV_FB_USED`: Active VRAM consumption (Bytes).
* **Redis Exporter (`redis-exporter:9121`):**
  * `redis_db_keys`: Total cached records in memory.
  * `redis_connected_clients`: Active client connections.
* **cAdvisor (`cadvisor:8080`):**
  * `container_cpu_usage_seconds_total`: Real-time CPU usage per container.
  * `container_memory_usage_bytes`: RAM usage per container.

---

## 📝 Structured Logging Schema (Loki-Ready)

The worker outputs standardized **JSON** logs specifically structured for Promtail to parse and push into **Loki**. 

### Standard Worker Log Output:
```json
{
  "asctime": "2026-05-19 06:33:16,516", 
  "levelname": "INFO", 
  "message": "🎯 Worker picked up job", 
  "job_id": "8943c18c-aeef-4083-8e3d-04a426b2db63", 
  "team": "Beta_Team", 
  "tokens": 50, 
  "trace_id": "8a85038f4355db58761a49987ac58955"
}
```
This lets you log query specific transaction logs simply by filtering on `{container_name="worker"} |= "8a85038f4355db58761a49987ac58955"` inside Grafana!

---

## 🛠️ CLI Operations Manual

### 1. Run Stack Locally (CPU / Simulation Mode)
Launches all services on local CPU with mock engine fallback:
```bash
docker compose up -d --build
```

### 2. Run Stack in Production (RunPod GPU Mode)
Binds host GPU resources, limits vLLM to the 4090 capacity, and launches the NVIDIA metrics exporter:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

### 3. Monitoring & Management
```bash
# Check service states
docker compose ps

# Check vLLM engine auto-detection logs
docker compose logs llm-engine

# View active log streams
docker compose logs -f gateway worker

# Inspect Prometheus health targets
curl http://localhost:9090/api/v1/targets

# Stop and wipe all data volumes
docker compose down -v
```

---

## 🚀 Step-by-Step RunPod Deployment

For complete, step-by-step instructions on setting up your pod, exposing external network ports, and launching this repository on **RunPod**, please refer to the detailed [Production RunPod Deployment Guide](file:///home/momen/.gemini/antigravity/brain/80d4a7e8-9ac9-4f82-9d99-c009a38f4041/runpod_deployment_guide.md).
