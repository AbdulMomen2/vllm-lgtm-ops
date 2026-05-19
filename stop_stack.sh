#!/bin/bash

# ==============================================================================
# vLLM LLMOps Telemetry Stack - Native Teardown Script
# ==============================================================================

echo "🛑 Stopping all native LLMOps background services..."

# Kill function
kill_process() {
    local pattern=$1
    local name=$2
    local pids=$(pgrep -f "$pattern")
    if [ -n "$pids" ]; then
        echo "Stopping $name (PIDs: $pids)..."
        kill $pids || kill -9 $pids
    else
        echo "💤 $name is not running."
    fi
}

# 1. Kill Telemetry components
kill_process "prometheus" "Prometheus"
kill_process "loki" "Loki"
kill_process "promtail" "Promtail"
kill_process "grafana-server" "Grafana Server"

# 2. Kill Python applications
kill_process "gateway" "API Gateway"
kill_process "worker.py" "Inference Worker"
kill_process "engine_sim.py" "Mock LLM Engine"
kill_process "vllm" "vLLM Engine"

# 3. Stop Redis
if pgrep -x "redis-server" > /dev/null; then
    echo "Stopping Redis server..."
    redis-cli shutdown || killall redis-server
else
    echo "💤 Redis server is not running."
fi

echo "=============================================================================="
echo "🎯 All services have been stopped successfully!"
echo "=============================================================================="
