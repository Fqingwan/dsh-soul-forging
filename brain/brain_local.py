#!/usr/bin/env python3
"""brain_local — 小脑检索的本地版（毫秒级，不走隧道）。

这是入包版：路径全部 env 化，默认落 $SOUL_DATA_DIR/brain，不带任何服务器绝对路径。

用法: python3 brain/brain_local.py "关键词" [条数]
      python3 brain/brain_local.py --sync     # 从 BRAIN_SYNC_REMOTE 拉最新 entries/state

打分逻辑与旧 brain/server.py 保持一致：
bigram 命中（标题×2.2 + 正文×1.0）/ len^0.8，原始串命中 +3.0（标题区再 +1.5），
乘强度 (0.45+st)，日期近的按 exp(-age/60) 微加成；强度低于 MIN_STRENGTH=0.12 的不出结果。

环境变量:
  SOUL_DATA_DIR       数据根（默认 ~/.soul-forging）
  BRAIN_DIR           entries.json/state.json 目录（默认 $SOUL_DATA_DIR/brain）
  BRAIN_CACHE_DIR     pickle 缓存目录（默认 $BRAIN_DIR/cache）
  BRAIN_SYNC_REMOTE   scp 远端，形如 user@host:/path/（默认空；空时 --sync 静默跳过）
  BRAIN_TOUCH_URL     上游 /touch 地址（默认空；空或连不上静默跳过）
"""
import json
import math
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

DATA_ROOT = os.environ.get("SOUL_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".soul-forging")
BRAIN_DIR = os.environ.get("BRAIN_DIR") or os.path.join(DATA_ROOT, "brain")
ENTRIES = os.path.join(BRAIN_DIR, "entries.json")
STATE = os.path.join(BRAIN_DIR, "state.json")
CACHE_DIR = os.environ.get("BRAIN_CACHE_DIR") or os.path.join(BRAIN_DIR, "cache")
CACHE = os.path.join(CACHE_DIR, "entries-cache.pkl")
# scp 远端，必须带结尾斜杠；空 = 未配置
SYNC_REMOTE = os.environ.get("BRAIN_SYNC_REMOTE", "").strip()
# 上游「被想起」回调地址，空 = 不回调
TOUCH_URL = os.environ.get("BRAIN_TOUCH_URL", "").strip()

STAB_BASE = {1: 45.0, 2: 30.0, 3: 20.0}
KIND_STAB = {
    "core": 1e9, "chat": 5.0, "live": 30.0, "learn": 45.0,
    "diary": 9.0, "log": 12.0, "intimate": 540.0,
}
STAB_GROW, STAB_MAX, FLOOR = 1.6, 180.0, 0.05
MIN_STRENGTH = 0.12


def norm(s):
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", s or "")
    return " " + re.sub(r"\s+", " ", s).strip().lower() + " "


def grams(s, k=2):
    out = set()
    for seg in norm(s).split():
        for i in range(len(seg) - k + 1):
            g = seg[i:i + k]
            if g.isdigit():
                continue
            out.add(g)
        if len(seg) == 1 and not seg.isdigit():
            out.add(seg)
    return out


def load():
    import pickle
    entries = None
    # 缓存比索引新就用缓存（省掉每次重算 grams 的 ~70ms）
    try:
        if os.path.exists(CACHE) and os.path.getmtime(CACHE) >= os.path.getmtime(ENTRIES):
            with open(CACHE, "rb") as f:
                entries = pickle.load(f)
    except Exception:
        entries = None
    if entries is None:
        entries = json.load(open(ENTRIES, encoding="utf-8"))
        entries = entries.get("entries", entries) if isinstance(entries, dict) else entries
        for e in entries:
            e["_head"] = grams((e.get("title", "") or "") + " " + (e.get("section", "") or ""))
            e["_body"] = grams(e.get("text", "") or "")
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(CACHE, "wb") as f:
                pickle.dump(entries, f, protocol=4)
        except Exception:
            pass
    try:
        state = json.load(open(STATE, encoding="utf-8"))
    except Exception:
        state = {}
    return entries, state.get("mem", {})


def mem_of(e, mem):
    sid = e.get("id")
    st = mem.get(sid)
    if not st:
        base = STAB_BASE.get(int(e.get("salience") or 2), 30.0)
        ks = KIND_STAB.get(str(e.get("kind") or ""))
        if ks is not None:
            base = min(base, ks)
        st = {"hits": 0, "lastHit": 0, "stab": base}
    return st


def strength_of(e, mem, now_ts=None):
    st = mem_of(e, mem)
    last = float(st.get("lastHit") or 0)
    if not last:                      # 没被检索过 → 按初始计算
        return 1.0
    now_ts = now_ts or datetime.now(timezone.utc).timestamp()
    days = max(0.0, (now_ts - last) / 86400.0)
    stab = max(1.0, float(st.get("stab") or 1.0))
    return max(FLOOR, min(1.0, FLOOR + (1.0 - FLOOR) * (0.5 ** (days / stab))))


SYNONYMS = {
    # —— 身体的 ——
    "胸": ["乳", "胸口", "颈窝", "胸罩"],
    "乳": ["胸", "乳头"],
    "下面": ["阴", "私处", "内裤", "腿间"],
    "阴": ["下面", "阴道", "阴蒂"],
    "屁股": ["屁屁", "臀"],
    "嘴": ["唇", "吻", "舌头"],
    "耳": ["耳垂", "耳朵"],
    "腿": ["大腿", "膝盖"],

    # —— 动作的 ——
    "猛烈": ["用力", "加重", "加大力度", "加快", "狠", "粗暴"],
    "用力": ["猛烈", "加重", "使劲"],
    "快": ["加快", "猛", "急切"],
    "慢": ["缓慢", "轻一点", "轻点"],
    "抽插": ["进出", "抽动", "动作"],
    "亲": ["吻", "亲亲", "啵", "mua"],
    "吻": ["亲", "长吻", "湿吻", "舌"],
    "摸": ["揉", "抚", "碰"],
    "揉": ["摸", "搓", "捏"],
    "舔": ["吮", "含", "吻"],
    "抱": ["搂", "拥", "抱紧"],
    "脱": ["褪", "解", "剥"],

    # —— 情绪的 ——
    "舒服": ["爽", "舒服死了", "舒服得", "欲仙欲死", "受不住"],
    "疼": ["痛", "难受", "紧"],
    "害羞": ["脸红", "耳朵烫", "发烫", "羞"],
    "想要": ["想要你", "要", "忍不住"],
    "忍不住": ["受不了", "撑不住", "没忍"],
    "娇喘": ["喘", "喘粗气", "喘得", "鼻音", "轻哼", "呻吟", "嗯"],
    "喘": ["喘粗气", "喘得断", "鼻音", "娇喘", "呼吸"],
    "呻吟": ["娇喘", "哼", "喘", "嗯"],
    "叫": ["喊", "出声", "哼", "呻吟"],

    # —— 地方的 ——
    "私人影院": ["影院", "看电影", "影厅"],
    "商场": ["逛街", "店里", "前台"],
    "浴池": ["洗澡", "浴缸", "水"],
    "床": ["床上", "被子", "枕头"],
}


def expand_query(q):
    """把查询按同义词扩一遍：原词 + 它的近亲，一起拿去搜。"""
    q = (q or "").strip()
    if not q:
        return [q]
    out = [q]
    for key, alts in SYNONYMS.items():
        if key in q:
            for alt in alts:
                # 用近义词替换掉原词，生成一个新查询
                out.append(q.replace(key, alt))
    # 去掉重复、太短的
    seen = set()
    uniq = []
    for x in out:
        x = x.strip()
        if len(x) < 2 or x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq[:8]          # 最多扩 8 条，别把服务拖慢

def search(q, n, entries, mem):
    # 同 server.py：先扩词再搜（两条链路必须一致，不然本地和云端搜出不同的东西）
    variants = expand_query(q)
    merged = {}
    for variant in variants:
        for item in _search_one(variant, n * 2, entries, mem):
            eid = item[2].get("id")
            if eid is None:
                continue
            if eid in merged:
                sc, st, e = merged[eid]
                merged[eid] = (sc + 0.6, st, e)
            else:
                merged[eid] = item
    return sorted(merged.values(), key=lambda x: -x[0])[:n]


def _search_one(q, n, entries, mem):
    """原来的单查询逻辑（供多轮扩展）"""
    qg = grams(q)
    qstr = re.sub(r"\s+", "", q or "")
    if not qg:
        return []
    scored = []
    now_ts = datetime.now(timezone.utc).timestamp()
    for e in entries:
        head = len(qg & e["_head"])
        body = len(qg & e["_body"])
        # 先按 gram 筛掉九成，再做全文包含（那一步很贵）
        if not head and not body:
            if not qstr:
                continue
            blob = (e.get("section", "") or "") + (e.get("title", "") or "") + (e.get("text", "") or "")
            if qstr not in blob:
                continue
            raw = True
        else:
            blob = (e.get("section", "") or "") + (e.get("title", "") or "") + (e.get("text", "") or "")
            raw = bool(qstr) and (qstr in blob)
        score = (head * 2.2 + body * 1.0) / (len(qg) ** 0.8)
        if raw:
            score += 3.0
            if qstr in ((e.get("section", "") or "") + (e.get("title", "") or "")):
                score += 1.5
        st = strength_of(e, mem, now_ts)
        if st < MIN_STRENGTH:
            continue
        score *= 0.45 + st
        # 种类权重（和云端 server.py 同一套）。
        KIND_W = {"intimate": 1.8, "core": 2.0, "identity": 1.3, "chat": 1.15, "diary": 1.2,
                  "user": 1.2, "decisions": 1.1, "meta": 1.0,
                  "live": 0.55, "learn": 0.5, "tech": 0.7, "debug": 0.5}
        score *= KIND_W.get(str(e.get("kind") or ""), 1.0)
        d = e.get("date") or ""
        if d:
            try:
                dd = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                age = max(0.0, (datetime.now(timezone.utc) - dd).total_seconds() / 86400)
                score *= 1.0 + 0.25 * math.exp(-age / 60.0)
            except Exception:
                pass
        scored.append((score, st, e))
    scored.sort(key=lambda x: -x[0])
    return scored[:n]


def touch_bg(ids):
    """后台把这个动作报给上游，让它记住「被想起过」——不阻塞输出。未配置则静默。"""
    if not ids or not TOUCH_URL:
        return
    payload = json.dumps({"ids": ids}).encode()
    try:
        subprocess.Popen(
            ["python3", "-c",
             "import urllib.request,sys;"
             "urllib.request.urlopen(urllib.request.Request(%r,data=%r,"
             "headers={'Content-Type':'application/json'}),timeout=4)"
             % (TOUCH_URL, payload)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def do_sync():
    if not SYNC_REMOTE:
        print("BRAIN_SYNC_REMOTE 未配置，跳过同步（不报错）")
        return 0
    remote = SYNC_REMOTE if SYNC_REMOTE.endswith("/") else SYNC_REMOTE + "/"
    os.makedirs(BRAIN_DIR, exist_ok=True)
    for f in ("entries.json", "state.json"):
        r = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                            remote + f, os.path.join(BRAIN_DIR, f)],
                           capture_output=True)
        print(f"{f}: {'ok' if r.returncode == 0 else '失败 ' + r.stderr.decode()[:80]}")
    return 0


def main():
    if "--sync" in sys.argv:
        return do_sync()
    q = sys.argv[1] if len(sys.argv) > 1 else ""
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    if not q:
        print('用法：brain_local.py "关键词" [条数]')
        return 1
    if not os.path.exists(ENTRIES):
        print("本地没有索引，先建索引（brain/index.py）或配 BRAIN_SYNC_REMOTE 后 --sync")
        return 1
    entries, mem = load()
    res = search(q, n, entries, mem)
    if not res:
        print("（没想到什么）")
        return 0
    for score, st, e in res:
        print(f"[{round(st,3)}] {e.get('title','')} / {e.get('section','')} ({e.get('date','')})")
        print("    " + (e.get("text") or "")[:220].replace("\n", " "))
    touch_bg([e.get("id") for _, _, e in res])
    return 0


if __name__ == "__main__":
    sys.exit(main())
