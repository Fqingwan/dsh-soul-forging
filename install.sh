#!/usr/bin/env bash
# 一键安装：检查环境 → 建索引 → 起服务 → 告诉你下一步
set -uo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

echo "== 记忆套件安装 =="
echo

# 1) 环境
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "✗ 没找到 python3。先装 Python 3.8+ 再来。"
  exit 1
fi
echo "✓ python3: $PY ($($PY -V 2>&1))"

if command -v curl >/dev/null 2>&1; then
  echo "✓ curl 有"
else
  echo "! 没有 curl —— 检索会退化成「每次现算」，慢一点但能用"
fi

# 2) 记忆库结构
for d in memory memory/core memory/identity memory/user memory/decisions memory/diary memory/raw brain docs/tech docs/debug; do
  [ -d "$d" ] || { mkdir -p "$d"; echo "✓ 补建 $d"; }
done

# 3) 建索引
echo
echo "== 建索引 =="
"$PY" brain/index.py || { echo "✗ 建索引失败"; exit 1; }

# 4) 起服务（可选）
echo
echo "== 起检索服务 =="
bash bin/serve || echo "! 服务没起来，不影响使用（检索会自动现算）"

# 5) 下一步
cat <<EOF

== 装好了（命令行模式）==

想当 DSH 插件用（记忆自动注入）：
  bash bin/init-home           # 铺一份空白记忆库到 ~/.soul-forging/memory
  dsh plugin add $(pwd)        # 装进 profile，重开 DSH 即生效


接下来：
  1. 打开 memory/SOUL.md，先把「身份」和「沟通风格」填了
  2. 打开 memory/BOOTSTRAP.md，按清单一项项聊（status: pending）
  3. 填完跑一次：bash bin/sync

常用命令：
  brain "关键词"                 查记忆小脑
  brain --topics                 看有哪些分类
  bin/soul write "内容"    记一条运行期记忆
  bin/soul check           体检
  bin/sync                       一键同步（建索引 + 重载 + 体检）
  debug-recall "报错"            查调试旧账

目录：
  memory/    记忆库（可提交到 git，也可以只本地留）
  brain/     索引与服务（一般不用管）
  docs/tech  技术结论     docs/debug  调试过程

EOF
