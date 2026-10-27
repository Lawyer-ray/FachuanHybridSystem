// @vitest-environment jsdom
/**
 * AI 直改的「就地落笔 vs 换 key 重载」决策（use-rewrite-refresh 的核心契约）。
 *
 * **为什么必须锁死**：就地落笔失败的唯一出口是换 document key 重建画布，
 * 用户体感是「AI 改完之后整页刷一下」（5–15 秒白屏）。曾经的真实故障链是：
 * 插件侧定位失败率很高 → 每次 AI 改完都重建画布。所以这里的每条断言
 * 都在守「什么时候**不该**重载」。
 *
 * 被测的三个入口：
 * - registerLiveRewriteApply：挂载中的画布登记就地通道
 * - useFileRewriteNonce：nonce 只增不减，作为 OfficeView 的 version 触发换 key
 * - handleRewrite（内部，经事件驱动）：有就地通道且成功 → **不动 nonce**
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { toast } from 'sonner'

import { registerLiveRewriteApply, useFileRewriteNonce } from './use-rewrite-refresh'

/**
 * nonce 是**模块级 Map**（跨组件卸载存活，这是它的设计目的），所以用例之间
 * 会共享计数。每个用例用独立 subpath 隔离，断言只看「本用例的增量」。
 */
let seq = 0
function newFile() {
  seq += 1
  const subpath = `case-${seq}/a.docx`
  return { subpath, key: `contract:393:${subpath}` }
}

function rewriteOf(subpath: string) {
  return {
    contractId: 393,
    subpath,
    name: 'a.docx',
    original: '经协商，甲方愿意聘用乙方',
    replacement: '经双方友好协商，甲方愿意聘用乙方',
  }
}

/** 读当前 nonce（与 OfficeView 传 version 同源） */
function nonceOf(subpath: string): number {
  return renderHook(() => useFileRewriteNonce('contract', 393, subpath)).result.current
}

/** 事件链是 Promise 串联的，等它跑完 */
async function flush() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0))
  })
}

function emitRewrite(detail: Record<string, unknown>) {
  act(() => {
    window.dispatchEvent(new CustomEvent('fachuan:file-rewritten', { detail }))
  })
}

/** 取最近一次 toast 的 description（用来区分「就地」与「重载」文案） */
function lastToastDesc(): string {
  const calls = (toast.success as unknown as { mock: { calls: unknown[][] } }).mock.calls
  const last = calls[calls.length - 1]
  const opts = last?.[1] as { description?: string } | undefined
  return String(opts?.description ?? '')
}

describe('AI 直改刷新决策', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('就地落笔成功时**不**推进 nonce（画布不重建）', async () => {
    const f = newFile()
    const before = nonceOf(f.subpath)
    const live = vi.fn().mockResolvedValue(true)
    const off = registerLiveRewriteApply(f.key, live)

    emitRewrite(rewriteOf(f.subpath))
    await flush()

    // 走了就地通道，且用的是事件里带的原文/改写全文
    expect(live).toHaveBeenCalledWith(rewriteOf(f.subpath).original, rewriteOf(f.subpath).replacement)
    // 文案必须是「已在文档中生成」，不能是「正在刷新」（后者=重载路径）
    expect(lastToastDesc()).toContain('已在打开的文档中生成')

    expect(nonceOf(f.subpath)).toBe(before)
    off()
  })

  it('就地落笔失败时推进 nonce（降级换 key 重载）', async () => {
    const f = newFile()
    const before = nonceOf(f.subpath)
    const off = registerLiveRewriteApply(f.key, vi.fn().mockResolvedValue(false))

    emitRewrite(rewriteOf(f.subpath))
    await flush()

    expect(lastToastDesc()).toContain('正在刷新')
    expect(nonceOf(f.subpath)).toBe(before + 1)
    off()
  })

  it('没有画布登记就地通道时直接走重载', async () => {
    const f = newFile()
    const before = nonceOf(f.subpath)
    emitRewrite(rewriteOf(f.subpath))
    await flush()
    expect(nonceOf(f.subpath)).toBe(before + 1)
  })

  it('事件缺原文/改写全文时不做就地尝试，直接重载', async () => {
    const f = newFile()
    const before = nonceOf(f.subpath)
    const live = vi.fn().mockResolvedValue(true)
    const off = registerLiveRewriteApply(f.key, live)

    emitRewrite({ contractId: 393, subpath: f.subpath, name: 'a.docx' })
    await flush()

    expect(live).not.toHaveBeenCalled()
    expect(nonceOf(f.subpath)).toBe(before + 1)
    off()
  })

  it('就地通道抛异常时也降级重载，不把异常抛给调用方', async () => {
    const f = newFile()
    const before = nonceOf(f.subpath)
    const off = registerLiveRewriteApply(f.key, vi.fn().mockRejectedValue(new Error('bridge died')))

    emitRewrite(rewriteOf(f.subpath))
    await flush()

    expect(nonceOf(f.subpath)).toBe(before + 1)
    off()
  })

  it('注销后再来的事件不再走就地（画布已卸载）', async () => {
    const f = newFile()
    const before = nonceOf(f.subpath)
    const live = vi.fn().mockResolvedValue(true)
    const off = registerLiveRewriteApply(f.key, live)
    off()

    emitRewrite(rewriteOf(f.subpath))
    await flush()

    expect(live).not.toHaveBeenCalled()
    expect(nonceOf(f.subpath)).toBe(before + 1)
  })

  it('不同文件的 key 不串味', async () => {
    const f = newFile()
    const before = nonceOf(f.subpath)
    const otherLive = vi.fn().mockResolvedValue(true)
    const off = registerLiveRewriteApply(`contract:393:other/${f.subpath}`, otherLive)

    emitRewrite(rewriteOf(f.subpath))
    await flush()

    expect(otherLive).not.toHaveBeenCalled()
    expect(nonceOf(f.subpath)).toBe(before + 1)
    off()
  })

  it('非法事件（缺 contractId/subpath）被忽略，不推进 nonce', async () => {
    const f = newFile()
    const before = nonceOf(f.subpath)
    emitRewrite({ name: 'x' })
    await flush()
    expect(nonceOf(f.subpath)).toBe(before)
  })
})
