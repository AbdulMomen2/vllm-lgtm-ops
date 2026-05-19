# 🚀 vLLM RTX 4090 Telemetry & Monitoring Stack (`vllm-lgtm-ops`)

An industrial-grade, highly optimized LLMOps gateway, queue, and worker architecture designed specifically to extract maximum performance from a single **NVIDIA RTX 4090 (24GB VRAM)** GPU (e.g., deployed on **RunPod**).

This stack implements a fully comprehensive **LGTM Lite monitoring suite** (Loki, Grafana, Promtail, Prometheus) to ensure hardware safety, key-based token billing, and end-to-end tracing without enterprise bloat.

---

## 🏛️ System Architecture

```
                 [ User Request ]
                        │
                        ▼
                 [ API Gateway ]  ◄──►  [ Redis Cache ]
                        │
                 (BRPOPLPUSH Queue)
                        │
                        ▼
                 [ Worker Pool ]
                        │
             (Langfuse v4 OpenTelemetry)
                        │
                        ▼
        ┌────────────────────────────────┐
        │        llm-engine Pod          │
        ├────────────────────────────────┤
        │  Auto-Detecting Bootstrapper:  │
        │  - GPU: vLLM OpenAI Server     │
        │  - CPU: Fast mock-engine       │
        └────────────────────────────────┘
```

---

## ✨ Features Implemented

1. **Hybrid Auto-Detecting Engine (`entrypoint.sh`):** Bypasses mock services and automatically boots the real vLLM engine (`Mistral-7B-Instruct-v0.2`) on port `8000` with optimized parameters (`--gpu-memory-utilization 0.85`, `--max-num-seqs 4`) the second an NVIDIA card is found.
2. **Reliable Redis Queuing:** Utilizes `BRPOPLPUSH` FIFO list processing with automated queue depth limits, Job TTLs, and a dedicated **Dead Letter Queue (DLQ)** for failed inferences.
3. **OpenTelemetry Tracing:** Tracks worker actions with modern **Langfuse v4** context-manager spans and generations.
4. **Structured JSON Logs (Loki-Ready):** Worker outputs structured logs injected with exact trace IDs and job IDs for central indexing.
5. **Integrated LGTM Lite Monitoring:**
   * **NVIDIA DCGM Exporter:** Exposes real-time VRAM, temperature, and power metrics.
   * **Redis Exporter:** Exposes queue backlog and memory metrics.
   * **cAdvisor:** Tracks CPU/RAM of each container dynamically.
   * **FastAPI Instrumentator:** Logs HTTP metrics and cache hit ratios.
6. **Pre-Provisioned Grafana Dashboards:** Automatically loads a complete system dashboard on container start (zero manual UI clicks needed).

---

## 🛠️ CLI Reference Guide

### 1. Build and Run locally (CPU / Simulation Mode)
Runs the entire stack with the mock engine fallback enabled (no GPU needed):
```bash
docker compose up -d --build
```

### 2. Build and Run in Production (GPU Mode)
Binds the GPU reservations and activates the live NVIDIA exporter:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

### 3. General Maintenance Commands
```bash
# Check service health and container states
docker compose ps

# Check vLLM engine auto-detection logs
docker compose logs llm-engine

# Inspect live worker json log lines
docker compose logs worker

# Tear down the stack and delete active volumes
docker compose down -v
```

---

## 🚦 API Reference

### 1. Gateway Health Check
* **Endpoint:** `GET /health`
* **Response:** `{"status": "ok"}`

### 2. OpenAI-Compatible Chat Endpoint
* **Endpoint:** `POST /v1/chat`
* **Headers:**
  * `Authorization: Bearer <API_KEY>` (e.g. `team-alpha-123` or `team-beta-456`)
* **Request Payload:**
  ```json
  {
    "model": "mistralai/Mistral-7B-Instruct-v0.2",
    "messages": [
      {"role": "user", "content": "Explain gravity in one sentence."}
    ]
  }
  ```
* **Response Payload:** Standard OpenAI completions format.

---

## 📊 Live Monitoring Port Mapping

When the stack is running, access these ports on your host IP:

* **Grafana Dashboard:** `http://localhost:3000` (Default credentials: `admin` / Password set in `.env`)
* **cAdvisor Metrics:** `http://localhost:8081`
* **Prometheus Targets:** `http://localhost:9090`
* **vLLM Engine Port:** `http://localhost:8000`
