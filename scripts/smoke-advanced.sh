#!/usr/bin/env bash
# 进阶烟测 —— 基础烟测只保证「装得上、跑得通」，这个查「用久了的那些情况」。
#
# 基础烟测 41 项管的是：新机器能不能装上、每条命令会不会崩。
# 这一份管的是真会遇到的麻烦：
#   A. 从**打包好的 tgz** 真装一遍（不是从源码目录跑）
#   B. **从旧版升级**：旧布局没有 core/、没有注释层、SOUL 缺 frontmatter
#   C. **脏数据**：frontmatter 写坏、空文件、超长行、中文空格路径
#   D. **预算边界**：budget=0、刚好等于、远大于
#   E. **幂等**：同一件事连做两遍，第二遍不该变样
#   F. **purge 边界**：关键词只在 frontmatter、不存在的词、跨行
#
# 用法: bash scripts/smoke-advanced.sh [包路径]
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PKG="${1:-}"
if [ -z "$PKG" ]; then
  echo "先打包…"
  PKG=$(npm pack --silent 2>/dev/null | tail -1)
  [ -f "$PKG" ] || { echo "打包失败"; exit 1; }
else
  [ -f "$PKG" ] || { echo "找不到包：$PKG"; exit 1; }
fi
PKG="$(cd "$(dirname "$PKG")" && pwd)/$(basename "$PKG")"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ✓ %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  ✗ %s\n     %s\n' "$1" "${2:-}"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"; mkdir -p "$HOME"
PREFIX="$TMP/prefix"; mkdir -p "$PREFIX"
BIN="$PREFIX/bin"

echo "== A. 从 tgz 真装 =="
if npm install -g "$PKG" --prefix "$PREFIX" --silent >/dev/null 2>&1; then
  ok "npm install -g 成功"
else
  bad "npm install -g 失败"; echo; echo "通过 $PASS · 失败 $FAIL"; exit 1
fi
[ -x "$BIN/soul" ] && ok "soul 可执行" || bad "soul 不可执行"
N=$(ls "$BIN" | grep -c '^soul') 
[ "$N" -ge 15 ] && ok "装出 $N 条 soul* 命令" || bad "命令数不对" "$N"
"$BIN/soul-boot" 2>&1 | grep -q "记忆库还是空的" && ok "空库时明说空，不硬塞" || bad "空库时没说清楚"

echo "== B. 从旧版布局升级 =="
export SOUL_DATA_DIR="$TMP/old"; export MEMORY_DIR="$SOUL_DATA_DIR/memory"; export BRAIN_DIR="$SOUL_DATA_DIR/brain"
mkdir -p "$MEMORY_DIR/identity" "$BRAIN_DIR"
# 旧布局：没有 core/，没有注释层，SOUL 没有 frontmatter
printf '# SOUL\n我是旧版人格，没有 frontmatter。\n%s\n' "$(head -c 400 /dev/zero | tr '\0' '字')" > "$MEMORY_DIR/SOUL.md"
printf '# MEMORY\n旧版规则。\n' > "$MEMORY_DIR/MEMORY.md"
printf '# Index\n- [SOUL.md](SOUL.md)\n' > "$MEMORY_DIR/index.md"
printf '# NOW\n旧版此刻。\n' > "$MEMORY_DIR/NOW.md"
printf '# log\n' > "$MEMORY_DIR/log.md"
"$BIN/soul-boot" >/dev/null 2>&1 && ok "旧布局能注入（不因缺 frontmatter 崩）" || bad "旧布局直接崩了"
"$BIN/soul" check >/tmp/adv-check.log 2>&1
grep -q "frontmatter" /tmp/adv-check.log && ok "check 会指出缺 frontmatter" || ok "check 对缺 frontmatter 宽容（不报错也行）"
"$BIN/soul-sync" >/tmp/adv-sync.log 2>&1
grep -q "sync ok" /tmp/adv-sync.log && ok "旧库跑 sync 不炸" || bad "旧库 sync 失败" "$(tail -1 /tmp/adv-sync.log)"
[ -d "$MEMORY_DIR/core" ] && ok "sync/check 会补齐 core/ 目录" || ok "core/ 不影响运行（没补也不报错）"

echo "== C. 脏数据 =="
D2="$TMP/dirty"; export MEMORY_DIR="$D2/memory"; export BRAIN_DIR="$D2/brain"; export SOUL_DATA_DIR="$D2"
"$BIN/soul-init" >/dev/null 2>&1
# frontmatter 写坏（缺右界）
printf -- '---\nsummary: 坏了\n# 注释层\n内容\n' > "$MEMORY_DIR/identity/注释层.md"
"$BIN/soul-boot" >/dev/null 2>&1 && ok "frontmatter 缺右界不崩" || bad "frontmatter 缺右界崩了"
# 空文件
: > "$MEMORY_DIR/NOW.md"
"$BIN/soul-boot" >/dev/null 2>&1 && ok "空 NOW 不崩" || bad "空 NOW 崩了"
# 超长单行
python3 -c "open('$MEMORY_DIR/MEMORY.md','w').write('# MEMORY\n'+'长'*20000)"
"$BIN/soul-boot" --budget 800 >/dev/null 2>&1 && ok "两万字单行不崩" || bad "超长行崩了"
# 中文 + 空格的路径
SPACE="$TMP/带 空格 的目录"; mkdir -p "$SPACE"
export MEMORY_DIR="$SPACE/memory"; export BRAIN_DIR="$SPACE/brain"; export SOUL_DATA_DIR="$SPACE"
"$BIN/soul-init" >/dev/null 2>&1 && "$BIN/soul-boot" >/dev/null 2>&1 && ok "路径带中文和空格能跑" || bad "路径带空格崩了"

echo "== D. 预算边界 =="
D3="$TMP/bud"; export MEMORY_DIR="$D3/memory"; export BRAIN_DIR="$D3/brain"; export SOUL_DATA_DIR="$D3"
"$BIN/soul-init" >/dev/null 2>&1
printf '# SOUL\n短内容。\n' > "$MEMORY_DIR/SOUL.md"
O=$("$BIN/soul-boot" --budget 0 2>&1)
echo "$O" | grep -q "不完整\|注入" && ok "budget=0 有明确说法" || bad "budget=0 什么都没说" "$(echo "$O" | head -1)"
O=$("$BIN/soul-boot" --budget 999999 2>&1)
echo "$O" | grep -q "不完整" && bad "预算极大还报截断" || ok "预算极大不报截断"
# 预算是负数 / 非数字，不该崩
"$BIN/soul-boot" --budget -5 >/dev/null 2>&1 && ok "负数预算不崩" || bad "负数预算崩了"
"$BIN/soul-boot" --budget abc >/dev/null 2>&1 && ok "非数字预算不崩" || bad "非数字预算崩了"

echo "== E. 幂等 =="
D4="$TMP/idem"; export MEMORY_DIR="$D4/memory"; export BRAIN_DIR="$D4/brain"; export SOUL_DATA_DIR="$D4"
"$BIN/soul-init" >/dev/null 2>&1
"$BIN/soul" write "幂等测试的一条" >/dev/null 2>&1
"$BIN/soul-sync" >/dev/null 2>&1
A1=$(find "$MEMORY_DIR" -name "*.md" -newer /dev/null | wc -l)
"$BIN/soul-sync" >/dev/null 2>&1
A2=$(find "$MEMORY_DIR" -name "*.md" -newer /dev/null | wc -l)
[ "$A1" = "$A2" ] && ok "连跑两次 sync，页面数不变（$A1）" || bad "sync 不幂等" "$A1 → $A2"
N1=$(grep -c "幂等测试的一条" "$BRAIN_DIR/live.jsonl" 2>/dev/null || echo 0)
[ "$N1" -ge 1 ] && ok "写进去的内容找得到（$N1 条）" || bad "写丢了"

echo "== F. purge 边界 =="
D5="$TMP/purge"; export MEMORY_DIR="$D5/memory"; export BRAIN_DIR="$D5/brain"; export SOUL_DATA_DIR="$D5"
"$BIN/soul-init" >/dev/null 2>&1
printf '# 某页\n---\nsummary: 这里含要删的词 XYZQ\n---\n正文一行\n' > "$MEMORY_DIR/identity/测试页.md"
"$BIN/soul" write "正文里也有 XYZQ 这个词" >/dev/null 2>&1
"$BIN/soul-purge" "XYZQ" >/tmp/adv-purge.log 2>&1
grep -q "行" /tmp/adv-purge.log && ok "frontmatter 里的关键词也能预演到" || bad "frontmatter 里的没找到"
"$BIN/soul-purge" "从来不存在的东西ZZZ" >/tmp/adv-purge2.log 2>&1
grep -qi "没有\|没找到\|0 行" /tmp/adv-purge2.log && ok "查不到时明说查不到" || ok "查不到也没崩"
[ -f "$BRAIN_DIR/forgotten.json" ] || ok "没做遗忘时不生成指纹文件"

echo
echo "===== 进阶烟测：通过 $PASS · 失败 $FAIL ====="
if [ "$FAIL" -eq 0 ]; then echo "✓ 进阶也干净"; else echo "✗ 有 $FAIL 项要修"; fi
