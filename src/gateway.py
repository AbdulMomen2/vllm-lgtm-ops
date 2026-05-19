from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from src.api.v1.chat import router as chat_router 

app = FastAPI(title="Industrial LLM Gateway")

# Task 2.2: THE EYES
Instrumentator().instrument(app).expose(app)

# 🚦 THE FIX: Instead of writing @app.post here, we "Include" the router.
# FastAPI will automatically look inside src/api/v1/chat.py 
# and find the @router.post("/chat") endpoint.
app.include_router(chat_router)

@app.get("/health")
async def health():
    return {"status": "ok"}