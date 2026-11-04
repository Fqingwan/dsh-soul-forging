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

有两种用法，按你需要挑：

### 用法 A：当 DSH 插件（记忆自动注入）

```bash
# 1) 铺一份空白记忆库到 ~/.memkit/memory
bash bin/init-home

# 2) 装进 DSH 的 profile
dsh plugin add dsh-memkit          # 发布到 npm 后
# 或者从本地目录装：
dsh plugin add /path/to/dsh-memkit

# 3) 重开 DSH，记忆会自动注入
```

装好后每轮对话开头都会自动带上 `~/.memkit/memory` 里的那四个文件。
想换位置：配置里设 `memoryDir`，或设环境变量 `MEMORY_DIR`。

### 用法 B：只要命令行（不装插件）

```bash
bash install.sh
```

适合接自己的 agent、或者只想用它的检索能力。需要 Python 3.8+。

**两种都不需要服务器、不需要数据库。**

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

## 插件形态的配置

如果装成 DSH 插件，这几个可以在 profile 配置里覆盖：

| 配置 | 默认 | 说明 |
|---|---|---|
| `memoryDir` | `~/.memkit/memory` | 记忆库位置 |
| `bootMaxChars` | `20000` | 注入字数上限 |
| `autoInject` | `true` | 关掉就不注入（只留命令行） |
| `registerSkill` | `true` | 关掉就不注册 memkit 技能 |

插件本体在 `lib/plugin.js`，就一百多行：**只读四个 markdown，拼成一块注入，不写任何文件**。

---

## 接进你的 agent（接线层）

这套东西不会自己长在模型身上——**你得在每轮开头把记忆喂进去**。三种接法：

**① 命令行（任何语言都能调）**

```bash
kit-boot                 # 打印开局注入块，拼到 system prompt 最前面
kit-boot --budget 12000  # 限制字数（超了从末尾截，先保 SOUL）
kit-boot --list          # 看四个文件各多长
```

**② Python 模块**

```python
from kit import boot, recall, remember

system_prompt = "你是一个助手…\n\n" + boot()      # 开局注入
context       = recall("他说过在意什么", n=3)      # 想起来了就查
remember("今天他说想换个方向", kind="chat")        # 记一条
```

**③ 直接读文件**

就是四个 markdown：`SOUL.md` `MEMORY.md` `index.md` `NOW.md`。
想自己控制格式就自己拼，效果一样。

> **注意**：`boot()` 只管注入，**不改任何文件**。要写记忆走 `remember()`。
> 注入块默认 3.4K 字左右——这就是"每轮要花的固定开销"，觉得贵就调 `--budget`，
> 或者定期把四个文件压瘦。

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
