#!/usr/bin/env python3
"""brain_local_server — 本地常驻小脑检索（127.0.0.1，默认端口 3914）。

入包版：路径全部 env 化，不写死任何服务器绝对路径；同目录 import brain_local。

端点:
  GET  /health          探活
  GET  /topics          分类计数（text/plain）
  GET  /context        组装注入文本：core 全量 + ?q 命中 + ?body + 落 snapshot.md
  GET  /text?q=&n=      人话标题 + 日期 + 出处
  GET  /search?q=&n=    JSON 结果
  POST /reload          清模块缓存重读 entries.json（供 bin/sync 调用）

环境变量:
  BRAIN_PORT        监听端口（默认 3914）
  MEMORY_DIR        记忆根（默认 $SOUL_DATA_DIR/memory）
  BRAIN_DIR         脑数据目录（默认 $SOUL_DATA_DIR/brain）
  BRAIN_CORE_DIR    core/*.md 目录（默认 $MEMORY_DIR/core）
  BRAIN_BODIES_DIR  ?body= 读取目录（默认 $BRAIN_DIR/bodies；不存在则跳过 body 段）
  BRAIN_SNAPSHOT    合并快照落盘路径（默认 $BRAIN_DIR/snapshot.md）
  BRAIN_TOUCH_URL   /text /search 命中后异步回调地址（默认空；空或连不上静默）
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# 同目录导入兄弟模块（不再 sys.path 插 /srv、不再 importlib 按路径加载）
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
import brain_local as bl

DATA_ROOT = os.environ.get("SOUL_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".soul-forging")
MEMORY_DIR = os.environ.get("MEMORY_DIR") or os.path.join(DATA_ROOT, "memory")
BRAIN_DIR = os.environ.get("BRAIN_DIR") or os.path.join(DATA_ROOT, "brain")

PORT = int(os.environ.get("BRAIN_PORT") or "3914")
CORE_DIR = os.environ.get("BRAIN_CORE_DIR") or os.path.join(MEMORY_DIR, "core")
BODIES_DIR = os.environ.get("BRAIN_BODIES_DIR") or os.path.join(BRAIN_DIR, "bodies")
SNAPSHOT = os.environ.get("BRAIN_SNAPSHOT") or os.path.join(BRAIN_DIR, "snapshot.md")
TOUCH_URL = os.environ.get("BRAIN_TOUCH_URL", "").strip()

_lock = threading.Lock()
_cache = {"mtime": 0, "entries": None, "mem": {}}


def _touch_async(ids):
    """/text /search 命中后异步上报上游；未配置或连不上都静默。"""
    if not ids or not TOUCH_URL:
        return
    try:
        import urllib.request
        payload = json.dumps({"ids": ids}).encode()
        req = urllib.request.Request(TOUCH_URL, data=payload,
                                     headers={"Content-Type": "application/json"})
        threading.Thread(target=lambda: urllib.request.urlopen(req, timeout=3),
                         daemon=True).start()
    except Exception:
        pass


def reload_entries():
    """强制清空服务端缓存，下次 ensure() 重读 entries.json / state.json。"""
    with _lock:
        _cache["mtime"] = 0
        _cache["entries"] = None


def ensure():
    """索引或状态有更新就重载（加锁，避免并发重复加载）"""
    with _lock:
        em = os.path.getmtime(bl.ENTRIES) if os.path.exists(bl.ENTRIES) else 0
        sm = os.path.getmtime(bl.STATE) if os.path.exists(bl.STATE) else 0
        stamp = max(em, sm)
        if _cache["entries"] is None or stamp > _cache["mtime"]:
            _cache["entries"], _cache["mem"] = bl.load()
            _cache["mtime"] = stamp
        return _cache["entries"], _cache["mem"]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, text, code=200):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        raw = self.path
        try:  # http.server 按 latin-1 解码路径，先还原再按 utf-8 解，客户端才能直接传中文
            raw = raw.encode("latin-1").decode("utf-8")
        except Exception:
            pass
        u = urlparse(raw)
        qs = parse_qs(u.query)
        if u.path == "/health":
            entries, _ = ensure()
            return self._json({"ok": True, "entries": len(entries)})
        if u.path == "/topics":
            entries, _ = ensure()
            from collections import Counter
            c = Counter((e.get("section") or "").strip() for e in entries if (e.get("section") or "").strip())
            body = ("\n".join(f"{n:4d}  {k}" for k, n in c.most_common(60)) + "\n")
            return self._text(body)
        if u.path == "/context":
            q = (qs.get("q") or [""])[0]
            n = int((qs.get("n") or ["4"])[0])
            chunks = []
            try:
                names = sorted(f for f in os.listdir(CORE_DIR) if f.endswith(".md"))
            except OSError:
                names = []
            for name in names:
                if name.startswith("40-"):
                    # 索引永远带，但截断——目录是路由，丢了就找不着页
                    try:
                        with open(os.path.join(CORE_DIR, name), encoding="utf-8") as f:
                            txt = f.read().strip()
                    except OSError:
                        continue
                    if len(txt) > 2600:
                        cut = txt[:2600].rsplit("\n", 1)[0]
                        txt = cut + "\n…（索引已截断，完整版 `brain/index.md`）"
                    chunks.append(txt)
                    continue
                try:
                    with open(os.path.join(CORE_DIR, name), encoding="utf-8") as f:
                        chunks.append(f.read().strip())
                except OSError:
                    pass
            if q:
                try:
                    entries, mem = ensure()
                    res = bl.search(q, n, entries, mem)
                    if res:
                        lines = ["# 跟这句有关的记忆"]
                        for _sc, st2, e in res:
                            head = (e.get("head") or e.get("section") or e.get("title") or "").strip()
                            lines.append(f"- [{st2:.2f}] {head}（{e.get('date','')}）：{(e.get('text') or '')[:160]}")
                        chunks.append("\n".join(lines))
                except Exception:
                    pass
            # 身体说明：?body=dsh / qq —— 人是一颗脑子，出声的方式各走各的
            body_name = (qs.get("body") or [""])[0].strip()
            if body_name and body_name.replace("-", "").isalnum() and os.path.isdir(BODIES_DIR):
                try:
                    with open(os.path.join(BODIES_DIR, f"{body_name}.md"), encoding="utf-8") as f:
                        chunks.append(f.read().strip())
                except OSError:
                    pass
            text = "\n\n---\n\n".join(chunks) + "\n"
            # 每次组装都留一份合并快照：小脑服务挂了，兜底读它，内容一模一样。
            try:
                os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
                with open(SNAPSHOT, "w", encoding="utf-8") as f:
                    f.write(text)
            except OSError:
                pass
            return self._text(text)
        if u.path == "/text":
            q = (qs.get("q") or [""])[0]
            n = int((qs.get("n") or ["5"])[0])
            entries, mem = ensure()
            res = bl.search(q, n, entries, mem)
            if not res:
                lines = ["（没想到什么）"]
            else:
                lines = []
                byid = {x.get("id"): x for x in entries}
                for score, st, e in res:
                    head = (e.get("head") or e.get("section") or e.get("title") or "").strip()
                    src = e.get("page") or ""
                    lines.append(f"[{round(st,2)}] {head}")
                    lines.append(f"    {e.get('date','')} · {src} · {e.get('section','')}")
                    lines.append("    " + (e.get("text") or "")[:200].replace("\n", " "))
                    rels = [byid[r].get("head", "") for r in (e.get("rel") or [])[:2] if r in byid]
                    if rels:
                        lines.append("    ↳ 相关：" + " ｜ ".join(x[:18] for x in rels))
                _touch_async([e.get("id") for _, _, e in res])
            return self._text("\n".join(lines) + "\n")
        if u.path != "/search":
            return self._json({"error": "not found"}, 404)
        q = (qs.get("q") or [""])[0]
        n = int((qs.get("n") or ["5"])[0])
        t0 = time.time()
        entries, mem = ensure()
        res = bl.search(q, n, entries, mem)
        out = []
        for score, st, e in res:
            out.append({
                "id": e.get("id"), "title": e.get("title", ""), "section": e.get("section", ""),
                "kind": e.get("kind", ""), "date": e.get("date", ""),
                "text": (e.get("text") or "")[:700],
                "strength": round(st, 3), "score": round(score, 3),
            })
        self._json({"results": out, "ms": round((time.time() - t0) * 1000, 1)})
        # 异步报给上游，让「被想起」这件事被记住（失败无所谓）
        if out:
            _touch_async([r["id"] for r in out])

    def do_POST(self):
        raw = self.path
        try:
            raw = raw.encode("latin-1").decode("utf-8")
        except Exception:
            pass
        u = urlparse(raw)
        if u.path == "/reload":
            reload_entries()
            return self._json({"ok": True, "reloaded": True})
        return self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    ensure()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"brain-local 起来了：127.0.0.1:{PORT}（{len(_cache['entries'])} 条）", flush=True)
    srv.serve_forever()
