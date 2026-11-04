#!/usr/bin/env bash
# 所有脚本共用的路径与环境。别的脚本都 source 这个文件，不要各自写死路径。
set -uo pipefail

# 关键：装成 npm 包后，node_modules/.bin/ 里是软链接，
# 直接按 $0 推上级会指到 node_modules/ 而不是包目录。必须先把链接解开。
_SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
MEMKIT_ROOT="$(cd "$(dirname "$_SELF")/.." && pwd)"
# 数据放用户目录，不放 node_modules 里 —— 那里升级会被整个换掉，而且通常没写权限
export SOUL_DATA_DIR="${SOUL_DATA_DIR:-$HOME/.soul-forging}"
export MEMORY_DIR="${MEMORY_DIR:-$SOUL_DATA_DIR/memory}"
export BRAIN_DIR="${BRAIN_DIR:-$SOUL_DATA_DIR/brain}"
export DOCS_DIR="${DOCS_DIR:-$MEMKIT_ROOT/docs}"
export BIN_DIR="$MEMKIT_ROOT/bin"
export BRAIN_PORT="${BRAIN_PORT:-3914}"
export BRAIN_URL="http://127.0.0.1:${BRAIN_PORT}"
export PY="${PY:-python3}"
