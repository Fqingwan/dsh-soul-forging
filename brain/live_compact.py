#!/usr/bin/env python3
"""小脑瘦身：按年龄分层压缩 live.jsonl，防止条目无限增长把检索拖慢。

入包版：路径与 LLM 凭证全部 env 化，不读任何本机 config.json；无 key 时 LLM 段静默，
压缩照常走 raw / 原样保留路径。只做一次性命令，不拉起常驻进程（由用户自挂 cron）。

  3 天内        → 原文不动（还记得清）
  3~7 天        → 轻度合并（同一天的多条并成一条，细节全留）
  7~15 天       → 压成摘要（2~3 句，留结论和名词）
  15~30 天      → 压成一句结论
  30~180 天     → 只留一行结果（不超过 30 字）
  180 天以上    → 删掉（除非标了 keep）

intimate 特权：<30 天 raw、<180 天 merge、再老只到 digest，永不 drop。

用法: python3 brain/live_compact.py [--dry] [--plan]
环境变量:
  BRAIN_DIR           脑数据目录（默认 $SOUL_DATA_DIR/brain）
  BRAIN_LIVE          live.jsonl 路径（默认 $BRAIN_DIR/live.jsonl）
  BRAIN_BACKUP_DIR    备份目录（默认 $BRAIN_DIR/live-backup，只留最近 10 份）
  BRAIN_COMPACT_LOG   日志路径（默认 $BRAIN_DIR/compact.log，超 1MB 轮转 .1）
  BRAIN_LLM_BASE_URL  OpenAI 兼容 base（默认空；空则 llm() 静默返回空串）
  BRAIN_LLM_API_KEY   API key（默认空）
  BRAIN_LLM_MODEL     模型名（默认空）
"""
import json
import os
import re
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone

DATA_ROOT = os.environ.get("SOUL_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".soul-forging")
BRAIN_DIR = os.environ.get("BRAIN_DIR") or os.path.join(DATA_ROOT, "brain")
LIVE = os.environ.get("BRAIN_LIVE") or os.path.join(BRAIN_DIR, "live.jsonl")
BACKUP_DIR = os.environ.get("BRAIN_BACKUP_DIR") or os.path.join(BRAIN_DIR, "live-backup")
LOG = os.environ.get("BRAIN_COMPACT_LOG") or os.path.join(BRAIN_DIR, "compact.log")

LLM_BASE = (os.environ.get("BRAIN_LLM_BASE_URL") or "").strip().rstrip("/")
LLM_KEY = (os.environ.get("BRAIN_LLM_API_KEY") or "").strip()
LLM_MODEL = (os.environ.get("BRAIN_LLM_MODEL") or "").strip()

# (天数上限, 档位名)
TIERS = [(3, "raw"), (7, "merge"), (15, "digest"), (30, "brief"), (180, "line")]
DROP_AFTER = 180

PROMPTS = {
    "merge": "把下面这几条合并成一条。要求：保留所有具体名词（模型名、文件名、软件名、数字、人名）、"
             "所有约定和结论；可以写得比单条长，但不要重复；不要列表，不要「以上」「这些」这种词。只输出合并后的记忆。",
    "digest": "把下面这几条压成一条摘要。要求：2~4 句，写清聊了什么、结论是什么，"
              "保留关键的具体名词（模型名、文件名、数字）；不要列表，不要空话。只输出摘要。",
    "brief": "把下面这段压成一句话，只留结论和最关键的那个名词。不超过 60 字。只输出这句话。",
    "line": "把下面这段压成一行，只留最重要的那个结果或事实，带上具体名词。不超过 30 字。只输出这一行。",
}
MAX_IN = 4000


def say(msg):
    line = f"[{datetime.now().strftime('%F %T')}] {msg}"
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if os.path.getsize(LOG) > 1_000_000:
            os.replace(LOG, LOG + ".1")
    except Exception:
        pass


def load_live():
    items = []
    try:
        with open(LIVE, encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                d.setdefault("id", f"anon{i}")
                items.append(d)
    except FileNotFoundError:
        pass
    return items


def save_live(items):
    tmp = LIVE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for d in items:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    os.replace(tmp, LIVE)


def age_days_of(d):
    raw = str(d.get("date") or "").strip()
    if raw:
        try:
            dd = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return max(0, (datetime.now(timezone.utc) - dd).days)
        except Exception:
            pass
    at = d.get("at")
    if isinstance(at, (int, float)) and at > 0:
        return max(0, int((time.time() - at / 1000) / 86400))
    return 0


def topic_of(d):
    """同一天里不同主题不能混着压——否则「独立游戏」和「乳糖不耐」会被压成一句话，
    两个都不剩。所以按 section 分段：去掉时间戳那一段，剩下当主题。"""
    sec = str(d.get("section") or "").strip()
    parts = [p.strip() for p in sec.split("·") if p.strip()]
    parts = [p for p in parts if not re.match(r"^\d{1,2}:\d{2}$", p)]
    return "·".join(parts) or "杂"


def bucket_of(tier, d):
    """同一档位里按什么粒度归并。越久越粗，条目数才不会线性涨。
    merge 按天、digest 按周、brief 按半月、line 按月。"""
    raw = str(d.get("date") or "").strip()
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d")
    except Exception:
        return "unknown"
    if tier == "merge":
        return dt.strftime("%Y-%m-%d")
    if tier == "digest":
        y, w, _ = dt.isocalendar()
        return f"{y}-W{w:02d}"
    if tier == "brief":
        half = 1 if dt.day <= 15 else 2
        return f"{dt.year}-{dt.month:02d}-H{half}"
    if tier == "line":
        return f"{dt.year}-{dt.month:02d}"
    return dt.strftime("%Y-%m-%d")


def tier_of(days, kind=""):
    """亲密记忆（intimate）走特权路线：压得慢、永不删。"""
    if kind == "intimate":
        if days < 30:
            return "raw"
        if days < 180:
            return "merge"
        return "digest"
    for limit, name in TIERS:
        if days < limit:
            return name
    return "drop"


def llm(messages, max_tokens=800):
    """OpenAI 兼容 /chat/completions；未配置 base/key 时静默返回空串，失败也返回空串。"""
    if not (LLM_BASE and LLM_KEY and LLM_MODEL):
        return ""
    try:
        body = json.dumps({
            "model": LLM_MODEL, "messages": messages,
            "temperature": 0.6, "max_tokens": max_tokens,
        }).encode("utf-8")
        req = urllib.request.Request(
            LLM_BASE + "/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {LLM_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    except Exception as e:
        say(f"✗ LLM 失败：{e}")
        return ""


def combine(group, level):
    """把一组条目压成一条；返回新条目，失败返回 None"""
    parts = []
    for d in group:
        head = str(d.get("section") or "").strip()
        text = str(d.get("text") or "").strip()
        parts.append(f"（{head}）{text}" if head else text)
    src = "\n".join(parts)[:MAX_IN]
    out = llm([
        {"role": "system", "content": PROMPTS[level]},
        {"role": "user", "content": src},
    ], max_tokens=600 if level in ("merge", "digest") else 200)
    out = re.sub(r"\s*\n+\s*", " ", out or "").strip()
    if not out:
        return None
    keep = any(bool(d.get("keep")) for d in group)
    tags = "chat" if all(str(d.get("tags") or "").startswith("chat") for d in group) else "qq"
    return {
        "id": f"c{int(time.time())}{len(group)}",
        "at": int(time.time() * 1000),
        "date": min(str(d.get("date") or "") for d in group if d.get("date")) or
                datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "section": f"合并·{len(group)}条",
        "text": out[:1400],
        "salience": min(int(d.get("salience") or 2) for d in group),
        "tags": tags,
        "kind": str(group[0].get("kind") or "live"),
        "compacted": level,
        "keep": keep,
    }


def main(argv):
    dry = "--dry" in argv
    items = load_live()
    before = len(items)
    if not before:
        say("live.jsonl 是空的，不用瘦身")
        return 0

    keepers, drops, work = [], [], {}
    for d in items:
        days = age_days_of(d)
        tier = tier_of(days, str(d.get("kind") or ""))
        if tier == "raw":
            keepers.append(d)
        elif tier == "drop":
            if bool(d.get("keep")) or str(d.get("kind")) in ("vow",):
                keepers.append(d)          # 标了 keep 的一律不动
            else:
                drops.append(d)
        else:
            is_int = str(d.get("kind") or "") == "intimate"
            bkey = str(d.get("date") or "?") if is_int else bucket_of(tier, d)
            work.setdefault((tier, bkey, topic_of(d)), []).append(d)

    say(f"开始瘦身：共 {before} 条；保留原样 {len(keepers)}；待压缩 {sum(len(v) for v in work.values())}；待删 {len(drops)}")

    if "--plan" in argv:
        # 只算账，不调模型、不写盘——用来验证「条目数到底有没有上界」
        after_plan = len(keepers) + len(work)
        print(f"现在 {before} 条 → 瘦身后约 {after_plan} 条"
              f"（原样 {len(keepers)} + 压成 {len(work)} 组 + 删 {len(drops)}）")
        for (tier, bucket, topic), g in sorted(work.items()):
            print(f"  {tier:6} {bucket:12} {topic:18} {len(g):3} 条 → 1")
        return 0

    added = []
    for (tier, bucket, topic), group in sorted(work.items()):
        if len(group) == 1:
            keepers.append(group[0])       # 单独一条压成一条是白调模型，原样留着
            continue
        new = combine(group, tier)
        if new is None:
            keepers.extend(group)          # 压失败就原样留着，宁多勿丢
            say(f"⚠ {tier}/{bucket}/{topic} 压缩失败，{len(group)} 条保留原样")
        else:
            added.append(new)
            say(f"✓ {tier}/{bucket}/{topic}：{len(group)} 条 → 1 条（{len(new['text'])} 字）")

    after_items = keepers + added
    after = len(after_items)
    say(f"瘦身后：{after} 条（原 {before}，压缩掉 {len(drops) + sum(len(v) for v in work.values()) - len(added)} 条）")

    if dry:
        say("（--dry 只报告，不写文件）")
        return 0

    if after >= before:
        say("没有可瘦身的，跳过写盘")
        return 0

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(LIVE, os.path.join(BACKUP_DIR, f"live-{stamp}.jsonl"))
    # 备份只留最近 10 份
    olds = sorted(os.listdir(BACKUP_DIR))[:-10]
    for f in olds:
        try:
            os.unlink(os.path.join(BACKUP_DIR, f))
        except Exception:
            pass

    save_live(after_items)
    say(f"✓ 已写盘（备份 live-{stamp}.jsonl）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
