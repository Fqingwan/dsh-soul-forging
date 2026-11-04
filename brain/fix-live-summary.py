#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补齐 live.jsonl 里缺摘要的记录；把坏行隔离出来（不删）。

摘要缺了会怎样：检索只看到半句，模型就只记得"有这么回事"，不知道具体。
用法: python3 brain/fix-live-summary.py [--dry]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memkit_lib import LIVE, derive_summary, atomic_write

def main():
    dry = "--dry" in sys.argv
    if not os.path.exists(LIVE):
        print("没有 live.jsonl，跳过"); return 0
    good, bad, fixed = [], [], 0
    for line in open(LIVE, encoding="utf-8"):
        s = line.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except Exception:
            bad.append(s)
            continue
        if not str(rec.get("summary") or "").strip():
            rec["summary"] = derive_summary(rec.get("text", ""))
            fixed += 1
        good.append(json.dumps(rec, ensure_ascii=False))
    if bad:
        atomic_write(LIVE + ".bad", "\n".join(bad) + "\n")
    if not dry:
        atomic_write(LIVE, "\n".join(good) + ("\n" if good else ""))
    print(f"补摘要 {fixed} 条 · 坏行 {len(bad)} 条{'（已隔离到 .bad）' if bad else ''}{' [dry]' if dry else ''}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
