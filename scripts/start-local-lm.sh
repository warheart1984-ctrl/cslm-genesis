#!/usr/bin/env bash
# Start a project-local Ollama with weights on the 4TB drive (not /).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="${OLLAMA_MODELS:-/media/jon/DEEA8E6FEA8E442D/ollama-models}"
HOST="${OLLAMA_HOST:-127.0.0.1:11435}"
MODEL="${CSLM_BASE_LM_MODEL:-llama3.2:3b}"

mkdir -p "$MODELS_DIR"
export OLLAMA_MODELS="$MODELS_DIR"
export OLLAMA_HOST="$HOST"

if curl -sf "http://${HOST}/api/tags" >/dev/null 2>&1; then
  echo "ollama already reachable at ${HOST}"
else
  echo "starting ollama serve on ${HOST} with OLLAMA_MODELS=${MODELS_DIR}"
  nohup /usr/local/bin/ollama serve >"${ROOT}/.ollama-serve.log" 2>&1 &
  echo $! >"${ROOT}/.ollama-serve.pid"
  for _ in $(seq 1 30); do
    if curl -sf "http://${HOST}/api/tags" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
fi

if ! /usr/local/bin/ollama list | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
  echo "pulling ${MODEL} into ${MODELS_DIR}"
  /usr/local/bin/ollama pull "$MODEL"
fi

/usr/local/bin/ollama list
echo "CSLM: CSLM_ADAPTER=openai_compat CSLM_BASE_LM_BASE_URL=http://${HOST} CSLM_BASE_LM_MODEL=${MODEL}"
