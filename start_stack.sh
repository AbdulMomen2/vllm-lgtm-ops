#!/bin/bash

# ==============================================================================
# vLLM LLMOps Telemetry Stack - Native RunPod Orchestrator (No Docker)
# ==============================================================================

set -e

PROJECT_ROOT="/home/momen/momen/vLLM"
DEPLOY_DIR="$PROJECT_ROOT/native_deploy"
BIN_DIR="$DEPLOY_DIR/bin"
LOG_DIR="$PROJECT_ROOT/logs"

echo "🚀 Starting Native LLMOps Stack Installation & Boot..."
mkdir -p "$BIN_DIR" "$LOG_DIR" "$DEPLOY_DIR/data/prometheus"

# ------------------------------------------------------------------------------
# 1. Install Required System Utilities
# ------------------------------------------------------------------------------
echo "📦 Installing system dependencies (Redis, Unzip, Wget)..."
apt-get update -y -qq
apt-get install -y -qq redis-server unzip wget procps sqlite3 > /dev/null

# ------------------------------------------------------------------------------
# 2. Download Standalone Observability Binaries (if not present)
# ------------------------------------------------------------------------------
cd "$DEPLOY_DIR"

# Prometheus
if [ ! -f "$BIN_DIR/prometheus" ]; then
    echo "⬇️ Downloading Prometheus..."
    wget -q https://github.com/prometheus/prometheus/releases/download/v2.51.1/prometheus-2.51.1.linux-amd64.tar.gz
    tar -xf prometheus-2.51.1.linux-amd64.tar.gz
    cp prometheus-2.51.1.linux-amd64/prometheus "$BIN_DIR/"
    cp prometheus-2.51.1.linux-amd64/promtool "$BIN_DIR/"
    rm -rf prometheus-2.51.1.linux-amd64*
fi

# Loki
if [ ! -f "$BIN_DIR/loki" ]; then
    echo "⬇️ Downloading Loki..."
    wget -q https://github.com/grafana/loki/releases/download/v2.9.0/loki-linux-amd64.zip
    unzip -q loki-linux-amd64.zip
    mv loki-linux-amd64 "$BIN_DIR/loki"
    chmod +x "$BIN_DIR/loki"
    rm -f loki-linux-amd64.zip
fi

# Promtail
if [ ! -f "$BIN_DIR/promtail" ]; then
    echo "⬇️ Downloading Promtail..."
    wget -q https://github.com/grafana/loki/releases/download/v2.9.0/promtail-linux-amd64.zip
    unzip -q promtail-linux-amd64.zip
    mv promtail-linux-amd64 "$BIN_DIR/promtail"
    chmod +x "$BIN_DIR/promtail"
    rm -f promtail-linux-amd64.zip
fi

# Grafana
if [ ! -d "grafana-server-extracted" ]; then
    echo "⬇️ Downloading Grafana..."
    wget -q https://dl.grafana.com/oss/release/grafana-10.4.1.linux-amd64.tar.gz
    tar -xf grafana-10.4.1.linux-amd64.tar.gz
    mv grafana-10.4.1 grafana-server-extracted
    rm -f grafana-10.4.1.linux-amd64.tar.gz
fi

# ------------------------------------------------------------------------------
# 3. Configure Grafana Provisioning
# ------------------------------------------------------------------------------
echo "⚙️ Configuring Grafana dashboards and datasources..."
GRAFANA_CONF_DIR="$DEPLOY_DIR/grafana-server-extracted/conf/provisioning"
mkdir -p "$GRAFANA_CONF_DIR/datasources" "$GRAFANA_CONF_DIR/dashboards"

# Copy local dashboard JSON and configs
cp "$PROJECT_ROOT/grafana/provisioning/dashboards/dashboard_provisioning.yml" "$GRAFANA_CONF_DIR/dashboards/"
cp "$PROJECT_ROOT/grafana/provisioning/dashboards/llmops_dashboard.json" "$GRAFANA_CONF_DIR/dashboards/"

# Setup local datasource pointing to localhost Prometheus
cat <<EOF > "$GRAFANA_CONF_DIR/datasources/datasource.yml"
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://127.0.0.1:9090
    isDefault: true
EOF

# ------------------------------------------------------------------------------
# 4. Update local .env file variables if needed
# ------------------------------------------------------------------------------
echo "📝 Updating local environment variables in .env..."
if [ -f "$PROJECT_ROOT/.env" ]; then
    # Replace docker hostnames with localhost
    sed -i 's/REDIS_HOST=redis/REDIS_HOST=127.0.0.1/g' "$PROJECT_ROOT/.env"
    sed -i 's/LLM_ENGINE_URL=http:\/\/llm-engine:8000/LLM_ENGINE_URL=http:\/\/127.0.0.1:8000/g' "$PROJECT_ROOT/.env"
fi

# ------------------------------------------------------------------------------
# 5. Boot Up Services Natively (Background Processes)
# ------------------------------------------------------------------------------
echo "🔥 Starting background services..."

# A. Redis DB & Queue
echo "🟢 Starting Redis..."
redis-server --daemonize yes --port 6379 || echo "⚠️ Redis already running"

# B. Prometheus
echo "🟢 Starting Prometheus..."
nohup "$BIN_DIR/prometheus" \
  --config.file="$DEPLOY_DIR/prometheus-local.yml" \
  --storage.tsdb.path="$DEPLOY_DIR/data/prometheus" \
  > "$LOG_DIR/prometheus.log" 2>&1 &

# C. Loki
echo "🟢 Starting Loki..."
nohup "$BIN_DIR/loki" \
  -config.file="$DEPLOY_DIR/loki-local.yml" \
  > "$LOG_DIR/loki.log" 2>&1 &

# D. Promtail
echo "🟢 Starting Promtail..."
nohup "$BIN_DIR/promtail" \
  -config.file="$DEPLOY_DIR/promtail-local.yml" \
  > "$LOG_DIR/promtail.log" 2>&1 &

# E. Grafana
echo "🟢 Starting Grafana..."
cd "$DEPLOY_DIR/grafana-server-extracted"
export GF_SECURITY_ADMIN_PASSWORD=admin
nohup ./bin/grafana-server \
  --homepath="$DEPLOY_DIR/grafana-server-extracted" \
  > "$LOG_DIR/grafana.log" 2>&1 &

# F. Install Python Requirements
echo "🐍 Installing Python requirements..."
cd "$PROJECT_ROOT"
pip install -r requirements.txt --quiet

# G. Real/Mock vLLM Engine Auto-Detect Boot
echo "🟢 Booting vLLM Engine..."
DEVICE="cpu"
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    DEVICE="gpu"
fi

if [ "$DEVICE" = "gpu" ]; then
    echo "🎮 [llm-engine] NVIDIA GPU Detected! Booting real production vLLM engine..."
    nohup python -m vllm.entrypoints.openai.api_server \
      --model mistralai/Mistral-7B-Instruct-v0.2 \
      --gpu-memory-utilization 0.85 \
      --max-num-seqs 4 \
      --host 127.0.0.1 \
      --port 8000 \
      > "$LOG_DIR/llm-engine.log" 2>&1 &
else
    echo "💻 [llm-engine] No NVIDIA GPU found. Booting Mock LLM Engine..."
    nohup python src/engine_sim.py > "$LOG_DIR/llm-engine.log" 2>&1 &
fi

# H. API Gateway
echo "🟢 Starting API Gateway..."
nohup uvicorn src.gateway:app --host 0.0.0.0 --port 8080 > "$LOG_DIR/gateway.log" 2>&1 &

# I. Inference Worker
echo "🟢 Starting Inference Worker..."
nohup python src/worker.py > "$LOG_DIR/worker.log" 2>&1 &

echo "=============================================================================="
echo "🎉 ALL SERVICES STARTED SUCCESSFULLY!"
echo "=============================================================================="
echo "Check your logs directory for updates: tail -f logs/gateway.log"
echo "Grafana Dashboard is active on port 3000 (admin / admin)"
echo "=============================================================================="
