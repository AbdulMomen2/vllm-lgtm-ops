import time
import json
import httpx
import redis
import hashlib
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import langfuse
from prometheus_client import start_http_server
from src.core.config import settings
from src.core.models import LLMJob
from src.metrics.custom_metrics import (
    QUEUE_WAIT_TIME,
    WORKER_ERROR_COUNTER,
    ACTIVE_WORKERS_GAUGE
)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
# Why we need this: To turn the 'extra' dict into searchable JSON fields for Loki
from pythonjsonlogger import jsonlogger 

# --- 1. SETUP STRUCTURED LOGGING ---
# Why: Standard logging prints text. JSON logging prints data that Loki can index.
logger = logging.getLogger("worker")
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(message)s %(job_id)s %(team)s %(tokens)s %(trace_id)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# --- 2. INITIALIZE SERVICES ---
# Modern Langfuse v4 Client Initialization
client = langfuse.get_client()

r = redis.from_url(settings.REDIS_URL, decode_responses=True)

# --- 3. ENGINE CALL (RETRY LOGIC) ---
# Trade-off: We only retry Network/HTTP errors. If the prompt is "Bad Request", we don't retry.
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    reraise=True
)
def call_engine(job: LLMJob):
    """Hits the vLLM engine with retry logic."""
    engine_url = os.getenv("LLM_ENGINE_URL", "http://llm-engine:8000")
    with httpx.Client(timeout=60.0) as client_http:
        response = client_http.post(
            f"{engine_url}/v1/chat/completions",
            json={
                "model": job.model,
                "messages": [{"role": "user", "content": job.prompt}],
                "max_tokens": job.max_tokens,
                "temperature": 0.7
            }
        )
        response.raise_for_status()
        return response.json()

# --- 4. THE CORE PROCESSOR ---
def process_job(job_raw_data: str):
    """Processes a job: Tracing (Langfuse v4) + Logging (Loki) + Logic (4090)"""
    try:
        # Create the 'job' object from raw Redis string
        job_dict = json.loads(job_raw_data)
        job = LLMJob(**job_dict)
        
        # Track worker thread occupancy
        worker_id = threading.current_thread().name
        ACTIVE_WORKERS_GAUGE.labels(worker_id=worker_id).set(1)

        # Measure Queue Wait Time
        wait_time = time.time() - job.arrival_time
        QUEUE_WAIT_TIME.labels(team_name=job.team_name).observe(wait_time)

        # MODERN LANGFUSE V4 TRACING: Context Manager Spans
        with client.start_as_current_observation(
            name="llm-inference",
            as_type="span",
            metadata={"job_id": job.job_id}
        ) as span:
            trace_id = client.get_current_trace_id()

            # INDUSTRIAL LOGGING: This goes to Loki
            # We include 'extra' so you can search for this specific job_id in Grafana
            logger.info(f"🎯 Worker picked up job", extra={
                "job_id": job.job_id, 
                "team": job.team_name,
                "tokens": job.max_tokens,
                "trace_id": trace_id
            })

            try:
                with client.start_as_current_observation(
                    name="vllm-generation",
                    as_type="generation",
                    model=job.model,
                    input=job.prompt
                ) as generation:

                    # 4090 INFERENCE CALL
                    result = call_engine(job)
                    
                    llm_response = result['choices'][0]['message']['content']
                    usage = result.get('usage', {})

                    # Update generation with outputs and token usages
                    generation.update(
                        output=llm_response,
                        usage_details={
                            "input": usage.get("prompt_tokens", 0),
                            "output": usage.get("completion_tokens", 0),
                            "total": usage.get("total_tokens", 0)
                        }
                    )
                
                # PERSISTENCE (Cache & Result Store)
                r.set(f"result:{job.job_id}", json.dumps(result), ex=3600)
                cache_key = hashlib.md5(f"{job.model}:{job.prompt}".encode()).hexdigest()
                r.set(f"cache:{cache_key}", json.dumps(result), ex=86400)
                
                # ATOMIC CLEANUP
                r.lrem("jobs:processing", 1, job_raw_data)
                
                logger.info(f"✅ Job finished successfully", extra={
                    "job_id": job.job_id,
                    "team": job.team_name,
                    "trace_id": trace_id
                })

            except Exception as e:
                # We can update the span level to ERROR
                span.update(level="ERROR", status_message=str(e))
                
                logger.error(f"❌ Job failed", extra={
                    "job_id": job.job_id,
                    "team": job.team_name,
                    "error": str(e),
                    "trace_id": trace_id
                })
                
                # Track failures
                WORKER_ERROR_COUNTER.labels(team_name=job.team_name, error_type=type(e).__name__).inc()
                
                # DEAD LETTER QUEUE (Safety)
                r.lpush("jobs:dlq", json.dumps({"job_id": job.job_id, "error": str(e), "data": job_dict}))
                r.lrem("jobs:processing", 1, job_raw_data)
            finally:
                ACTIVE_WORKERS_GAUGE.labels(worker_id=worker_id).set(0)
    except Exception as e:
        logger.exception("💥 Uncaught exception in process_job thread!")

# --- 5. MAIN LOOP ---
def main_worker_loop():
    logger.info("👷 Worker started. Max Concurrency: 4")
    
    # Start Prometheus Metrics Server on Port 8001
    start_http_server(8001)
    
    # Pre-initialize Gauges for ThreadPoolExecutor threads
    for i in range(4):
        ACTIVE_WORKERS_GAUGE.labels(worker_id=f"ThreadPoolExecutor-0_{i}").set(0)
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        while True:
            # RPOPLPUSH (Reliable Queue)
            job_raw = r.brpoplpush("jobs:pending", "jobs:processing", timeout=2)
            if job_raw:
                executor.submit(process_job, job_raw)
            else:
                time.sleep(0.1)

if __name__ == "__main__":
    main_worker_loop()