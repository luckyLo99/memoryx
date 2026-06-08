#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
VER="$(cat VERSION 2>/dev/null || echo unknown)"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()  { printf "${GREEN}\xe2\x9c\x93${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}\xe2\x9a\xa0 %s${NC}\n" "$*"; }
error() { printf "${RED}\xe2\x9c\x97 %s${NC}\n" "$*"; }
step()  { printf "\n${CYAN}%s${NC}\n" "================"; printf "${BOLD}Step %s${NC}\n" "$*"; }
prompt_yn() {
  local m="$1" d="${2:-y}" a h
  [ "$d" = "y" ] && h="Y/n" || h="y/N"
  read -r -p "$(printf "${YELLOW}?${NC} %s [${h}]: " "$m")" a
  a="${a:-$d}"; case "$a" in [yY]|[yY][eE][sS]) return 0;; *) return 1;; esac
}
echo ""
echo "=============================================="
echo "  MemoryX Configuration Wizard v3"
echo "  Long-term memory: configure, install, run"
echo "=============================================="
echo "  v${VER}  |  ${SCRIPT_DIR}"
echo ""
step "1/5 - Check environment"
PY=""
for c in python3.12 python3.11 python3; do command -v "$c" &>/dev/null && PY="$c" && break; done
if [ -z "$PY" ]; then error "Python 3.11+ not found"; exit 1; fi
info "Python: $($PY --version 2>&1)"
$PY -c "import sqlite3; c=sqlite3.connect(":memory:"); c.execute("CREATE VIRTUAL TABLE t USING fts5(content)")" 2>/dev/null && info "FTS5: ok" || warn "FTS5: unavailable"
step "2/5 - Configure modules"
echo "--- Storage ---"
SB="sqlite"
prompt_yn "Enable vector storage (LanceDB+Embeddings)?" "n" && { SB="hybrid"; info "Vector ON"; }
echo "--- LLM ---"
LP=""; LK=""; LM=""; LU=""
prompt_yn "Configure LLM API?" "y" && {
  echo "1: OpenAI  2: SiliconFlow  3: Custom"; read -r -p "[1]: " LC; LC="${LC:-1}"
  case "$LC" in
    2) LP="siliconflow"; LU="https://api.siliconflow.cn/v1"; LM="Qwen/Qwen2.5-7B-Instruct" ;;
    3) LP="custom"; read -r -p "URL: " LU; read -r -p "Model: " LM ;;
    *) LP="openai"; LU="https://api.openai.com/v1"; LM="gpt-4o-mini" ;;
  esac; read -r -p "API Key: " LK; info "LLM: ${LP} / ${LM}";
}
echo "--- Embedding ---"
EP=""; EK=""; EM=""; EU=""; ED=768
[ "$SB" = "hybrid" ] && {
  prompt_yn "Use remote Embedding API?" "y" && {
    echo "1: OpenAI  2: SiliconFlow  3: Custom"; read -r -p "[1]: " EC; EC="${EC:-1}"
    case "$EC" in
      2) EP="siliconflow"; EU="https://api.siliconflow.cn/v1"; EM="BAAI/bge-m3"; ED=1024 ;;
      3) EP="custom"; read -r -p "URL: " EU; read -r -p "Model: " EM; read -r -p "Dim: " ED ;;
      *) EP="openai"; EU="https://api.openai.com/v1"; EM="text-embedding-3-small"; ED=1536 ;;
    esac; read -r -p "API Key: " EK; info "Embed: ${EP} / ${EM} (dim=${ED})"
  } || { EP="local"; EM="BAAI/bge-small-zh-v1.5"; ED=384; info "Embed: local / ${EM}"; }
}
echo "--- Integration ---"
echo "1: MCP Server  2: Hermes Agent  3: Standalone"
read -r -p "[1]: " IM; IM="${IM:-1}"
case "$IM" in 2) IM="hermes";; 3) IM="standalone";; *) IM="mcp";; esac; info "Mode: ${IM}"
echo "--- Memory source ---"
UNQ="false"
prompt_yn "Sole memory source (replace all others)?" "n" && UNQ="true" && info "Sole source: ON" || info "Sole source: OFF"
echo "--- Advanced modules ---"
CG="n"; TP="n"; RF="n"; TM="n"; MC="n"; PL="n"; OB="n"
prompt_yn "Cognitive module?" "y" && CG="y"
prompt_yn "Temporal cognition?" "y" && TP="y"
prompt_yn "Reflection engine?" "y" && RF="y"
prompt_yn "Tool memory?" "y" && TM="y"
prompt_yn "Meta-cognition?" "n" && MC="y"
prompt_yn "Palace of Memory?" "n" && PL="y"
prompt_yn "Observability?" "n" && OB="y"
step "3/5 - Generate .env"
[ -f .env ] && cp .env ".env.$(date +%Y%m%d_%H%M%S).bak" && info "Backed up"
{
  echo "# MemoryX v${VER} - Auto-generated config"
  echo "MEMORYX_STORAGE_ENABLED=true"
  echo "MEMORYX_HOME=${SCRIPT_DIR}/.memoryx"
  [ -n "$LK" ] && { echo ""; echo "# LLM"; echo "MEMORYX_LLM_PROVIDER=${LP}"; echo "MEMORYX_LLM_API_KEY=${LK}"; echo "MEMORYX_LLM_MODEL=${LM}"; echo "MEMORYX_LLM_BASE_URL=${LU}"; }
  [ -n "$EK" ] && { echo ""; echo "# Embedding"; echo "MEMORYX_EMBEDDING_PROVIDER=${EP}"; echo "MEMORYX_EMBEDDING_API_KEY=${EK}"; echo "MEMORYX_EMBEDDING_MODEL=${EM}"; echo "MEMORYX_EMBEDDING_BASE_URL=${EU}"; echo "MEMORYX_EMBEDDING_DIM=${ED}"; }
  echo ""; echo "# Integration"; echo "MEMORYX_INTEGRATION_MODE=${IM}"
  [ "$UNQ" = "true" ] && { echo ""; echo "# Sole source"; echo "MEMORYX_UNIQUE_MEMORY_SOURCE=true"; echo "MEMORYX_EXTRACTION_EVERY_N_TURNS=1"; }
  echo ""; echo "# Modules"
  [ "$CG" = "y" ] && echo "MEMORYX_MODULE_COGNITIVE=true"
  [ "$TP" = "y" ] && echo "MEMORYX_MODULE_TEMPORAL=true"
  [ "$RF" = "y" ] && echo "MEMORYX_MODULE_REFLECTION=true"
  [ "$TM" = "y" ] && echo "MEMORYX_MODULE_TOOL_MEMORY=true"
  [ "$MC" = "y" ] && echo "MEMORYX_MODULE_META_COGNITION=true"
  [ "$PL" = "y" ] && echo "MEMORYX_MODULE_PALACE=true"
  [ "$OB" = "y" ] && echo "MEMORYX_MODULE_OBSERVABILITY=true"
  echo ""; echo "# Optional"; echo "# MEMORYX_LOG_LEVEL=INFO"
} > .env && info ".env generated"
step "4/5 - Install dependencies"
[ ! -d .venv ] && { $PY -m venv .venv; info "venv created"; } || info "venv exists"
source .venv/bin/activate
pip install --upgrade pip -q 2>/dev/null || true
pip install -r requirements.txt -q && info "Core deps installed"
[ "$SB" = "hybrid" ] && { pip install lancedb sentence-transformers -q 2>/dev/null && info "Vector deps" || warn "Vector deps failed"; }
[ "$IM" = "mcp" ] && { pip install mcp -q 2>/dev/null && info "MCP dep" || warn "MCP dep failed"; }
pip install pytest pytest-asyncio -q 2>/dev/null || true
pip install -e . -q 2>/dev/null || true && info "MemoryX installed"
mkdir -p .memoryx/db .memoryx/logs .memoryx/cache
[ -f db/schema.sql ] && $PY -c "import sqlite3,os; db=\".memoryx/db/memoryx.sqlite3\"; os.makedirs(\".memoryx/db\",exist_ok=True); c=sqlite3.connect(db); c.executescript(open(\"db/schema.sql\").read()); c.commit(); c.close(); print(\"DB initialized\")" 2>&1 | grep -v "^wsl:" | tail -1
$PY -c "import memoryx; print(\"import ok: v\"+memoryx.__version__)" 2>&1 | grep -v "^wsl:" | tail -1 && info "Verified"
step "5/5 - Launch MemoryX"
echo ""; echo "  Summary:"; echo "  Storage: ${SB}  |  LLM: ${LP:-none}  |  Embed: ${EP:-none}"
echo "  Mode: ${IM}  |  Sole src: ${UNQ}"
echo "  Modules: CG=${CG} TP=${TP} RF=${RF} TM=${TM} MC=${MC} PL=${PL} OB=${OB}"
prompt_yn "Launch now?" "y" || { info "Done"; exit 0; }
source .venv/bin/activate
case "$IM" in
  mcp) info "MCP: python -m memoryx.mcp.server";;
  hermes) $PY -c "from memoryx.integration.runtime import HermesIntegrationRuntime; from pathlib import Path; rt=HermesIntegrationRuntime(home=Path(\".memoryx\")); print(\"Hermes RT\"); [print(f\"  {s}\") for s in rt.startup_flow()]" 2>&1 | grep -v "^wsl:" | grep -v Deprecation || true;;
  standalone) info "API: uvicorn memoryx.api.app:app --port 8000";;
esac
echo ""
echo "=============================================="
echo "  Complete! Data: .memoryx/  Conf: .env"
echo "  source .venv/bin/activate"
echo "  python -c \"import memoryx\""
echo "=============================================="