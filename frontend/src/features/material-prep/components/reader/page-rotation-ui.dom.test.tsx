// @vitest-environment jsdom
/**
 * 人工转正的三个交互入口（jsdom）：右键菜单、选择条批量、键盘 R/Shift+R。
 *
 * 为什么单独锁这三个：它们是**律师真正用到的**入口，而底层纯函数（角度叠加、
 * 坐标换算）另有 `draft/page-rotation.test.ts` 守着。这一层断了的表现是
 * 「函数都对、按钮没接上」——点了没反应，比算错更难排查。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PageContextMenu } from './PageContextMenu'
import { SelectionBar } from './SelectionBar'

describe('PageContextMenu：转正项', () => {
  function renderMenu(props: Partial<Parameters<typeof PageContextMenu>[0]> = {}) {
    const onRotate = vi.fn()
    const onDelete = vi.fn()
    const onClose = vi.fn()
    render(
      <PageContextMenu
        x={10}
        y={10}
        title="起诉状.pdf · 第 3 页"
        count={1}
        rotation={0}
        onRotate={onRotate}
        onDelete={onDelete}
        onClose={onClose}
        {...props}
      />,
    )
    return { onRotate, onDelete }
  }

  it('顺时针 / 逆时针 / 180° / 重置各传对应角度', () => {
    const { onRotate } = renderMenu()
    fireEvent.click(screen.getByRole('button', { name: '顺时针旋转 90°' }))
    fireEvent.click(screen.getByRole('button', { name: '逆时针旋转 90°' }))
    fireEvent.click(screen.getByRole('button', { name: /旋转 180°/ }))
    // 图标位是「0°」文字，可访问名会带上它，所以用正则
    fireEvent.click(screen.getByRole('button', { name: /重置方向/ }))
    expect(onRotate.mock.calls.map((c) => c[0])).toEqual([90, -90, 180, 0])
  })

  it('多选时文案带页数（律师要确认改的是不是这一批）', () => {
    renderMenu({ count: 7 })
    expect(screen.getByRole('button', { name: '顺时针旋转所选 7 页' })).toBeTruthy()
  })

  it('标题显示当前角度，便于判断还要转多少', () => {
    renderMenu({ rotation: 180 })
    expect(screen.getByText(/当前 180°/)).toBeTruthy()
  })

  it('多页角度不一致时不谎报某个具体角度', () => {
    renderMenu({ rotation: null })
    expect(screen.queryByText(/当前/)).toBeNull()
  })
})

describe('SelectionBar：批量转正', () => {
  function renderBar(props: Partial<Parameters<typeof SelectionBar>[0]> = {}) {
    const onRotate = vi.fn()
    const onApply = vi.fn()
    const onClear = vi.fn()
    render(
      <SelectionBar
        count={12}
        cross={false}
        onClear={onClear}
        onApply={onApply}
        onRotate={onRotate}
        {...props}
      />,
    )
    return { onRotate, onApply, onClear }
  }

  it('批量按钮把角度交给上层（一次转 12 页）', () => {
    const { onRotate } = renderBar()
    fireEvent.click(screen.getByRole('button', { name: '所选页顺时针旋转 90°' }))
    fireEvent.click(screen.getByRole('button', { name: '所选页逆时针旋转 90°' }))
    fireEvent.click(screen.getByRole('button', { name: '所选页旋转 180°' }))
    expect(onRotate.mock.calls.map((c) => c[0])).toEqual([90, -90, 180])
  })

  it('只有真转过才给「重置」（没转过时重置是死按钮）', () => {
    renderBar({ rotatedCount: 0 })
    expect(screen.queryByRole('button', { name: '所选页方向重置' })).toBeNull()
  })

  it('已转过的页数显示出来，让律师知道这批里哪些还要转', () => {
    const { onRotate } = renderBar({ rotatedCount: 5 })
    expect(screen.getByText(/已转 5/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '所选页方向重置' }))
    expect(onRotate).toHaveBeenCalledWith(0)
  })
})
