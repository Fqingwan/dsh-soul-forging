#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小脑检索服务（本地 HTTP，默认 127.0.0.1:3914）。

为什么要有它：每次检索都重新读 json 太慢，而且 agent 在对话里要反复查。
起一个常驻进程，索引在内存里，一次查询几毫秒。

端点：
  GET  /text?q=词&n=5     纯文本结果（给人/给模型直接看）
  GET  /search?q=词&n=5   JSON 结果
  GET  /topics            有哪些分类、各多少条
  GET  /recent?kind=diary&n=5   按分类取最近的
  POST /reload            重读 entries.json（索引重建后调）
  POST /touch  {"id":..}  标记"被想起了"，影响强度
  GET  /health            存活检查

用法: python3 brain/server.py [--port 3914]
"""
import json
import math
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAIN = os.environ.get("BRAIN_DIR") or os.path.join(ROOT, "brain")
ENTRIES = os.path.join(BRAIN, "entries.json")
STATE = os.path.join(BRAIN, "state.json")
PORT = int(os.environ.get("BRAIN_PORT") or 3914)

_lock = threading.Lock()
_data = {"entries": [], "by_id": {}, "built": 0}
_state = {"touch": {}}


# ---------- 强度模型 ----------
# 强度决定一条记忆"还在不在"：查得到，但太弱的会被过滤掉。
# 规则要能讲明白，所以很简单：
#   salience 1 衰减极慢（几乎不忘）· 2 中等 · 3 快
#   被想起一次 +一点；越常被想起越牢
BASE = {1: 1.0, 2: 0.75, 3: 0.5}
HALFLIFE = {1: 720, 2: 180, 3: 45}   # 天


def strength_of(e):
    sal = int(e.get("salience") or 2)
    base = BASE.get(sal, 0.75)
    age = age_days(e.get("date") or "")
    decay = math.exp(-age / HALFLIFE.get(sal, 180)) if age is not None else 1.0
    hits = _state["touch"].get(e.get("id"), 0)
    bonus = min(0.35, hits * 0.05)
    val = base * decay + bonus
    # 钉住的记忆不再淡掉 —— "我特意找回的东西，就该一直在"
    if e.get("id") in (_state.get("pinned") or {}):
        val = max(val, 0.6)
    return max(0.0, min(1.0, val))


def age_days(d):
    if not d:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            dd = datetime.strptime(d[:16] if fmt.endswith("%H:%M") else d[:10], fmt)
            dd = dd.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - dd).total_seconds() / 86400)
        except Exception:
            continue
    return None


# ---------- 打分 ----------
def grams(s, k=2):
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", s or "")
    out = set()
    for seg in s.split():
        if len(seg) < k:
            if seg:
                out.add(seg)
            continue
        for i in range(len(seg) - k + 1):
            out.add(seg[i:i + k])
    return out


def search(q, n=5, min_strength=0.12):
    qs = re.sub(r"\s+", "", q or "")
    if not qs:
        return []
    qg = grams(q, k=1) if len(qs) == 1 else grams(q)
    if not qg:
        return []
    scored = []
    for e in _data["entries"]:
        head_hit = len(qg & e["_head"])
        body_hit = len(qg & e["_body"])
        raw_hit = qs in (e.get("section", "") + e.get("title", "") + e.get("text", ""))
        if not head_hit and not body_hit and not raw_hit:
            continue
        st = strength_of(e)
        if st < min_strength:
            continue
        score = (head_hit * 2.2 + body_hit * 1.0) / (len(qg) ** 0.8)
        if raw_hit:
            score += 3.0
            if qs in (e.get("section", "") + e.get("title", "")):
                score += 1.5
        score *= 0.45 + st
        age = age_days(e.get("date") or "")
        if age is not None:
            score *= 1.0 + 0.25 * math.exp(-age / 60.0)
        scored.append((score, st, e))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, st, e in scored[:n]:
        out.append({
            "id": e["id"], "page": e.get("page", ""), "title": e.get("title", ""), "section": e.get("section", ""),
            "kind": e.get("kind", ""), "date": e.get("date", ""),
            "text": (e.get("text") or "")[:700],
            "strength": round(st, 3), "score": round(score, 3),
            "age_days": None if age_days(e.get("date") or "") is None else round(age_days(e.get("date") or ""), 1),
        })
    return out


def fmt_text(rows):
    if not rows:
        return "（没有找到相关的记忆）"
    out = []
    for r in rows:
        head = r["section"] or r["title"]
        out.append(f"[{r['strength']:.2f}] {head}\n    {r['date']} · {r.get('page') or r['kind']}\n    {r['text'][:300]}")
    return "\n".join(out)


# ---------- 数据装载 ----------
def reload_data():
    global _data
    entries = []
    try:
        with open(ENTRIES, encoding="utf-8") as f:
            entries = json.load(f)
    except Exception:
        entries = []
    for e in entries:
        e["_head"] = grams(e.get("section", "") + " " + e.get("title", ""))
        e["_body"] = grams(e.get("text", ""))
    _data = {
        "entries": entries,
        "by_id": {e["id"]: e for e in entries},
        "built": time.time(),
    }
    return len(entries)


def load_state():
    global _state
    try:
        with open(STATE, encoding="utf-8") as f:
            _state = json.load(f)
    except Exception:
        _state = {"touch": {}}
    _state.setdefault("touch", {})


def save_state():
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f)
        os.replace(tmp, STATE)
    except Exception:
        pass


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        q = (qs.get("q") or [""])[0]
        n = int((qs.get("n") or ["5"])[0])
        with _lock:
            if u.path in ("/text", "/search"):
                rows = search(q, n)
                if u.path == "/text":
                    return self._send(200, fmt_text(rows), "text/plain; charset=utf-8")
                return self._send(200, json.dumps({"query": q, "results": rows}, ensure_ascii=False))
            if u.path == "/topics":
                kinds = {}
                for e in _data["entries"]:
                    kinds[e.get("kind", "")] = kinds.get(e.get("kind", ""), 0) + 1
                return self._send(200, json.dumps(kinds, ensure_ascii=False, indent=1))
            if u.path == "/recent":
                kind = (qs.get("kind") or [""])[0]
                rows = [e for e in _data["entries"] if not kind or e.get("kind") == kind]
                rows.sort(key=lambda e: (e.get("date") or ""), reverse=True)
                out = [{"id": e["id"], "title": e.get("title"), "section": e.get("section"),
                        "kind": e.get("kind"), "date": e.get("date"),
                        "text": (e.get("text") or "")[:300]} for e in rows[:n]]
                return self._send(200, json.dumps({"results": out}, ensure_ascii=False))
            if u.path == "/health":
                return self._send(200, json.dumps({"ok": True, "entries": len(_data["entries"])}))
        return self._send(404, json.dumps({"ok": False, "msg": "unknown path"}))

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        with _lock:
            if u.path == "/reload":
                load_state()          # 遗忘/钉住的状态也要重读，不然改了不生效
                cnt = reload_data()
                return self._send(200, json.dumps({"ok": True, "count": cnt}))
            if u.path == "/touch":
                try:
                    d = json.loads(body or b"{}")
                    sid = d.get("id")
                except Exception:
                    sid = None
                if sid and sid in _data["by_id"]:
                    _state["touch"][sid] = _state["touch"].get(sid, 0) + 1
                    save_state()
                    return self._send(200, json.dumps({"ok": True}))
                return self._send(404, json.dumps({"ok": False}))
        return self._send(404, json.dumps({"ok": False, "msg": "unknown path"}))


def main():
    # 单次查询模式：不起服务，直接算完打印。给 bin/brain 当兜底用。
    if "--query" in sys.argv:
        i = sys.argv.index("--query")
        q = sys.argv[i + 1] if len(sys.argv) > i + 1 else ""
        n = 5
        if "-n" in sys.argv:
            n = int(sys.argv[sys.argv.index("-n") + 1])
        load_state()
        reload_data()
        print(fmt_text(search(q, n)))
        return

    port = PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    load_state()
    cnt = reload_data()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"小脑检索服务已启动 http://127.0.0.1:{port} · {cnt} 条", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
