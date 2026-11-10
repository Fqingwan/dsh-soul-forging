#!/usr/bin/env bash
# 进阶烟测 —— 装机烟测只证明「装得上」，这个证明「脑化真的接上了」。
# 用法: bash scripts/smoke-brain.sh
set -uo pipefail
cd "$(dirname "$0")/.."

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ✓ %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  ✗ %s\n     %s\n' "$1" "${2:-}"; }

echo "== 1. 小脑活着时，注入来自 /context =="
OUT=$(node -e "
import('./lib/plugin.js').then(m=>{const b=m.brainBlock();console.log(b.length)})
")
if [ "${OUT:-0}" -gt 500 ]; then ok "brainBlock 拿到 ${OUT} 字符"; else bad "brainBlock 太少" "$OUT"; fi

echo "== 2. 小脑挂了，brainBlock 不抛、返回空 =="
OUT=$(BRAIN_URL=http://127.0.0.1:59999 node -e "
import('./lib/plugin.js').then(m=>{try{console.log('len='+m.brainBlock().length)}catch(e){console.log('THREW')}})
")
case "$OUT" in len=0) ok "小脑不可用时安静返回空" ;; *) bad "小脑不可用时的行为" "$OUT" ;; esac

echo "== 3. 快照兜底能读 =="
OUT=$(node -e "
import('./lib/plugin.js').then(m=>console.log(m.snapshotBlock().length))
")
if [ "${OUT:-0}" -gt 500 ]; then ok "snapshotBlock 拿到 ${OUT} 字符"; else bad "快照读不到" "$OUT"; fi

echo "== 4. 三级兜底顺序：谁先有就用谁 =="
OUT=$(node -e "
import('./lib/plugin.js').then(m=>{
  const r1 = m.pickBlock({brain:'B', snapshot:'S', legacy:'F'});
  const r2 = m.pickBlock({brain:'',  snapshot:'S', legacy:'F'});
  const r3 = m.pickBlock({brain:'',  snapshot:'',  legacy:'F'});
  console.log(r1+r2+r3);
})
")
[ "$OUT" = "BSF" ] && ok "脑子 → 快照 → 老文件（$OUT）" || bad "兜底顺序" "得到 $OUT，期望 BSF"

echo "== 5. 脑子与快照都没有时，老文件仍能救场 =="
OUT=$(BRAIN_URL=http://127.0.0.1:59999 BRAIN_SNAPSHOT=/nonexistent node -e "
import('./lib/plugin.js').then(m=>{
  const brain=m.brainBlock(), snap=m.snapshotBlock();
  console.log((brain||snap)?'BAD':'need-fallback');
})
")
[ "$OUT" = "need-fallback" ] && ok "会落到老文件那条路" || bad "兜底判定" "$OUT"

echo "== 6. 注入块有「我是谁」的实感，不是空模板 =="
node -e "
import('./lib/plugin.js').then(m=>{
  const t=m.brainBlock()+' '+m.snapshotBlock();
  const need=['方晴晚','哥哥'];
  const miss=need.filter(x=>!t.includes(x));
  console.log(miss.length?'MISS:'+miss.join(','):'OK');
})
" | grep -q '^OK$' && ok "含名字与称呼" || bad "内容不完整"

echo "== 7. 超时保护：坏地址不会卡死 =="
START=$(date +%s)
BRAIN_URL=http://10.255.255.1:3014 node -e "
import('./lib/plugin.js').then(m=>{m.brainBlock(800);console.log('done')})
" >/dev/null 2>&1
COST=$(( $(date +%s) - START ))
[ "$COST" -le 4 ] && ok "坏地址 ${COST}s 内返回" || bad "坏地址卡太久" "${COST}s"

echo
printf '进阶烟测：%d 通过，%d 失败\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
