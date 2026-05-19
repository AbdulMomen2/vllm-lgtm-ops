#!/bin/bash

# 1. Detect if an NVIDIA GPU is available
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo "🎮 [llm-engine] NVIDIA GPU Detected! Booting real production vLLM engine..."
    # Launch real vLLM engine as a module (exposing OpenAPI endpoints on 8000)
    python -m vllm.entrypoints.openai.api_server \
        --model mistralai/Mistral-7B-Instruct-v0.2 \
        --gpu-memory-utilization 0.85 \
        --max-num-seqs 4 \
        --host 0.0.0.0 \
        --port 8000 &
else
    echo "💻 [llm-engine] No NVIDIA GPU found or nvidia-smi failed. Booting Mock LLM Engine..."
    uvicorn src.engine_sim:app --host 0.0.0.0 --port 8000 &
fi

# 2. Wait a few seconds for the server to bind to the port
sleep 2

# 3. Run the Warmup script
# This ensures the engine is 'hot' before we consider the container 'Ready'
python src/warmup.py

# 4. Bring the background process back to the foreground to keep the container alive
wait -n