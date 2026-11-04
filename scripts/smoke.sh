#!/usr/bin/env bash
# 装机烟测 —— 每次 npm publish 之前必须跑过。
#
# 为什么要有这个：源码目录里跑一百遍都是好的，装出来才炸。
# 已经栽过三次：
#   ① .bin 里是软链接，按 $0 推上级目录指错
#   ② 数据目录写进 /usr/local/lib/node_modules，权限拒绝
#   ③ runlog 没执行位；后来又用 python 去跑 bash 脚本
#
# 这个脚本模拟「全新机器 + 全局安装 + 干净 HOME」：
#   npm pack → 装进临时 prefix → 用干净 HOME 跑每一条命令 → 逐项断言
#
# 用法: bash scripts/smoke.sh
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ✓ %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  ✗ %s\n     %s\n' "$1" "${2:-}"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"; mkdir -p "$HOME"
PREFIX="$TMP/prefix"; mkdir -p "$PREFIX"

echo "== 1. 打包 =="
TGZ=$(npm pack --silent 2>/dev/null | tail -1)
[ -f "$TGZ" ] && ok "npm pack → $TGZ" || { bad "npm pack"; exit 1; }

echo "== 2. 全局安装（模拟 /usr/local）=="
INSTALL_LOG=$TMP/install.log
if ! npm i -g --prefix "$PREFIX" "$ROOT/$TGZ" >"$INSTALL_LOG" 2>&1; then
  bad "安装失败" "$(grep -E 'npm (ERR|error)' "$INSTALL_LOG" | head -2 | tr '\n' ' ')"
  exit 1
fi
BIN="$PREFIX/bin"
[ -x "$BIN/soul" ] && ok "命令已安装到 $BIN" || { bad "安装后没有 soul 命令" "$(ls "$PREFIX" 2>/dev/null | tr '\n' ' ')"; exit 1; }
VER=$(node -e "console.log(require('$PREFIX/lib/node_modules/dsh-soul-forging/package.json').version)")
ok "版本 $VER"

check_pkg_clean() {
  node -e "
const fs=require('fs');const p='$PREFIX/lib/node_modules/dsh-soul-forging';
const bad=['brain/entries.json','brain/state.json','brain/live.jsonl','brain/snapshots']
  .filter(f=>fs.existsSync(p+'/'+f));
if(bad.length){console.log(bad.join(','));process.exit(1)}
" 2>/dev/null
}

echo "== 3. 逐条命令 =="
run() { # 名字 命令...
  local name="$1"; shift
  local out; out=$("$@" 2>&1); local rc=$?
  if [ $rc -eq 0 ] && [ -n "$out" ]; then ok "$name"; else bad "$name" "rc=$rc ${out:0:120}"; fi
  LAST_OUT="$out"
}

run "soul-init"      "$BIN/soul-init"
run "soul-boot"      "$BIN/soul-boot" --list
# sync 永远 exit 0（失败也返回 0，只是打印"有失败项"），所以必须看输出
sync_ok() {
  local out; out=$("$BIN/soul-sync" 2>&1)
  echo "$out" | grep -q "^sync ok$" && ok "soul-sync（干净）" && return 0
  bad "soul-sync 有失败项" "$(echo "$out" | grep -E '失败' | head -1)"
  return 1
}
sync_ok
run "soul (write)"   "$BIN/soul" write "烟测写的一条"
sync_ok
run "soul-recall"    "$BIN/soul-recall" "烟测" 1
echo "$LAST_OUT" | grep -q "烟测写的一条" && ok "检索命中刚写的内容" || bad "检索没命中"

# 服务类：起在随机高位端口，测完杀掉
PORT=$(( (RANDOM % 2000) + 39000 ))
BRAIN_PORT=$PORT "$BIN/soul-serve" >/dev/null 2>&1
sleep 1
curl -s -m 3 "http://127.0.0.1:$PORT/health" | grep -q '"ok": true' && ok "soul-serve 起得来" || bad "soul-serve"
BRAIN_PORT=$PORT "$BIN/soul-sync" 2>&1 | grep -q "^sync ok$" && ok "sync（服务在跑时）" || bad "sync（服务在跑时）"

run "soul-check"     "$BIN/soul" check
run "soul-forget"    "$BIN/soul-forget"
run "soul-snapshot"  "$BIN/soul-snapshot" save "烟测"
run "soul-peer"      "$BIN/soul-peer" export
run "soul-sediment"  "$BIN/soul-sediment"
run "soul-review"    "$BIN/soul-review"
run "soul-archive"   "$BIN/soul-archive"
run "soul-debug"     "$BIN/soul-debug"

echo "== 4. 包目录必须干净（跑完所有命令之后查）=="
DIRTY=$(check_pkg_clean) && ok "包目录没被写脏" || bad "包目录被污染：$DIRTY"

echo "== 5. 插件加载 =="
node -e "
import('$PREFIX/lib/node_modules/dsh-soul-forging/lib/plugin.js').then(m=>{
  let c; const ctx={systemPrompt:{context(o){c=o;return()=>{}}},skills:{register(){return()=>{}}},logger:{info(){},warn(){}}};
  m.apply(ctx,{});
  const t=c.text({});
  if(typeof m.name!=='string') throw new Error('name 缺失');
  if(!Array.isArray(m.inject)) throw new Error('inject 缺失');
  if(!t || t.length<1000) throw new Error('注入块太短: '+t.length);
  console.log('OK '+t.length);
}).catch(e=>{console.log('FAIL '+e.message);process.exit(1)})
" >/tmp/smoke-plugin.out 2>&1
grep -q "^OK" /tmp/smoke-plugin.out && ok "插件注入 $(cut -d' ' -f2 /tmp/smoke-plugin.out) 字" \
  || bad "插件加载" "$(cat /tmp/smoke-plugin.out | head -2)"

rm -f "$ROOT/$TGZ"
echo
echo "===== 通过 $PASS · 失败 $FAIL ====="
[ $FAIL -eq 0 ] || exit 1
echo "✓ 可以发"
