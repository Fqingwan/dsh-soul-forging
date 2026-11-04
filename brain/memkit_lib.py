#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""套件内部共用的东西：路径、frontmatter、live.jsonl 读写、摘要派生。

所有脚本都从这里拿路径，不要再各自写死。
"""
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.environ.get("MEMORY_DIR") or os.path.join(ROOT, "memory")
BRAIN = os.environ.get("BRAIN_DIR") or os.path.join(ROOT, "brain")
DOCS = os.environ.get("DOCS_DIR") or os.path.join(ROOT, "docs")
LIVE = os.path.join(BRAIN, "live.jsonl")
STATE = os.path.join(BRAIN, "state.json")

# 每轮注入的那四个 —— 它们不进小脑（否则自己搜自己）
INJECTED = {"SOUL.md", "MEMORY.md", "index.md", "NOW.md"}
META_ONLY = {"BOOTSTRAP.md", "MEMORY-schema.md", "README.md"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_front(text):
    """拆 frontmatter，返回 (meta, body)。"""
    meta = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return meta, text
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, text[m.end():]


def write_front(meta, body):
    lines = ["---"]
    for k, v in meta.items():
        if v is None or v == "":
            continue
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.lstrip("\n")


def derive_summary(text, limit=120):
    """摘要：≤limit 直接用原文；长文取第一句（12~limit）；再长截断加 …"""
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t:
        return ""
    if len(t) <= limit:
        return t
    m = re.search(r"[^。！？]*[。！？]", t)
    s = m.group(0).strip() if m else ""
    if len(s) < 12 or len(s) > limit:
        s = t[:limit]
    return s if len(s) <= limit else s[: limit - 1] + "…"


def read_live():
    """按行读 live.jsonl，跳过坏行（坏行不删，留给 fix-live-summary 处理）。"""
    out = []
    if not os.path.exists(LIVE):
        return out
    with open(LIVE, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                out.append((i, json.loads(line)))
            except Exception:
                out.append((i, None))
    return out


def append_live(rec):
    os.makedirs(BRAIN, exist_ok=True)
    with open(LIVE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def make_rec(text, kind="chat", section="", summary="", salience=2, source="local", rid=None):
    """live.jsonl 的标准记录。source 是双端互通的锚点：local / qq / web …"""
    t = (text or "").strip()
    return {
        "id": rid or f"{int(datetime.now().timestamp()*1000):x}{os.getpid()%100:02d}",
        "text": t,
        "summary": summary or derive_summary(t),
        "kind": kind,
        "section": section,
        "salience": int(salience),
        "date": today(),
        "at": now_iso(),
        "source": source,
    }


def atomic_write(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("touch", {})
    s.setdefault("forgotten", {})
    s.setdefault("pinned", {})
    return s


def save_state(s):
    atomic_write(STATE, json.dumps(s, ensure_ascii=False, indent=1))
