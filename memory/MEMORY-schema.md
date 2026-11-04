# 记忆库结构说明

> 这份不注入，只在要改结构时读。

## 目录

```
memory/
├── SOUL.md            人格与灵魂（每轮注入）
├── MEMORY.md          操作规则（每轮注入）
├── index.md           路由表（每轮注入）
├── NOW.md             此刻（每轮注入）
├── BOOTSTRAP.md       铸魂清单
├── MEMORY-schema.md   本文件
├── log.md             时间线（append-only）
├── log-archive.md     老日志归档
├── NOW-archive.md     老「此刻」归档
├── core/              底座，永不删
├── identity/          我是谁、怎么变的
├── user/              主人
├── decisions/         决定与边界
├── diary/             日记
└── raw/               主人原话，只读
```

## frontmatter

每页开头：

```yaml
---
summary: 一句话摘要（≤80 字，index 用它）
salience: 1        # 1 热 / 2 温 / 3 冷
---
```

`summary` 是**路由用的**，不是正文摘要。写清楚"这页讲什么、值不值得点进去"。

## 注入策略

每轮注入：`SOUL.md` + `MEMORY.md` + `index.md` + `NOW.md`。
其余靠检索（`brain "关键词"`）现查。

**所以这四个文件要短。** 长了下不去，也烧钱。
