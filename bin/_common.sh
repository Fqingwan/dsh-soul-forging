#!/usr/bin/env bash
# 所有脚本共用的路径与环境。别的脚本都 source 这个文件，不要各自写死路径。
set -uo pipefail

# 关键：装成 npm 包后，node_modules/.bin/ 里是软链接，
# 直接按 $0 推上级会指到 node_modules/ 而不是包目录。必须先把链接解开。
_SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
MEMKIT_ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
export MEMORY_DIR="${MEMORY_DIR:-$MEMKIT_ROOT/memory}"
export BRAIN_DIR="${BRAIN_DIR:-$MEMKIT_ROOT/brain}"
export DOCS_DIR="${DOCS_DIR:-$MEMKIT_ROOT/docs}"
export BIN_DIR="$MEMKIT_ROOT/bin"
export BRAIN_PORT="${BRAIN_PORT:-3914}"
export BRAIN_URL="http://127.0.0.1:${BRAIN_PORT}"
export PY="${PY:-python3}"
