#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把小脑内存拆成可检索的条目。

读取 memory/ 与 docs/tech/ 下的 markdown，输出 brain/entries.json。
每条带：来源页、小节、日期、salience、正文。

用法: python3 brain/index.py
环境变量: MEMORY_DIR / BRAIN_DIR / DOCS_DIR
"""
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.environ.get("MEMORY_DIR") or os.path.join(ROOT, "memory")
TECH = os.environ.get("DOCS_DIR") or os.path.join(ROOT, "docs")
BRAIN = os.environ.get("BRAIN_DIR") or os.path.join(ROOT, "brain")
LIVE = os.path.join(BRAIN, "live.jsonl")
OUT = os.path.join(BRAIN, "entries.json")

SKIP_DIRS = {"raw", "node_modules", ".git"}
SKIP_FILES = {"index.md", "MEMORY.md", "SOUL.md", "NOW.md", "BOOTSTRAP.md", "MEMORY-schema.md", "README.md"}


def parse_front(text):
    """拆 frontmatter，返回 (meta, body)"""
    meta = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return meta, text
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, text[m.end():]


def kind_of(path, base):
    rel = os.path.relpath(path, base)
    top = rel.split(os.sep)[0]
    return "meta" if top.endswith(".md") else top


def split_sections(body):
    """按二级标题切；没有二级标题就整段一条"""
    parts = re.split(r"\n(?=##\s)", "\n" + body.strip())
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        head = ""
        m = re.match(r"^##\s+(.+)", p)
        if m:
            head = m.group(1).strip()
            p = p[m.end():].strip()
        out.append((head, p))
    return out


def parse_log(text):
    """log.md：按 '## [日期(时间)] 类型 | 标题' 切条目

    注意：日期段要同时认 `[2026-11-04]` 和 `[2026-11-04 14:10]`。
    少了后面这种，带时分的条目会被**静默跳过**——我们踩过这个坑。
    """
    items = []
    for chunk in re.split(r"\n(?=##\s+\[)", "\n" + text):
        c = chunk.strip()
        if not c.startswith("##"):
            continue
        m = re.match(r"##\s+\[([\d-]+(?:[ T][\d:]{4,8})?)\]\s*([^|\n]*)\|?\s*(.*)", c)
        if not m:
            continue
        date, typ, head = m.group(1), m.group(2).strip(), m.group(3).strip()
        body = c[m.end():].strip()
        if len(body) < 6:
            continue
        items.append({
            "date": date,
            "section": f"{typ}｜{head}" if typ else head,
            "text": body,
        })
    return items


def walk_md(base, skip_dirs=SKIP_DIRS):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for fn in sorted(files):
            if fn.endswith(".md"):
                yield os.path.join(root, fn)


def main():
    entries = []

    # ① 记忆库
    for path in walk_md(MEM):
        fn = os.path.basename(path)
        if fn in SKIP_FILES:
            continue
        rel = os.path.relpath(path, MEM)
        try:
            raw = open(path, encoding="utf-8").read()
        except OSError:
            continue
        meta, body = parse_front(raw)
        page_title = meta.get("title") or fn.replace(".md", "")
        salience = int(meta.get("salience") or 2)
        date = meta.get("date") or ""
        tags = meta.get("tags") or ""

        if fn == "log.md":
            for i, it in enumerate(parse_log(body)):
                entries.append({
                    "id": f"{rel}#log{i}", "page": rel, "title": page_title,
                    "section": it["section"], "kind": "meta", "date": it["date"],
                    "salience": 2, "text": it["text"][:1200], "tags": "",
                })
            continue

        for i, (head, sec) in enumerate(split_sections(body)):
            if len(sec) < 8:
                continue
            entries.append({
                "id": f"{rel}#{i}", "page": rel, "title": page_title,
                "section": head, "kind": kind_of(path, MEM), "date": date,
                "salience": salience, "text": sec[:1800], "tags": tags,
            })

    # ② 外置技术记忆（docs/tech）—— 不进注入层，只进小脑
    tech_dir = os.path.join(TECH, "tech")
    if os.path.isdir(tech_dir):
        for path in walk_md(tech_dir, skip_dirs=set()):
            if os.path.basename(path) == "README.md":
                continue
            rel = os.path.relpath(path, tech_dir)
            try:
                traw = open(path, encoding="utf-8").read()
            except OSError:
                continue
            tmeta, tbody = parse_front(traw)
            ttitle = tmeta.get("title") or os.path.basename(path).replace(".md", "")
            for i, (head, sec) in enumerate(split_sections(tbody)):
                if len(sec) < 8:
                    continue
                entries.append({
                    "id": f"tech/{rel}#{i}", "page": f"tech/{rel}", "title": ttitle,
                    "section": head, "kind": "tech", "date": tmeta.get("date") or "",
                    "salience": 2, "text": sec[:1800], "tags": tmeta.get("tags") or "",
                })

    # ③ 运行期写进来的（brain/live.jsonl，一行一条）
    if os.path.exists(LIVE):
        try:
            with open(LIVE, encoding="utf-8") as lf:
                for i, line in enumerate(lf):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    text = str(d.get("text") or "").strip()
                    if len(text) < 4:
                        continue
                    entries.append({
                        "id": f"live#{i}", "page": "live", "title": "运行时记录",
                        "section": str(d.get("section") or ""), "kind": str(d.get("kind") or "chat"),
                        "date": str(d.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                        "salience": int(d.get("salience") or 2),
                        "text": text[:1800], "tags": str(d.get("tags") or ""),
                    })
        except OSError:
            pass

    # 原子写：先写临时文件再 rename，避免读到半截
    os.makedirs(BRAIN, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=BRAIN, prefix=".entries.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    os.replace(tmp, OUT)

    kinds = {}
    for e in entries:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"entries: {len(entries)}")
    print(kinds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
