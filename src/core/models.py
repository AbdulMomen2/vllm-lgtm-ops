from pydantic import BaseModel, Field
import uuid
import time

class LLMJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    team_name: str
    model: str
    prompt: str
    max_tokens: int
    created_at: float = Field(default_factory=time.time)
    # To track how long it sits in the queue
    arrival_time: float = Field(default_factory=time.time)