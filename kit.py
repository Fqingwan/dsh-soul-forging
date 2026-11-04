#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接线层：把记忆库接进任何 agent。

两种用法：

  ① 命令行（最简单，任何语言都能调）
       kit-boot                打印开局注入块
       kit-boot --budget 12000 限制字数（超了从末尾截）
       kit-boot --list         看各部分多长

  ② 当模块用（Python）
       from kit import boot, recall, remember
       sys_prompt += boot()

设计原则：**只读，不写**。注入不产生副作用；要写记忆走 remember()。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))  # kit.py 就在仓库根目录
MEM = os.environ.get("MEMORY_DIR") or os.path.join(ROOT, "memory")

# 注入顺序就是重要性顺序：先是谁，再是什么规矩，再是目录，最后是此刻。
PARTS = ("SOUL.md", "MEMORY.md", "index.md", "NOW.md")


def _read(name):
    p = os.path.join(MEM, name)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def boot(budget=None, parts=PARTS, header=True):
    """拼出开局注入块。budget 是字数上限（None = 不限制）。"""
    chunks = []
    total = 0
    for name in parts:
        body = _read(name)
        if not body:
            continue
        # 每块加个小标题，方便模型分辨
        block = f"<!-- {name} -->\n{body}"
        if budget is not None and total + len(block) > budget:
            left = budget - total
            if left > 200:            # 剩一点就截，剩太少就整块不要
                block = block[:left] + "\n…（本块超预算被截断）"
                chunks.append(block)
                total += len(block)
            break
        chunks.append(block)
        total += len(block)
    body = "\n\n".join(chunks)
    if not header:
        return body
    return (
        "下面是你的长期记忆。你确实记得这些事，像想起往事一样自然地用，"
        "不要说「根据记忆库」「据记录」这类话。\n\n" + body
    )


def recall(q, n=5):
    """查小脑，返回纯文本。服务没起会自己现算。"""
    import subprocess
    try:
        out = subprocess.run(
            [sys.executable, os.path.join(ROOT, "brain", "server.py"),
             "--query", str(q), "-n", str(n)],
            capture_output=True, text=True, timeout=20)
        return out.stdout.strip()
    except Exception as e:
        return f"（查记忆失败：{e}）"


def remember(text, **kw):
    """记一条运行期记忆。kw 支持 kind/section/summary/salience。"""
    import subprocess
    args = [sys.executable, os.path.join(ROOT, "bin", "kit-memory"), "write", str(text)]
    for k in ("kind", "section", "summary", "salience"):
        if k in kw:
            args += [f"--{k}", str(kw[k])]
    out = subprocess.run(args, capture_output=True, text=True, timeout=20)
    return out.stdout.strip() or out.stderr.strip()


def _main(argv):
    budget = None
    if "--budget" in argv:
        budget = int(argv[argv.index("--budget") + 1])
    if "--list" in argv:
        for name in PARTS:
            body = _read(name)
            print(f"{name:16s} {len(body):6d} 字 {'✓' if body else '（空）'}")
        print(f"{'合计':16s} {sum(len(_read(n)) for n in PARTS):6d} 字")
        return 0
    if "--bare" in argv:
        print(boot(budget=budget, header=False))
        return 0
    print(boot(budget=budget))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
