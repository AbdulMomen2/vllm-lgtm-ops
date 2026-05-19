from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):
    # Industrial Tip: Always version your environment
    ENV: Literal["dev", "prod"] = "dev"
    
    # Toggle between Mock and Real vLLM
    ENGINE_MODE: Literal["mock", "vllm"] = "mock"
    
    # Engine Settings
    MODEL_NAME: str = "mistralai/Mistral-7B-Instruct-v0.2"
    MAX_MODEL_LEN: int = 8192
    GPU_UTILIZATION: float = 0.85
    MAX_CONCURRENT_SEQS: int = 4
    MAX_TOKENS_PER_REQUEST: int = 1024  # Hard cap for 4090 sanity
    DEFAULT_TEMPERATURE: float = 0.7

    REDIS_URL: str = "redis://redis:6379/0"
    RATE_LIMIT_PER_MINUTE: int = 5
    API_KEYS: str = '{"team-alpha-123": "Alpha_Team", "team-beta-456": "Beta_Team"}'

    class Config:
        env_file = ".env"

settings = Settings()