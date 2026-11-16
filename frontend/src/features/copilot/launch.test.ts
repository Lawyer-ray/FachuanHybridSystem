// @vitest-environment jsdom
/**
 * Copilot 跨域启动入口（launch.ts）单测（jsdom：全靠 window 自定义事件）。
 *
 * 这个模块是**其它 feature 拉起 AI 面板的唯一门**，也是懒加载边界的关键：
 * 它刻意不 import store / 组件（否则使用方 chunk 会把整个面板拖进来）。
 * 所以这里测的是「事件是否派发、pending 是否被取走、兜底是否生效」，
 * 以及几条只有真机才看得出来的细节：
 *
 * - `prefillCopilot('')` 只开面板、不写内容——按钮点下去必须有反应，但
 *   不能给律师塞一段空白；
 * - 预填事件延后 120ms 派发：面板是懒加载 chunk，刚挂载时 Composer 还没订阅
 *   事件，立刻派发等于丢字；
 * - 引用（quote）走**结构化状态**而不是文本模板，展示侧先做换行归一与限长：
 *   引用要随消息出站、回放成卡，长度不限会在卡片里撑破布局。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  clearPendingQuote,
  COPILOT_LAUNCH_EVENT,
  COPILOT_PREFILL_EVENT,
  COPILOT_QUOTE_EVENT,
  FILE_REWRITTEN_EVENT,
  openCopilot,
  prefillCopilot,
  quoteCopilot,
  takePendingLaunchContext,
  takePendingQuote,
  type CopilotLaunchContext,
} from './launch'
import type { SelectionQuote } from './types'

const ctx: CopilotLaunchContext = { origin: 'case', refId: 12, title: '某某公司诉李某' }

/** 记录某个自定义事件被派发时的 detail */
function watch(type: string) {
  const seen: unknown[] = []
  const handler = (e: Event) => seen.push((e as CustomEvent).detail)
  window.addEventListener(type, handler)
  return { seen, stop: () => window.removeEventListener(type, handler) }
}

beforeEach(() => {
  vi.useFakeTimers()
  // pending 是模块级变量：清干净，避免用例之间互相污染
  takePendingLaunchContext()
  clearPendingQuote()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('openCopilot', () => {
  it('带上下文时派发会话事件，并把上下文留作 pending（chunk 加载竞态的兜底）', () => {
    const w = watch(COPILOT_LAUNCH_EVENT)
    openCopilot(ctx)
    expect(w.seen).toEqual([ctx])
    expect(takePendingLaunchContext()).toEqual(ctx)
    w.stop()
  })

  it('pending 取后即清：第二次取到 null（否则每次面板挂载都会重放旧上下文）', () => {
    openCopilot(ctx)
    takePendingLaunchContext()
    expect(takePendingLaunchContext()).toBeNull()
  })

  it('不带上下文时 detail 为 null（通用模式下必须清掉上一条业务归属）', () => {
    const w = watch(COPILOT_LAUNCH_EVENT)
    openCopilot()
    expect(w.seen).toEqual([null])
    expect(takePendingLaunchContext()).toBeNull()
    w.stop()
  })
})

describe('prefillCopilot', () => {
  it('文本延后 120ms 才进输入框：面板刚挂载时 Composer 还没订阅事件', () => {
    const w = watch(COPILOT_PREFILL_EVENT)
    prefillCopilot('请分析这段', ctx)

    // 立刻派发会丢：懒加载 chunk 还没挂载完
    expect(w.seen).toEqual([])
    vi.advanceTimersByTime(119)
    expect(w.seen).toEqual([])
    vi.advanceTimersByTime(1)
    expect(w.seen).toEqual([{ text: '请分析这段' }])
    w.stop()
  })

  it('空文本只开面板、不写输入框（按钮点下去要有反应，但不能塞空白）', () => {
    const launch = watch(COPILOT_LAUNCH_EVENT)
    const prefill = watch(COPILOT_PREFILL_EVENT)
    prefillCopilot('   ', ctx)
    vi.advanceTimersByTime(200)

    expect(launch.seen).toEqual([ctx])
    expect(prefill.seen).toEqual([])
    launch.stop()
    prefill.stop()
  })
})

describe('quoteCopilot', () => {
  const quote: SelectionQuote = {
    kind: 'contract',
    ownerId: 393,
    subpath: 'a.docx',
    name: '委托合同.docx',
    text: '第一条\n\n  双方约定……',
  }

  it('展示侧先归一：换行压平、首尾空白 trim', () => {
    quoteCopilot(quote)
    // 卡片里多行文本会把高度撑开，且出站块要求单行
    expect(takePendingQuote()?.text).toBe('第一条 双方约定……')
  })

  it('超长选段截断到 400 字并加省略号（否则四处注入的引用会把 prompt 撑爆）', () => {
    quoteCopilot({ ...quote, text: 'x'.repeat(500) })
    const text = takePendingQuote()?.text ?? ''
    // 400 字正文 + '……'（两个字符）= 402，不是 403
    expect(text.length).toBe(402)
    expect(text.endsWith('……')).toBe(true)
  })

  it('派发引用事件时带的是归一后的内容（事件与 pending 必须同源）', () => {
    const w = watch(COPILOT_QUOTE_EVENT)
    quoteCopilot({ ...quote, text: '内容\n换行' })
    expect(w.seen).toEqual([{ ...quote, text: '内容 换行' }])
    // 事件与 pending 是两份引用，内容必须一致，否则卡片与出站块会对不上
    expect(takePendingQuote()).toEqual({ ...quote, text: '内容 换行' })
    w.stop()
  })

  it('不传上下文时等价于通用模式开面板', () => {
    const w = watch(COPILOT_LAUNCH_EVENT)
    quoteCopilot(quote)
    expect(w.seen).toEqual([null])
    w.stop()
  })

  it('clearPendingQuote 清掉未消费的引用（防重复挂卡）', () => {
    quoteCopilot(quote)
    clearPendingQuote()
    expect(takePendingQuote()).toBeNull()
  })
})

describe('FILE_REWRITTEN_EVENT 常量', () => {
  it('事件名是 fachuan:file-rewritten（workbench 的刷新钩子按字面量订阅）', () => {
    // 改名等于静默断链：AI 落盘后画布不再刷新，而两边都不会报错
    expect(FILE_REWRITTEN_EVENT).toBe('fachuan:file-rewritten')
  })
})
