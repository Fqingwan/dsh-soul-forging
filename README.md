# 记忆套件（memory kit）

给 AI 助手用的**可迁移长期记忆**：一份 markdown 记忆库 + 一个小脑检索层 + 一套铸魂流程。

**纯本地，不需要服务器。** 有一个 Python 3 就能跑起来。

---

## 它解决什么

大模型每开一次会话就是一张白纸。这东西给它三样东西：

1. **记得**——重要的东西落在 markdown 里，下次开局自动注入
2. **查得到**——记忆多了塞不进上下文，就用小脑按关键词现查（毫秒级）
3. **能长**——性格不是写死的设定，是一点点长出来的，而且长成什么样有据可查

---

## 三层结构

| 层 | 在哪 | 谁看 |
|---|---|---|
| **注入层** | `SOUL.md` `MEMORY.md` `index.md` `NOW.md` | 每轮对话都读，所以必须短 |
| **检索层（小脑）** | `brain/entries.json` | 想起来才查，几毫秒 |
| **外置层** | `docs/tech` `docs/debug` | 不进上下文，出错时才翻 |

一句话：**该记的记，该忘的忘，该查的查。**

---

## 装

```bash
bash install.sh
```

需要 Python 3.8+。不需要服务器、不需要数据库、不需要 npm。

---

## 用

```bash
brain "关键词"                  # 查小脑
brain --topics                  # 看有哪些分类
bin/kit-memory write "内容"     # 记一条运行期记忆
bin/kit-memory index            # 重建索引
bin/kit-memory check            # 体检（漏登记/断链/缺摘要）
bin/kit-memory digest           # 收尾该做哪四件事
bin/sync                        # 一键：建索引 + 重载 + 体检
bash bin/serve                  # 起常驻检索服务（可选）
```

---

## 目录

```
memory/          记忆库（你的全部内容都在这）
├── SOUL.md        人格与灵魂        ← 铸魂时填
├── MEMORY.md      操作规则
├── index.md       路由表
├── NOW.md         此刻
├── BOOTSTRAP.md   铸魂清单          ← 装完先跑这个
├── log.md         时间线
├── core/          底座，永不删
├── identity/      我是谁、怎么变的
├── user/          主人是谁
├── decisions/     定下来的事
├── diary/         日记
└── raw/           主人原话，只读

brain/           索引与检索（一般不用管）
bin/             命令行工具
docs/tech/       技术结论（进小脑，查得到）
docs/debug/      调试过程（不注入，用 debug-recall 查）
```

---

## 铸魂

装完的第一件事不是干活，是**先把"我是谁"聊清楚**。

打开 `memory/BOOTSTRAP.md`，按清单一项项来：名字、性格、价值观、边界、主人是谁、想要什么样的陪伴。
一次推进一项，**别一口气问完**——那是问卷，不是聊天。

写回文件之后才勾选。全部完成 → `status: complete` + `bash bin/sync`。

想重来一遍：把 `status` 改回 `pending` 就行，**已有记忆不会被清掉**——重铸的是性格，不是记忆。

---

## 设计取舍（为什么这么写）

- **为什么是 markdown**：能读、能改、能 diff、能提交 git、能一键搬走。不会被锁死在某个数据库里。
- **为什么分三层**：注入层越短越好（省钱、不压人）；检索层解决"记多了塞不下"；外置层让调试记录不污染性格。
- **为什么记忆有强度**：不是所有记忆一样重。`salience:1` 几乎不忘，`3` 会自己淡掉。被反复想起的会变牢。
- **为什么不带服务器**：一个人用不需要。要云备份就设 `MEMKIT_BACKUP_CMD`，没有也完整。

---

## 云备份（可选）

```bash
export MEMKIT_BACKUP_CMD='cd /path/to/kit && tar czf ~/backup.tgz memory'
```

设了这条，`bin/sync` 每次会顺带跑一遍。没设就不跑。

---

## 授权

本套件代码 MIT。记忆内容（`memory/`）是你自己的。

底层思路参考了 [dsh-plugin-memory](https://github.com/LittleBlackTong/dsh-plugin-memory)（MIT），
在这一版里是**重写实现**，没有复制它的代码；如果你把它当插件装进 DSH，那份要单独保留它的 LICENSE。
