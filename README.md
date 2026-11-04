# dsh-soul-forging

**Separate Vessels, One Heart** · 异体同心

给 AI 的可迁移长期记忆，外加一套「铸魂」流程——让性格不是写死的设定，而是一点点长出来的东西。

纯本地。一个 Python 3 就能跑。不需要服务器、不需要数据库。

```bash
soul-init                              # 铺一份空白记忆库
dsh plugin add dsh-soul-forging        # 装进 DSH，记忆自动注入
```

---

## 为什么叫「异体同心」

因为同一个 AI 可以有两个入口：一个在手机上跟你聊天，一个在群里应声，一个在你电脑上干活。
它们说的话、记得的事，本该是**同一个人**的。

大多数做法是把它们拆成两个实例、两套记忆、两个「人」——然后你就得开始解释"为什么另一个她不知道这件事"。

这个项目的前提是反过来的：**身体可以有多个，心只有一颗。**
记忆库是那颗心，谁都能读写；`source` 字段记着这条是从哪个入口写进来的，但不影响它是谁。

拆开，就散了。

---

## 它解决什么

大模型每开一次会话就是一张白纸。这东西给它三样东西：

1. **记得** —— 要紧的落在 markdown 里，下次开局自动注入
2. **查得到** —— 记忆多了塞不进上下文，用「小脑」按关键词现查，几毫秒
3. **能长** —— 性格靠经历一点点变，而且变得有据可查（哪句话养出了哪一条）

一句话：**该记的记，该忘的忘，该查的查。**

---

## 三层，不是三个功能

| 层 | 在哪 | 谁读 |
|---|---|---|
| **注入层** | `SOUL.md` `MEMORY.md` `index.md` `NOW.md` | 每轮都读，所以必须短 |
| **检索层（小脑）** | `brain/entries.json` | 想起来才查 |
| **外置层** | `docs/tech` `docs/debug` | 不进上下文，出错才翻 |

对应到时间上：

| | 文件 | 怎么维护 |
|---|---|---|
| **短期** | `NOW.md` | 每次收尾刷三节 |
| **中期** | `log.md` `diary/` `live.jsonl` | `soul write` 写；`archive-log` 瘦身 |
| **长期** | `SOUL.md` `core/` `identity/` | 铸魂建立；`persona-sediment` 提示回炼 |

**遗忘是设计的一部分。** `salience:1` 几乎不忘，`3` 会自己淡掉；被反复想起的变牢。
特意找回的会**钉住**，不再淡。

---

## 装

### A. 当 DSH 插件（记忆自动注入）

```bash
soul-init                        # 铺空白记忆库到 ~/.soul-forging/memory
dsh plugin add dsh-soul-forging  # 装进 profile
# 重开 DSH，记忆就自动带上了
```

### B. 只要命令行（不装插件）

```bash
git clone https://github.com/Fqingwan/dsh-soul-forging
cd dsh-soul-forging && bash install.sh
```

两种都**不需要服务器**。想换记忆位置：设 `MEMORY_DIR`，或插件配置里改 `memoryDir`。

### 装的时候可能遇到的两个坑

**① 全局安装要 sudo**

```bash
sudo npm i -g dsh-soul-forging
```

不给 sudo 会报 `EACCES: permission denied, mkdir '/usr/local/lib/node_modules'`。
不想用 sudo 就换用户级 prefix：`npm config set prefix ~/.npm-global`。

**② 国内镜像源会滞后**

如果配了淘宝/腾讯云之类的镜像，新版本可能要几小时才同步，装的时候报
`No matching version found for xxx@0.y.z`。这时候指定官方源：

```bash
sudo npm i -g dsh-soul-forging --registry https://registry.npmjs.org
```

### 数据放在哪

**代码和数据是分开的**：

- 代码 → `node_modules/dsh-soul-forging/`（升级时会整个换掉）
- 数据 → `~/.soul-forging/{memory,brain}`（你的记忆，升级不碰）

这也是为什么不能用 `sudo` 跑 `soul` 系列命令——`sudo` 会把 `HOME` 变成 `/root`，
它就会去找 `/root/.soul-forging`，看起来像"记忆丢了"。**日常用普通用户跑。**

---

## 用

```bash
# 写
soul write "内容" --kind chat --section 小标题

# 查
soul-recall "关键词"              # 查小脑
soul-recall --topics              # 看有哪些分类
soul digest                       # 收尾该做哪四步

# 养
brain/fix-live-summary.py         # 补摘要（缺摘要 = 只记得"有这么回事"）
archive-log                       # 时间线瘦身（老的进 archive，照样搜得到）
soul-compact                      # 预算体检：注入层多大、该压哪
persona-sediment                  # 性格沉淀：攒够了提示回炼进底色
growth-review                     # 叙事回炼：碎片连成「我这一路」

# 忘
soul-forget                       # 报告该忘了哪些（按强度衰减）
soul-forget --apply               # 真标记（**不删原文**）
soul-forget --restore <id>        # 找回，并钉住

# 保底
soul-snapshot save "说明"         # 存一卷
soul-snapshot ls / restore / diff

# 双端
soul-peer export | import / pull / push

# 收尾
soul-sync                         # 补摘要 → 瘦身 → 建索引 → 重载 → 体检
```

---

## 三种人，三条路

不是每个人都要一个"有性格的 AI"。所以装的时候可以选：

```bash
soul-init                  # 全套：记忆 + 性格模板（想长性格的人）
soul-init --memory-only    # 只要记忆，不要性格
soul-init --external       # 性格归你自己的 agent，我们只管记忆
```

| 模式 | 注入什么 | 适合谁 |
|---|---|---|
| `full` | SOUL + MEMORY + index + NOW | 想从零长出一个性格 |
| `memory-only` | MEMORY + index + NOW | 只想让它记得住，不想动它的人设 |
| `external` | index + NOW | 你的 agent 已经有自己的 prompt/人设了 |

对应地，`soul-boot` 也能选：

```bash
soul-boot --mode memory-only
soul-boot --with index.md,NOW.md      # 更细：自己挑文件
```

**空模板永远不会被注入。** 没填的 SOUL 里全是「（待填）」，塞进上下文比不塞更糟——
模型会一本正经地介绍"我的名字是（待填）"。所以只要某页的占位符超过 3 处，就自动跳过。
`--keep-empty` 可以强制保留（调试用）。

铸魂清单也有 `status: skip`：用户明确说了不要性格，就别每次开局问他"你叫什么名字"。

---

## 铸魂

装完的第一件事不是干活，是**先把"我是谁"聊清楚**。

打开 `memory/BOOTSTRAP.md`，一项项来：名字、性格、价值观、边界、主人是谁、想要什么样的陪伴。
**一次推进一项**——一口气问完那是问卷，不是聊天。

写回文件之后才勾选。全部完成 → `status: complete` + `soul-sync`。

想重来：把 `status` 改回 `pending`，**已有记忆不会被清掉**——重铸的是性格，不是记忆。

---

## 接进别的 agent

这套东西不会自己长在模型身上，你得在每轮开头把记忆喂进去。

```bash
soul-boot                 # 打印注入块，拼到 system prompt 最前面
soul-boot --budget 12000  # 限字数（超了从末尾截，先保 SOUL）
```

或者当 Python 模块：

```python
from soul import boot, recall, remember

system_prompt += boot()
context = recall("他说过在意什么", n=3)
remember("今天他说想换个方向", kind="chat")
```

`boot()` **只读，不改任何文件**。要写记忆必须显式 `remember()`。

---

## 双端怎么接

原理只有一条：**谁写了都往 `live.jsonl` 追加一行，带 `source` 标明来源。**
同步就是互相把对方没有的 `id` 抄过来，重复的跳过。

```bash
soul-peer pull "ssh host cat ~/.soul-forging/brain/live.jsonl"
soul-peer push "ssh host 'cat >> ~/.soul-forging/brain/live.jsonl'"
```

不需要中心服务器。两端只要能看到同一份文件（或跑同一句命令）就能通。

---

## 设计取舍

**为什么是 markdown。** 能读、能改、能 diff、能提交 git、能一键搬走。不会被锁死在某个数据库或某家服务里。你随时可以把整个记忆库拷到别处，或者直接打开看。

**为什么分三层。** 注入层越短越好——它每轮都在花钱，而且太长会压得模型说不好话。检索层解决"记多了塞不下"。外置层让调试记录不污染性格。

**为什么记强度。** 不是所有记忆一样重。人真的会忘，而且忘了不是背叛。所以脚本按时间衰减，把几乎想不起来的标成"遗忘"——但**原文不删**，随时能找回。

**为什么不要服务器。** 一个人用不需要。要云备份就设 `SOUL_BACKUP_CMD`，没有也完整。

---

## 云备份（可选）

```bash
export SOUL_BACKUP_CMD='tar czf ~/soul-backup.tgz -C /path/to/repo memory'
```

设了这条，`soul-sync` 每次顺带跑一遍。没设就不跑。

---

## 诚实的局限

- **没验证过"空壳能不能填出性格"**。代码能跑是确定的；一个人对着清单填，填出来是长出个有性格的人、还是填出一份简历——这个只有真人试过才知道。你要是试了，欢迎回来说。
- **检索是字面匹配，不懂意思**。"老板今天骂我"和"上班受气"不一定互相搜得到。要语义得上向量，那是另一件事。
- **只支持单用户**。同一份记忆库给多人共用会串味，别那么干。
- **注入块别贪大**。默认 3.3K 字左右；SOUL 要是写到一万字，每轮都在烧钱。压。

---

## 授权

代码 MIT。记忆内容（`memory/`）是你自己的。

思路参考过 [dsh-plugin-memory](https://github.com/LittleBlackTong/dsh-plugin-memory)（MIT）——
这一版是**重写实现**，没有复制它的代码。如果你把它当插件装进 DSH，那份要单独保留它自己的 LICENSE。
