// @vitest-environment jsdom
/**
 * 输入框上方的「框选引用区」测试（jsdom）。
 *
 * 这块 UI 的全部风险在「点一下会发生什么」：
 * - 快捷指令 pills **只填不发送**：误触不该烧掉一轮模型调用，所以 pill 必须
 *   把指令文本交回 Composer（`onPickPrompt`），而不是自己 submit；
 * - 移除钮必须真的把引用摘掉，否则律师以为删了、发出去却还带着选段。
 *
 * 展示部分（卡片、图标）靠稳定的可及名断言，不锁 className——
 * 那属于设计迭代范围，锁住只会让人不敢改样式。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ComposerQuote } from './ComposerQuote'
import type { SelectionQuote } from '../types'

const quote: SelectionQuote = {
  kind: 'contract',
  ownerId: 88,
  subpath: '个人购房借款合同.docx',
  name: '个人购房借款合同.docx',
  text: '甲方应于合同签订之日起三十日内支付全部价款。',
}

describe('ComposerQuote：框选引用区', () => {
  it('展示被引用的原文', () => {
    const { container } = render(<ComposerQuote quote={quote} onRemove={vi.fn()} onPickPrompt={vi.fn()} />)
    expect(container.textContent).toContain('甲方应于合同签订之日起三十日内支付全部价款。')
    container.remove()
  })

  it('快捷指令 pills 把指令文本交给 Composer（只填不发送）', () => {
    const onPickPrompt = vi.fn()
    const { container } = render(<ComposerQuote quote={quote} onRemove={vi.fn()} onPickPrompt={onPickPrompt} />)

    fireEvent.click(screen.getByRole('button', { name: '风险提示 →' }))

    expect(onPickPrompt).toHaveBeenCalledWith('这段条款对我方有什么风险？')
    container.remove()
  })

  it('改写类指令结尾留白（光标落在末尾，律师接着打要求）', () => {
    const onPickPrompt = vi.fn()
    const { container } = render(<ComposerQuote quote={quote} onRemove={vi.fn()} onPickPrompt={onPickPrompt} />)

    fireEvent.click(screen.getByRole('button', { name: '帮我改写 →' }))

    expect(onPickPrompt).toHaveBeenCalledWith('请按我的要求改写这段引用的条款（保持法律文书语体，只改这段）：')
    container.remove()
  })

  it('移除钮把「摘掉引用」交回 Composer', () => {
    const onRemove = vi.fn()
    const { container } = render(<ComposerQuote quote={quote} onRemove={onRemove} onPickPrompt={vi.fn()} />)

    // 引用条的移除钮带显式可及名，不靠图标位置点
    fireEvent.click(screen.getByRole('button', { name: '移除引用选段' }))

    expect(onRemove).toHaveBeenCalled()
    container.remove()
  })
})
