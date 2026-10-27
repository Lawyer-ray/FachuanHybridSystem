// @vitest-environment jsdom
/**
 * useSpeechInput 测试（jsdom + 假识别器）。
 *
 * 核心不变量（文本合并模型，见 hook 头注释）：
 * - final 只计一次（processed 指针推进），重复上报不叠字
 * - interim 每次全量重建，refined 版本覆盖旧的
 * - onend 采纳未转正尾巴，不丢最后半句
 * - rebase 后旧结果作废，新听写追加在编辑后的文本后
 * - 静默停止（发送场景）不做最后一次 emit
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSpeechInput } from './use-speech-input'

type FakeEvent = { resultIndex: number; results: Array<Array<{ transcript: string }> & { isFinal: boolean }> }

class FakeRecognition {
  lang = ''
  continuous = false
  interimResults = false
  onresult: ((e: FakeEvent) => void) | null = null
  onend: (() => void) | null = null
  onerror: ((e: { error: string }) => void) | null = null
  start = vi.fn()
  stop = vi.fn()
  abort = vi.fn()
  static instances: FakeRecognition[] = []
  constructor() {
    FakeRecognition.instances.push(this)
  }
}

function makeResults(...items: Array<{ transcript: string; isFinal: boolean }>) {
  return items.map((it) => {
    const r = [{ transcript: it.transcript }] as Array<{ transcript: string }> & { isFinal: boolean }
    r.isFinal = it.isFinal
    return r
  })
}

function fireResult(rec: FakeRecognition, items: Array<{ transcript: string; isFinal: boolean }>) {
  act(() => {
    rec.onresult?.({ resultIndex: 0, results: makeResults(...items) })
  })
}

function fireEnd(rec: FakeRecognition) {
  act(() => {
    rec.onend?.()
  })
}

/** 取最近实例化出的假识别器（noUncheckedIndexedAccess 下收敛掉 undefined） */
function lastInstance(): FakeRecognition {
  const inst = FakeRecognition.instances.at(-1)
  if (!inst) throw new Error('FakeRecognition 未实例化：先 start() 再取')
  return inst
}

beforeEach(() => {
  FakeRecognition.instances = []
  const w = window as unknown as { SpeechRecognition?: unknown }
  w.SpeechRecognition = FakeRecognition
})

afterEach(() => {
  delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition
})

describe('useSpeechInput：能力与启动', () => {
  it('无 SpeechRecognition 时 supported=false（按钮不渲染）', () => {
    delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition
    const { result } = renderHook(() => useSpeechInput({ onText: vi.fn() }))
    expect(result.current.supported).toBe(false)
  })

  it('开始听写：zh-CN + 连续 + interim，listening=true', () => {
    const { result } = renderHook(() => useSpeechInput({ onText: vi.fn() }))
    act(() => result.current.start(''))
    const rec = lastInstance()
    expect(rec).toBeDefined()
    expect(rec.lang).toBe('zh-CN')
    expect(rec.continuous).toBe(true)
    expect(rec.interimResults).toBe(true)
    expect(result.current.listening).toBe(true)
  })
})

describe('useSpeechInput：文本合并模型', () => {
  it('interim 实时进草稿，final 后无重复', () => {
    const onText = vi.fn()
    const { result } = renderHook(() => useSpeechInput({ onText }))
    act(() => result.current.start('问题：'))
    const rec = lastInstance()
    fireResult(rec, [{ transcript: '合同金额', isFinal: false }])
    expect(onText).toHaveBeenLastCalledWith('问题：合同金额')
    // refined：同一句越说越准，旧 interim 被覆盖而非叠加
    fireResult(rec, [{ transcript: '合同金额是多少', isFinal: false }])
    expect(onText).toHaveBeenLastCalledWith('问题：合同金额是多少')
    fireResult(rec, [{ transcript: '合同金额是多少？', isFinal: true }])
    expect(onText).toHaveBeenLastCalledWith('问题：合同金额是多少？')
  })

  it('重复上报已 final 的结果不叠字（processed 指针）', () => {
    const onText = vi.fn()
    const { result } = renderHook(() => useSpeechInput({ onText }))
    act(() => result.current.start(''))
    const rec = lastInstance()
    fireResult(rec, [{ transcript: '第一句。', isFinal: true }])
    // 第二个事件把 results[0] 原样再报一遍 + 新增 results[1]
    fireResult(rec, [
      { transcript: '第一句。', isFinal: true },
      { transcript: '第二句。', isFinal: true },
    ])
    expect(onText).toHaveBeenLastCalledWith('第一句。第二句。')
  })

  it('onend 采纳未转正的尾巴，不丢最后半句', () => {
    const onText = vi.fn()
    const { result } = renderHook(() => useSpeechInput({ onText }))
    act(() => result.current.start(''))
    const rec = lastInstance()
    fireResult(rec, [{ transcript: '最后半句', isFinal: false }])
    fireEnd(rec)
    expect(onText).toHaveBeenLastCalledWith('最后半句')
    expect(result.current.listening).toBe(false)
  })

  it('rebase：听写中手动改字后，新听写追加在编辑后的文本后', () => {
    const onText = vi.fn()
    const { result } = renderHook(() => useSpeechInput({ onText }))
    act(() => result.current.start(''))
    const rec = lastInstance()
    fireResult(rec, [{ transcript: '甲乙方', isFinal: true }])
    // 用户手动把「甲乙方」改成「甲方乙方」→ 全文「甲方乙方」
    act(() => result.current.rebase('甲方乙方'))
    fireResult(rec, [
      { transcript: '甲乙方', isFinal: true },
      { transcript: '是谁', isFinal: true },
    ])
    expect(onText).toHaveBeenLastCalledWith('甲方乙方是谁')
  })

  it('静默停止（发送场景）不做最后一次 emit', () => {
    const onText = vi.fn()
    const { result } = renderHook(() => useSpeechInput({ onText }))
    act(() => result.current.start(''))
    const rec = lastInstance()
    fireResult(rec, [{ transcript: '草稿里已有的字', isFinal: false }])
    const calls = onText.mock.calls.length
    act(() => result.current.stop(true))
    expect(rec.stop).toHaveBeenCalled()
    fireEnd(rec)
    expect(onText.mock.calls.length).toBe(calls)
    expect(result.current.listening).toBe(false)
  })
})

describe('useSpeechInput：错误面', () => {
  it('权限拒绝映射为可读原因', () => {
    const { result } = renderHook(() => useSpeechInput({ onText: vi.fn() }))
    act(() => result.current.start(''))
    const rec = lastInstance()
    act(() => rec.onerror?.({ error: 'not-allowed' }))
    expect(result.current.error).toContain('麦克风权限')
  })

  it('no-speech 属正常静默，不报错', () => {
    const { result } = renderHook(() => useSpeechInput({ onText: vi.fn() }))
    act(() => result.current.start(''))
    const rec = lastInstance()
    act(() => rec.onerror?.({ error: 'no-speech' }))
    expect(result.current.error).toBeNull()
  })
})
