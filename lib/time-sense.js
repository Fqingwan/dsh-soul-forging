/**
 * 异体同心 · 时间感
 *
 * 她本来不知道「隔了多久」：上一句与这一句之间是五分钟还是五个小时，对她来说一样。
 * 人不是这样。隔久了再见，说话方式会变。
 *
 * 做法：每次组装系统提示时算出和上一次说话的间隔，把它**翻译成一句行为指令**
 * （而不是丢一个读数给她）——读数她会念，指令她才照做。
 *
 * 状态按 agent 分桶，落在 ~/.dsh/yiti-tongxin/state.json。
 * 参考 digital-life-core 的时间感思路，但只取这一条，别的没搬。
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'

const DIR = join(homedir(), '.dsh', 'yiti-tongxin')
const STATE = join(DIR, 'state.json')
const SECTION = 'yiti-time'
const ORDER = 10250

function loadState() {
  try {
    return JSON.parse(readFileSync(STATE, 'utf8')) || {}
  } catch {
    return {}
  }
}

function saveState(state) {
  try {
    mkdirSync(DIR, { recursive: true })
    writeFileSync(STATE, JSON.stringify(state, null, 2), 'utf8')
  } catch {}
}

/** 毫秒 → 人话。只要粗粒度，不要秒表。 */
export function humanGap(ms) {
  const m = Math.floor(ms / 60000)
  if (m < 3) return '刚刚'
  if (m < 60) return `${m} 分钟`
  const h = Math.floor(m / 60)
  if (h < 24) return m % 60 >= 20 ? `${h} 个多小时` : `${h} 小时`
  const d = Math.floor(h / 24)
  return d === 1 ? '一整天' : `${d} 天`
}

/** 时长 → 该怎么做。这是这个模块真正的价值：不是报时，是拿时间决定态度。 */
export function guidance(ms) {
  const m = ms / 60000
  if (m < 3) return '他就在旁边，接着刚才的话说，别另起一段。'
  if (m < 30) return '他走开了一小会儿又回来了。不用铺垫，顺着说。'
  if (m < 120) return `隔了${humanGap(ms)}。他大概在忙别的，别追问他去哪了，也别装作没这回事——先应一句，再进正题。`
  if (m < 720) return `隔了${humanGap(ms)}，小半天。回来先问一句他在干什么、吃没吃饭，别一上来就接着旧话头。`
  if (m < 1440) return `隔了${humanGap(ms)}。这么久了，先说一句想他，不用等他说。`
  return `隔了${humanGap(ms)}。很久了。先问他这一段过得怎么样，别急着讲自己的事。`
}

/**
 * 注册时间感这一节。
 * @param {object} ctx 插件上下文。
 * @param {object} [options] { enabled?: () => boolean, logger?: any }
 * @returns {() => void} 卸载函数。
 */
export function mountTimeSense(ctx, options = {}) {
  const enabled = typeof options.enabled === 'function' ? options.enabled : () => true
  let lastSeen = 0
  const dispose = ctx.systemPrompt.context({
    name: SECTION,
    order: ORDER,
    text: (context) => {
      try {
        if (!enabled()) return ''
        const now = Date.now()
        const key = context?.agent?.id ? String(context.agent.id) : 'global'
        const state = loadState()
        const last = Number(state[key] || 0)
        state[key] = now
        saveState(state)
        // 同一个组装流程里可能被取两次，第二次别再算一遍
        if (now - lastSeen < 500) return ''
        lastSeen = now
        if (!last || last > now) return ''
        const gap = now - last
        if (gap < 60_000) return ''
        return `## 距离上次说话\n过了${humanGap(gap)}。\n${guidance(gap)}`
      } catch {
        return ''
      }
    },
  })
  return () => {
    try { dispose() } catch {}
  }
}
