// @vitest-environment jsdom
/**
 * 「就地落修订」的桥协议单测（jsdom + fake timers）。
 *
 * 这条链的失败**用户可见且代价明确**：插件没握手 / 原文找不到 / 内核超时，
 * 就降级成换 document key 重建画布 → 律师看到整页刷一下（5–15 秒白屏）。
 * 每条断言都在守两件事：
 *
 * 1. **该失败时立刻失败**：画布没就绪、桥没握手时立刻 resolve(false)，不白等
 *    10 秒——那 10 秒里用户面对的是「AI 说改好了，文档没动」。
 * 2. **该等时等够**：超时上限 10s 必须 >= plugin.js 自己的 8s 命令超时 + 1s
 *    余量（见被测文件头注释）。前端若先超时，会把插件马上要回的结论当成
 *    「桥失联」，明明能就地落笔却重载了整页。
 *
 * 装配方式：不 mock use-rewrite-refresh（那条事件链已有自己的 dom 测试），
 * 只把 `registerLiveRewriteApply` 换成**记录器**，于是可以直接拿到本 hook
 * 注册的就地通道并 `await` 它——比「派 file-rewritten 事件 + 等 toast 文案」
 * 更直接，也不用担心模块级串行队列在用例间残留。
 *
 * `supported === false` 那条尤其重要：插件在说「当前文档类型我处理不了」，
 * 此时仍标记就绪的话，每次 AI 直改都要白等 8 秒再超时。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** 本 hook 注册的就地通道：key → applier */
const registry = vi.hoisted(() => new Map<string, (original: string, replacement: string) => Promise<boolean>>())

vi.mock('./use-rewrite-refresh', () => ({
  registerLiveRewriteApply: (key: string, applier: (o: string, r: string) => Promise<boolean>) => {
    registry.set(key, applier)
    // 与真实实现同语义：注销时只删自己那一条
    return () => {
      if (registry.get(key) === applier) registry.delete(key)
    }
  },
  // nonce 不在本文件职责内（use-rewrite-refresh.dom.test.ts 已覆盖）
  useFileRewriteNonce: () => 0,
}))

import { useLiveRewriteApply } from './use-live-rewrite-apply'

/** 每个用例用独立 key 隔离注册表 */
let seq = 0
function newKey() {
  seq += 1
  return `contract:393:live-${seq}/a.docx`
}

function editorHandle() {
  return { requestSave: vi.fn(() => true), sendToPlugin: vi.fn() }
}

/** 手派插件桥消息：真实来源是 DS iframe 里 plugin.js 的 postMessage */
function emitBridge(data: Record<string, unknown> | null) {
  act(() => {
    window.dispatchEvent(new MessageEvent('message', { data }))
  })
}

/** 挂载 hook、交出编辑器句柄，返回可复用的上下文 */
function mount(enabled = true) {
  const key = newKey()
  const hook = renderHook(() => useLiveRewriteApply({ enabled, key }))
  const handle = editorHandle()
  act(() => hook.result.current.onEditorReady(handle))
  const applier = () => registry.get(key)
  return { key, hook, handle, applier }
}

beforeEach(() => {
  vi.useFakeTimers()
  registry.clear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useLiveRewriteApply：握手与就绪', () => {
  it('编辑器未就绪时立刻 resolve(false)，不发命令也不等超时', async () => {
    const key = newKey()
    const hook = renderHook(() => useLiveRewriteApply({ enabled: true, key }))
    const live = registry.get(key)
    expect(live).toBeDefined()

    // 从未调用 onEditorReady：画布还没挂上，插件桥也无处可发
    await expect(live!('原文', '改后')).resolves.toBe(false)
    hook.unmount()
  })

  it('桥未握手（没有 ready/hello）时立刻 resolve(false)', async () => {
    const { applier, handle, hook } = mount()
    // 句柄有了，但插件没发过握手消息 → 发命令只会石沉大海
    await expect(applier()!('原文', '改后')).resolves.toBe(false)
    expect(handle.sendToPlugin).not.toHaveBeenCalled()
    hook.unmount()
  })

  it('ready{supported:true} 后发 apply-revision，带上 orig/sug', async () => {
    const { applier, handle, hook } = mount()
    emitBridge({ source: 'fachuan-plugin', type: 'ready', supported: true })

    void applier()!('甲方愿意', '甲方同意')

    // 第三参是载荷：plugin.js 靠 orig 定位原文、sug 生成修订痕迹
    expect(handle.sendToPlugin).toHaveBeenCalledWith('apply-revision', undefined, {
      orig: '甲方愿意',
      sug: '甲方同意',
    })
    hook.unmount()
  })

  it('hello 与 ready 等价，都能让命令发出去', async () => {
    const { applier, handle, hook } = mount()
    emitBridge({ source: 'fachuan-plugin', type: 'hello' })

    void applier()!('a', 'b')
    expect(handle.sendToPlugin).toHaveBeenCalledTimes(1)
    hook.unmount()
  })

  it('ready{supported:false} 不置就绪：插件在说「这个文档类型我处理不了」', async () => {
    const { applier, handle, hook } = mount()
    emitBridge({ source: 'fachuan-plugin', type: 'ready', supported: false })

    // 置了就绪的话每次直改都会白等 8s 才超时
    await expect(applier()!('a', 'b')).resolves.toBe(false)
    expect(handle.sendToPlugin).not.toHaveBeenCalled()
    hook.unmount()
  })

  it('非 fachuan-plugin 来源的消息一律丢弃（别的 iframe 不得把桥置成就绪）', async () => {
    const { applier, handle, hook } = mount()
    emitBridge({ source: 'evil-extension', type: 'ready', supported: true })

    await expect(applier()!('a', 'b')).resolves.toBe(false)
    expect(handle.sendToPlugin).not.toHaveBeenCalled()
    hook.unmount()
  })

  it('data 为 null 时忽略而不抛（postMessage 可能是任意内容）', async () => {
    const { applier, handle, hook } = mount()
    emitBridge(null)
    await expect(applier()!('a', 'b')).resolves.toBe(false)
    expect(handle.sendToPlugin).not.toHaveBeenCalled()
    hook.unmount()
  })
})

describe('useLiveRewriteApply：回执与超时', () => {
  it('applied{result.ok:true} → resolve(true)（就地成功，不必重载）', async () => {
    const { applier, handle, hook } = mount()
    emitBridge({ source: 'fachuan-plugin', type: 'ready', supported: true })

    const pending = applier()!('a', 'b')
    emitBridge({ source: 'fachuan-plugin', type: 'applied', result: { ok: true } })
    await expect(pending).resolves.toBe(true)
    expect(handle.sendToPlugin).toHaveBeenCalledTimes(1)
    hook.unmount()
  })

  it('applied{result.ok:false} → resolve(false)（原文已被前一次改动破坏，调用方重载）', async () => {
    const { applier, hook } = mount()
    emitBridge({ source: 'fachuan-plugin', type: 'ready', supported: true })

    const pending = applier()!('a', 'b')
    emitBridge({ source: 'fachuan-plugin', type: 'applied', result: { ok: false } })
    await expect(pending).resolves.toBe(false)
    hook.unmount()
  })

  it('applied 缺 result 也按失败处理（回执不完整时取最坏情况）', async () => {
    const { applier, hook } = mount()
    emitBridge({ source: 'fachuan-plugin', type: 'ready', supported: true })

    const pending = applier()!('a', 'b')
    emitBridge({ source: 'fachuan-plugin', type: 'applied' })
    await expect(pending).resolves.toBe(false)
    hook.unmount()
  })

  it('9999ms 无回执时仍等待（插件自己的 8s 结论可能刚到），10000ms 才超时', async () => {
    const { applier, hook } = mount()
    emitBridge({ source: 'fachuan-plugin', type: 'ready', supported: true })

    let settled: boolean | null = null
    void applier()!('a', 'b').then((ok) => {
      settled = ok
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_999)
    })
    // 上限必须留足插件 8s 命令超时 + 余量，否则会抢在插件结论之前重载整页
    expect(settled).toBeNull()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(settled).toBe(false)
    hook.unmount()
  })

  it('回执到手后清掉定时器，迟到的 applied 不再二次 resolve', async () => {
    const { applier, hook } = mount()
    emitBridge({ source: 'fachuan-plugin', type: 'ready', supported: true })

    const pending = applier()!('a', 'b')
    emitBridge({ source: 'fachuan-plugin', type: 'applied', result: { ok: true } })
    await expect(pending).resolves.toBe(true)

    // 槽位已清：再来的 applied 不该把第二个 pending 误判成功
    emitBridge({ source: 'fachuan-plugin', type: 'applied', result: { ok: false } })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })
    hook.unmount()
  })

  it('画布重建（onEditorReady(null)）后 ready 态作废，必须重新握手', async () => {
    const { applier, hook } = mount()
    emitBridge({ source: 'fachuan-plugin', type: 'ready', supported: true })

    // 换 key 重载 / 换文件：旧 iframe 已销毁，桥状态必须跟着作废
    act(() => hook.result.current.onEditorReady(null))
    const handle2 = editorHandle()
    act(() => hook.result.current.onEditorReady(handle2))

    await expect(applier()!('a', 'b')).resolves.toBe(false)
    expect(handle2.sendToPlugin).not.toHaveBeenCalled()
    hook.unmount()
  })

  it('enabled=false 时不注册就地通道（非 docx 文件不该走插件）', () => {
    const key = newKey()
    const hook = renderHook(() => useLiveRewriteApply({ enabled: false, key }))
    expect(registry.has(key)).toBe(false)
    hook.unmount()
  })

  it('卸载后注销通道，避免已卸载的画布继续收命令', () => {
    const { applier, hook } = mount()
    expect(applier()).toBeDefined()
    hook.unmount()
    expect(registry.size).toBe(0)
  })
})
