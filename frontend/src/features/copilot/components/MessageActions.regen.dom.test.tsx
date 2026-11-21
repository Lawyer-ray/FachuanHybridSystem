// @vitest-environment jsdom
/**
 * 消息操作条上的「重生成 / 继续写」（jsdom）。
 *
 * 这两个按钮会**真花钱重跑一次模型**，所以口径必须是「能跑才出现」：
 * - 没落库的实时气泡不给（点了必然 404，律师只会以为按钮坏了）；
 * - 没被截断过的回答不给「继续写」（没有可接的前缀）；
 * - 动作本身只回调 `onRegenerate(mode)`，页面/气泡不在这里发请求（判据与副作用分离，
 *   这样 canRegenerate / canContinue 可以单独测，不用起 store）。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { MessageActions } from './MessageActions'

const base = { content: '回答正文', messageId: 42, createdAt: 1_700_000_000_000 }

describe('MessageActions：重生成 / 继续写', () => {
  it('两个开关都关时不出现任何重放按钮', () => {
    render(<MessageActions {...base} onRegenerate={() => {}} />)

    expect(screen.queryByLabelText('重新生成')).toBeNull()
    expect(screen.queryByLabelText('继续写')).toBeNull()
  })

  it('regenerable → 出现「重生成」，点击回调 regenerate', () => {
    const onRegenerate = vi.fn()
    render(<MessageActions {...base} regenerable onRegenerate={onRegenerate} />)

    screen.getByLabelText('重新生成').click()

    expect(onRegenerate).toHaveBeenCalledWith('regenerate')
  })

  it('continuable → 出现「继续写」，点击回调 continue', () => {
    const onRegenerate = vi.fn()
    render(<MessageActions {...base} continuable onRegenerate={onRegenerate} />)

    screen.getByLabelText('继续写').click()

    expect(onRegenerate).toHaveBeenCalledWith('continue')
  })

  it('没给 onRegenerate 时即使开关为真也不渲染（避免画出点了没反应的按钮）', () => {
    render(<MessageActions {...base} regenerable continuable />)

    expect(screen.queryByLabelText('重新生成')).toBeNull()
    expect(screen.queryByLabelText('继续写')).toBeNull()
  })

  it('复制与评分不受影响（同一条 action row 里共存）', () => {
    render(<MessageActions {...base} regenerable onRegenerate={() => {}} />)

    expect(screen.getByLabelText('有帮助')).toBeTruthy()
    expect(screen.getByLabelText('没帮助')).toBeTruthy()
  })
})
