#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接线层：把记忆库接进任何 agent（dsh-soul-forging）。

三种用法：

  ① 命令行
       soul-boot                     打印开局注入块
       soul-boot --budget 12000      限制字数（超了从末尾截）
       soul-boot --list              看各部分多长、哪些被跳过
       soul-boot --mode memory-only  只要记忆，不要性格
       soul-boot --with index.md,NOW.md   自己挑要哪些文件

  ② 当模块用（Python）
       from soul import boot, recall, remember
       sys_prompt += boot(mode="memory-only")

  ③ 直接读文件
       就是那四个 markdown，自己拼也行

三种模式：
  full         四个文件全注入（默认）—— 想长性格的人
  memory-only  不注入 SOUL —— 只要记忆、不想动性格的人
  external     只注入 index + NOW —— 性格交给你自己 agent 的 prompt

设计原则：**只读，不写**。注入不产生副作用；要写记忆走 remember()。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))  # soul.py 就在仓库根目录
DATA_ROOT = os.environ.get("SOUL_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".soul-forging")
MEM = os.environ.get("MEMORY_DIR") or os.path.join(DATA_ROOT, "memory")

# 注入顺序就是重要性顺序：先是谁，再是什么规矩，再是目录，最后是此刻。
ALL_PARTS = ("SOUL.md", "MEMORY.md", "index.md", "NOW.md")

MODES = {
    "full": ALL_PARTS,
    # 不要性格：SOUL 不注入。空模板塞进去比不塞更糟——模型会看到"我的名字是（待填）"
    "memory-only": ("MEMORY.md", "index.md", "NOW.md"),
    # 性格归你自己的 agent：我们只管目录和此刻
    "external": ("index.md", "NOW.md"),
}

# 判断"这页还是空模板"：占位符太多就别注入，省的把模型带偏
PLACEHOLDER_MARKS = ("（待填", "(待填", "TODO", "（示例", "（还没有")
PLACEHOLDER_MIN = 3


def _read(name):
    p = os.path.join(MEM, name)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def is_placeholder(body):
    """空模板检测：占位符出现次数够多，就当这页还没填。"""
    return sum(body.count(m) for m in PLACEHOLDER_MARKS) >= PLACEHOLDER_MIN


def boot(budget=None, parts=None, header=True, mode=None, skip_empty=True):
    """拼出开局注入块。

    budget      字数上限（None = 不限制）
    parts       指定要哪些文件（优先级高于 mode）
    mode        full / memory-only / external
    skip_empty  自动跳过还是空模板的页（默认开）
    """
    use = tuple(parts) if parts else MODES.get(mode or "full", ALL_PARTS)
    chunks = []
    total = 0
    for name in use:
        body = _read(name)
        if not body:
            continue
        if skip_empty and is_placeholder(body):
            continue
        block = f"<!-- {name} -->\n{body}"
        if budget is not None and total + len(block) > budget:
            left = budget - total
            if left > 200:            # 剩一点就截，剩太少就整块不要
                chunks.append(block[:left] + "\n…（本块超预算被截断）")
                total += left + 20
            break
        chunks.append(block)
        total += len(block)
    body = "\n\n".join(chunks)
    if not body:
        # 什么都没填时不硬塞一句空话，明说
        return "（记忆库还是空的，暂时没有可注入的内容。）" if header else ""
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
    args = [sys.executable, os.path.join(ROOT, "bin", "soul"), "write", str(text)]
    for k in ("kind", "section", "summary", "salience"):
        if k in kw:
            args += [f"--{k}", str(kw[k])]
    out = subprocess.run(args, capture_output=True, text=True, timeout=20)
    return out.stdout.strip() or out.stderr.strip()


def _main(argv):
    budget = None
    if "--budget" in argv:
        budget = int(argv[argv.index("--budget") + 1])
    mode = None
    if "--mode" in argv:
        mode = argv[argv.index("--mode") + 1]
        if mode not in MODES:
            print(f"不认识的模式：{mode}（可选：{', '.join(MODES)}）")
            return 1
    parts = None
    if "--with" in argv:
        parts = tuple(x.strip() for x in argv[argv.index("--with") + 1].split(",") if x.strip())
    skip_empty = "--keep-empty" not in argv

    if "--list" in argv:
        use = parts or MODES.get(mode or "full", ALL_PARTS)
        print(f"模式：{mode or 'full'}")
        for name in ALL_PARTS:
            body = _read(name)
            if name not in use:
                tag = "不注入（模式）"
            elif not body:
                tag = "（空）"
            elif skip_empty and is_placeholder(body):
                tag = "空模板，已跳过"
            else:
                tag = "✓"
            print(f"  {name:16s} {len(body):6d} 字  {tag}")
        return 0

    if "--bare" in argv:
        print(boot(budget=budget, parts=parts, header=False, mode=mode, skip_empty=skip_empty))
        return 0
    print(boot(budget=budget, parts=parts, mode=mode, skip_empty=skip_empty))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
