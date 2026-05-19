from src.core.config import settings
import random
import time
from fastapi import FastAPI, Response
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="vLLM Mock Engine")
request_count = 0

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None # User can ask for tokens

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    global request_count
    request_count += 1
    
    # Task 1.10: ENFORCE HARD CAP
    # If user asks for 5000, but cap is 1024, we use 1024.
    user_requested = request.max_tokens or settings.MAX_TOKENS_PER_REQUEST
    actual_max = min(user_requested, settings.MAX_TOKENS_PER_REQUEST)
    
    # Simulate work
    time.sleep(random.uniform(0.1, 0.4)) 
    
    # Verification: Show in the response that we capped it
    return {
        "choices": [{
            "message": {
                "role": "assistant", 
                "content": f"Mock response limited to {actual_max} tokens."
            }
        }],
        "usage": {
            "prompt_tokens": 5, 
            "completion_tokens": actual_max, # Using actual_max here
            "total_tokens": 5 + actual_max
        }
    }

@app.get("/metrics")
async def metrics():
    return Response(
        content=f"vllm_num_requests_running 0\nvllm_total_requests {request_count}",
        media_type="text/plain"
    )