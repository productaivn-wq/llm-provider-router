#!/usr/bin/env bash
# One-command macOS/Linux installer for llm-provider-router (zero secret echo).
set -euo pipefail

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export LANG="${LANG:-C.UTF-8}"
REPO_URL="https://github.com/productaivn-wq/llm-provider-router.git"
ZIP_URL="https://github.com/productaivn-wq/llm-provider-router/archive/refs/heads/main.zip"
INSTALL_DIR="${ROUTER_INSTALL_DIR:-$HOME/llm-provider-router}"
PROXY_URL="${ROUTER_PROXY_URL:-}"
MODEL="${ROUTER_MODEL:-chatgpt/gpt-5.3-instant}"
CODING_MODEL="${ROUTER_CODING_MODEL:-chatgpt/gpt-5.3-codex}"
API_KEY_STDIN=0
SKIP_CHAT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) PROXY_URL="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --api-key-stdin) API_KEY_STDIN=1; shift ;;
    --skip-chat) SKIP_CHAT=1; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

find_python() {
  for cand in python3 python /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
        echo "$cand"
        return 0
      fi
    fi
  done
  return 1
}

PY_BIN="$(find_python || true)"
if [[ -z "$PY_BIN" ]]; then
  echo "Python 3.10+ not found. Attempting installation..."
  if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    brew install python@3.12
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
  fi
  PY_BIN="$(find_python || true)"
fi
if [[ -z "$PY_BIN" ]]; then
  echo "Error: Python 3.10+ is required." >&2
  exit 1
fi

echo "[1/5] Using Python: $PY_BIN"

if [[ ! -f "$INSTALL_DIR/pyproject.toml" ]]; then
  mkdir -p "$(dirname "$INSTALL_DIR")"
  if command -v git >/dev/null 2>&1; then
    echo "[2/5] Cloning repository into $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
  else
    echo "[2/5] Git missing; downloading repository ZIP..."
    TMP_ZIP="$(mktemp /tmp/llm-provider-router.XXXXXX.zip)"
    curl -fsSL "$ZIP_URL" -o "$TMP_ZIP"
    "$PY_BIN" -m zipfile -e "$TMP_ZIP" "$(dirname "$INSTALL_DIR")"
    rm -f "$TMP_ZIP"
    mv "$(dirname "$INSTALL_DIR")/llm-provider-router-main" "$INSTALL_DIR"
  fi
else
  echo "[2/5] Using existing folder $INSTALL_DIR"
fi

VENV_DIR="$INSTALL_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "[3/5] Creating virtual environment..."
  "$PY_BIN" -m venv "$VENV_DIR"
fi

echo "[3/5] Installing package into .venv..."
"$VENV_PY" -m pip install --upgrade pip --quiet
"$VENV_PY" -m pip install -e "$INSTALL_DIR" --quiet

if [[ -z "$PROXY_URL" ]]; then
  read -r -p "Proxy URL (e.g. https://your-proxy.example.com/v1): " PROXY_URL
fi

API_KEY=""
if [[ "$API_KEY_STDIN" -eq 1 ]]; then
  API_KEY="$(cat | tr -d '\r\n')"
elif [[ -n "${ROUTER_API_KEY:-}" ]]; then
  API_KEY="${ROUTER_API_KEY}"
else
  read -r -s -p "Personal API Key (hidden): " API_KEY
  echo ""
fi
if [[ -z "$API_KEY" ]]; then
  echo "Error: API key is required." >&2
  exit 1
fi

echo "[4/5] Configuring 0600 .env and probing proxy..."
ENV_FILE="$INSTALL_DIR/.env"
printf "%s" "$API_KEY" | "$VENV_PY" -m llm_provider_router setup \
  --url "$PROXY_URL" \
  --api-key-stdin \
  --model "$MODEL" \
  --coding-model "$CODING_MODEL" \
  --user-agent "LLM-Provider-Router/1.0" \
  --env-file "$ENV_FILE" \
  --probe \
  --json

echo "[5/5] Auto-wiring Orchestrator rules & skills (AGY / Claude / Codex / Cursor)..."
"$VENV_PY" -m llm_provider_router connect --install-dir "$INSTALL_DIR" --python-exe "$VENV_PY" --env-file "$ENV_FILE" --json

if [[ "$SKIP_CHAT" -eq 0 ]]; then
  echo "[Verify] Listing models and testing OpenAI sub-agent delegation..."
  "$VENV_PY" -m llm_provider_router models --env-file "$ENV_FILE" --json >/dev/null
  "$VENV_PY" -m llm_provider_router delegate --env-file "$ENV_FILE" --role writing "Reply OK if connected" --json
fi

echo "Setup complete. Install folder: $INSTALL_DIR. Open a NEW chat in Antigravity / Claude / Codex / Cursor to start offloading sub-tasks to OpenAI."
