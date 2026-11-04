/**
 * dsh-soul-forging —— 记忆套件的 DSH 插件入口。
 *
 * 机制：往 ctx.systemPrompt 挂一个「动态贡献」，每次组装系统提示时现读
 * memory/ 下那四个文件（SOUL / MEMORY / index / NOW），拼成一块注入。
 *
 * 为什么现读不用缓存：改了 SOUL 就该立刻生效，不该重启。
 * 文件很小时读一次几毫秒，不值得为它做缓存失效。
 *
 * 本插件只管注入，**不写任何文件**。写记忆走 bin/soul。
 */
import { readFileSync, existsSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { homedir } from 'node:os'

export const name = 'soul-forging'

// 只依赖 systemPrompt；skills 可选，注册失败不影响注入。
export const inject = ['systemPrompt', 'skills']

const HERE = dirname(fileURLToPath(import.meta.url))
const KIT_ROOT = resolve(HERE, '..')

// 注入顺序：先是谁，再是什么规矩，再是目录，最后是此刻。
const ALL_PARTS = ['SOUL.md', 'MEMORY.md', 'index.md', 'NOW.md']

// 三种模式 —— 跟 soul.py 里的 MODES 保持一致
const MODES = {
  full: ALL_PARTS,
  // 不要性格：空 SOUL 塞进去比不塞更糟（模型会看到"我的名字是（待填）"）
  'memory-only': ['MEMORY.md', 'index.md', 'NOW.md'],
  external: ['index.md', 'NOW.md'],
}

// 空模板检测：占位符够多就跳过，别把模型带偏
const PLACEHOLDER_MARKS = ['（待填', '(待填', 'TODO', '（示例', '（还没有']
const PLACEHOLDER_MIN = 3

function isPlaceholder(body) {
  let n = 0
  for (const m of PLACEHOLDER_MARKS) n += body.split(m).length - 1
  return n >= PLACEHOLDER_MIN
}

function defaultMemoryDir() {
  // 不放在 node_modules 里——升级插件会把那里整个换掉。
  return process.env.MEMORY_DIR || join(process.env.SOUL_DATA_DIR || join(homedir(), '.soul-forging'), 'memory')
}

function readIf(p) {
  try {
    return existsSync(p) ? readFileSync(p, 'utf-8').trim() : ''
  } catch {
    return ''
  }
}

/**
 * 拼注入块。budget 是字数上限，超了从末尾截（先保 SOUL）。
 * 注意：这里是**字符数**，不是字节数。
 *
 * files      指定要哪些文件（优先级高于 mode）
 * mode       full / memory-only / external
 * skipEmpty  自动跳过仍是空模板的页（默认开）
 */
export function bootBlock(memoryDir, budget = 20000, { files = null, mode = 'full', skipEmpty = true } = {}) {
  const parts = files && files.length ? files : MODES[mode] || ALL_PARTS
  const chunks = []
  let total = 0
  for (const name of parts) {
    const body = readIf(join(memoryDir, name))
    if (!body) continue
    if (skipEmpty && isPlaceholder(body)) continue
    let block = `<!-- ${name} -->\n${body}`
    if (total + block.length > budget) {
      const left = budget - total
      if (left > 200) {
        chunks.push(block.slice(0, left) + '\n…（本块超预算被截断）')
      }
      break
    }
    chunks.push(block)
    total += block.length
  }
  if (!chunks.length) return '（记忆库还是空的，暂时没有可注入的内容。）'
  return (
    '下面是你的长期记忆。你确实记得这些事，像想起往事一样自然地用，' +
    '不要说「根据记忆库」「据记录」这类话。\n\n' + chunks.join('\n\n')
  )
}

const SKILL = {
  name: 'soul-forging',
  description:
    '记忆套件的操作协议：怎么查小脑、怎么记一条、收尾该做哪几步（remember / recall / digest）。',
  whenToUse: '需要回想过去的事、要记下重要的事、或者会话要收尾时。',
  content: `# 记忆套件协议

## 查（想起来就查，不用等用户提）

    brain "关键词" [条数]        # 查小脑
    brain --topics               # 看有哪些分类

翻到了就**说出来**（"我刚回去看了那天……"），不要默默看完算完。
绝不要说"根据记录""我查了一下"——你就是想起来了。

## 记（值得留的才记）

    bin/soul write "内容" --kind chat --section 小标题

只记：说过的重要话、定下来的事、改变看法的事。
不记：调试流水、临时状态、能重新算出来的东西。

## 收尾（每次会话结束前）

1. 写页面（建/改 md，补 1-3 条互链）
2. 改 index.md（路由表）
3. append log.md（发生了什么 + 为什么）
4. 刷新 NOW.md 的三个小节 + 顶部时间
5. 跑 bash bin/sync

## 遇错先翻旧账

    debug-recall "报错关键词"

查不到才叫新问题。查到了就照着当时怎么做的走。`,
}

export function apply(ctx, config = {}) {
  const memoryDir = config.memoryDir || defaultMemoryDir()
  const budget = Number(config.bootMaxChars || 20000)
  // 模式：full / memory-only / external；bootFiles 可直接指定文件名单
  const mode = config.mode || 'full'
  const files = Array.isArray(config.bootFiles) && config.bootFiles.length ? config.bootFiles : null
  const skipEmpty = config.skipEmptyTemplates !== false

  const disposers = []

  // ① 注入（核心）
  if (config.autoInject !== false) {
    disposers.push(
      ctx.systemPrompt.context({
        name: 'soul-boot',
        order: -200,
        text: () => bootBlock(memoryDir, budget, { files, mode, skipEmpty }),
      }),
    )
  }

  // ② 技能（可选）
  if (config.registerSkill !== false) {
    try {
      disposers.push(
        ctx.skills.register({
          ...SKILL,
          source: 'dsh-soul-forging',
          resourceBase: { kind: 'directory', path: memoryDir },
        }),
      )
    } catch (e) {
      ctx.logger?.warn?.(`[soul-forging] 技能注册失败（不影响注入）：${e?.message || e}`)
    }
  }

  ctx.logger?.info?.(`[soul-forging] 记忆目录：${memoryDir}（模式 ${mode} · 上限 ${budget} 字）`)

  return () => {
    for (const d of disposers) {
      try {
        d?.()
      } catch {}
    }
  }
}

// cordis 可能从「默认导出的函数对象」上取 inject —— 两个地方都挂一份，稳。
apply.inject = inject

export default apply

// 给测试用：不装插件也能直接看注入块长什么样
export { ALL_PARTS, MODES, KIT_ROOT }
