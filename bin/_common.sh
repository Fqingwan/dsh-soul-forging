#!/usr/bin/env bash
# 所有脚本共用的路径与环境。别的脚本都 source 这个文件，不要各自写死路径。
set -uo pipefail

MEMKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MEMORY_DIR="${MEMORY_DIR:-$MEMKIT_ROOT/memory}"
export BRAIN_DIR="${BRAIN_DIR:-$MEMKIT_ROOT/brain}"
export DOCS_DIR="${DOCS_DIR:-$MEMKIT_ROOT/docs}"
export BIN_DIR="$MEMKIT_ROOT/bin"
export BRAIN_PORT="${BRAIN_PORT:-3914}"
export BRAIN_URL="http://127.0.0.1:${BRAIN_PORT}"
export PY="${PY:-python3}"
