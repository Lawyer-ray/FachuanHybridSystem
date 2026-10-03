/**
 * doc-parse-outcome 纯逻辑单测（node 环境）。
 *
 * outcomeText 是纯函数直接断言；copyOutcome 覆盖「空内容早退 / 复制成功 / 剪贴板拒绝」
 * 三分支（navigator.clipboard 用 stub，sonner 用 mock）。
 * downloadOutcome 依赖 document/URL.createObjectURL，属 DOM 行为，不在 node 环境测。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: { info: vi.fn(), success: vi.fn(), error: vi.fn() },
}))

import { toast } from 'sonner'

import type { ParseOutcome } from '../../api'

import { copyOutcome, outcomeText } from './doc-parse-outcome'

type OutcomeFields = Pick<ParseOutcome, 'markdown' | 'text'>

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('outcomeText（markdown 优先级）', () => {
  it('markdown 优先于 text，isMd=true', () => {
    expect(outcomeText({ markdown: '# 标题', text: '纯文本' })).toEqual({ text: '# 标题', isMd: true })
  })

  it('markdown 为空串时回退 text，isMd=false', () => {
    expect(outcomeText({ markdown: '', text: '纯文本' })).toEqual({ text: '纯文本', isMd: false })
  })

  it('markdown 为 null（类型外防御值）时回退 text', () => {
    // 类型上 markdown: string，这里显式 cast 验证运行时对 falsy 的容错
    const o = { markdown: null, text: '纯文本' } as unknown as OutcomeFields
    expect(outcomeText(o)).toEqual({ text: '纯文本', isMd: false })
  })

  it('两者都为空 → 空文本', () => {
    expect(outcomeText({ markdown: '', text: '' })).toEqual({ text: '', isMd: false })
  })

  it('null → 空文本（不抛错）', () => {
    expect(outcomeText(null)).toEqual({ text: '', isMd: false })
  })

  it('字段缺失（类型外防御值）→ 空文本', () => {
    const o = {} as unknown as OutcomeFields
    expect(outcomeText(o)).toEqual({ text: '', isMd: false })
  })
})

describe('copyOutcome（剪贴板三分支）', () => {
  it('空内容：早退提示且不触碰剪贴板', async () => {
    const writeText = vi.fn()
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    await copyOutcome(null)

    expect(writeText).not.toHaveBeenCalled()
    expect(toast.info).toHaveBeenCalledWith('没有可复制的解析内容')
    expect(toast.success).not.toHaveBeenCalled()
  })

  it('有内容且剪贴板可用：writeText 收到解析文本并提示成功', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    await copyOutcome({ markdown: '', text: '解析结果正文' })

    expect(writeText).toHaveBeenCalledWith('解析结果正文')
    expect(toast.success).toHaveBeenCalledWith('已复制解析结果')
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('剪贴板拒绝：提示手动复制', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    await copyOutcome({ markdown: '# md 内容', text: '' })

    expect(writeText).toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith('浏览器拒绝了剪贴板，可在预览区手动选中复制')
  })
})
