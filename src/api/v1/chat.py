from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from src.core.security import validate_user
from src.services.token_service import token_service
from src.metrics.custom_metrics import TOKEN_USAGE_COUNTER, CACHE_HIT_COUNTER
from src.services.rate_limiter import rate_limiter
from prometheus_client import Counter
from src.core.config import settings
from src.core.models import LLMJob
import hashlib
import json
import secrets

router = APIRouter(prefix="/v1")

class ChatRequest(BaseModel):
    message: str
    model: str = "mistral-7b"
    max_tokens: Optional[int] = None

class KeyGenerationRequest(BaseModel):
    team_name: str
    max_tokens_limit: Optional[int] = None

THROTTLED_REQUESTS = Counter(
    "llm_gateway_throttled_requests_total",
    "Total number of 429 errors issued",
    ["team_name"]
)

@router.post("/chat")
async def chat_endpoint(payload: ChatRequest, team: str = Depends(validate_user)):
    # 1. AUTH & RATE LIMIT (Task 2.6) - Block spam immediately
    if await rate_limiter.is_rate_limited(team):
        THROTTLED_REQUESTS.labels(team_name=team).inc()
        raise HTTPException(status_code=429, detail="Too many requests. Your 4090 is busy!")
    
    # 2. TOKEN CALCULATION (Task 2.4)
    prompt_tokens = token_service.count_tokens(payload.message)
    queue_depth = await rate_limiter.r.llen("jobs:pending")
    cache_key = hashlib.md5(f"{payload.model}:{payload.message}".encode()).hexdigest()
    cached_result = await rate_limiter.r.get(f"cache:{cache_key}")

    # 3. SAFETY CHECK (Task 1.10) - FAIL FAST
    # Don't add to queue if the prompt is too long for our 4090 settings
    if prompt_tokens > 1000:
        raise HTTPException(status_code=400, detail=f"Prompt too long ({prompt_tokens} tokens). Max is 1000.")
    
   
    if queue_depth > 50:
        raise HTTPException(
            status_code=503, 
            detail="System Overloaded. Queue is full. Please try again in 5 minutes."
        )
    
    
    if cached_result:
        # Task 3.5: (Monitoring Task) Log a Cache Hit
        print(f"💎 Cache Hit for {team}! Saving GPU time.")
        CACHE_HIT_COUNTER.labels(team_name=team, status="hit").inc()
        return json.loads(cached_result)
    
    # Cache Miss
    CACHE_HIT_COUNTER.labels(team_name=team, status="miss").inc()
    # 4. MONITORING (Task 2.5) - Log usage before processing
    TOKEN_USAGE_COUNTER.labels(team_name=team, model=payload.model).inc(prompt_tokens)

    # 5. QUEUEING (Task 3.3) - Hand off to Redis
    # We ensure LLMJob is created with a unique ID and a fully non-hardcoded dynamic max_tokens
    # 5.1 Fetch dynamic max limit for this specific team from Redis
    try:
        limit_data = await rate_limiter.r.hget("team_limits", team)
        max_limit = int(limit_data) if limit_data else settings.MAX_TOKENS_PER_REQUEST
    except Exception:
        max_limit = settings.MAX_TOKENS_PER_REQUEST

    requested_max_tokens = payload.max_tokens or max_limit
    if requested_max_tokens > max_limit:
        raise HTTPException(
            status_code=400,
            detail=f"Requested max_tokens ({requested_max_tokens}) exceeds the dynamic cap of {max_limit} for team {team}."
        )

    job = LLMJob(
        team_name=team,
        model=payload.model,
        prompt=payload.message,
        max_tokens=requested_max_tokens
    )
    
    # Industrial Tip: Serialize to JSON string for Redis
    await rate_limiter.r.lpush("jobs:pending", job.model_dump_json())
    
    # 6. RESPONSE - Return the Job ID
    return {
        "job_id": job.job_id,
        "status": "queued",
        "team": team,
        "prompt_tokens": prompt_tokens,
        "tokens": prompt_tokens
    }

@router.get("/result/{job_id}")
async def get_result(job_id: str):
    # Task 4.6: Result Publisher (Retrieval side)
    result = await rate_limiter.r.get(f"result:{job_id}")
    
    if not result:
        # Check if it's still in the queue
        # Industrial logic: Tell the user to keep waiting or if it's missing
        return {"job_id": job_id, "status": "pending", "message": "Still in the oven..."}
    
    return {
        "job_id": job_id, 
        "status": "completed", 
        "result": json.loads(result)
    }

@router.post("/keys/generate")
async def generate_api_key(payload: KeyGenerationRequest, team: str = Depends(validate_user)):
    # Admin/Security check: Dynamic key generation can be done by authorized teams
    new_key = f"vllm_{secrets.token_hex(16)}"
    
    # Save the key-to-team mapping dynamically to Redis
    await rate_limiter.r.hset("api_keys", new_key, payload.team_name)
    
    # Save the dynamic custom token limit dynamically to Redis
    if payload.max_tokens_limit:
        await rate_limiter.r.hset("team_limits", payload.team_name, payload.max_tokens_limit)
        
    return {
        "api_key": new_key,
        "team_name": payload.team_name,
        "max_tokens_limit": payload.max_tokens_limit or settings.MAX_TOKENS_PER_REQUEST
    }