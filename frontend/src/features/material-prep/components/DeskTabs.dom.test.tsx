// @vitest-environment jsdom
/**
 * DeskTabs：两级导航。
 *
 * 锁定的是本次结构调整的核心语义：
 *   一级 = 【收件箱 | 材料包】——「流入」与「加工」两支，不再把「收件箱」
 *   和三种材料包状态平铺成四个互不同类的页签。
 *   二级 = 材料包之下的三种状态，且**只在材料包区段出现**。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DeskTabs } from './DeskTabs'
import type { PrepStage } from '../stages'

const counts: Record<PrepStage, number> = { inbox: 42, todo: 3, done: 8, filed: 1 }

function renderTabs(stage: PrepStage, setStage = vi.fn()) {
  render(
    <DeskTabs
      stage={stage}
      setStage={setStage}
      counts={counts}
      uploading={false}
      onPickFiles={vi.fn()}
      onOpenShareLinks={vi.fn()}
    />,
  )
  return { setStage }
}

describe('DeskTabs：一级导航', () => {
  it('只有两项：收件箱 / 材料包', () => {
    renderTabs('inbox')
    expect(screen.getByTestId('prep-section-inbox')).toBeTruthy()
    expect(screen.getByTestId('prep-section-pack')).toBeTruthy()
    // 三个状态名不能在一级出现（它们属于材料包之下）
    expect(screen.queryByTestId('prep-section-todo')).toBeNull()
  })

  it('材料包角标是三种状态之和（"这一支里共多少包"）', () => {
    renderTabs('inbox')
    // 3 + 8 + 1 = 12
    expect(screen.getByTestId('prep-section-pack').textContent).toContain('12')
  })

  it('收件箱角标取收件箱数，不含材料包', () => {
    renderTabs('inbox')
    expect(screen.getByTestId('prep-section-inbox').textContent).toContain('42')
  })

  it('点「材料包」：从收件箱进入时落到默认的「待处理」', () => {
    const { setStage } = renderTabs('inbox')
    fireEvent.click(screen.getByTestId('prep-section-pack'))
    expect(setStage).toHaveBeenCalledWith('todo')
  })

  it('点「材料包」：已在材料包某状态时**保持**该状态', () => {
    // 用户上次停在「已归案」，切去收件箱再切回来应该还回「已归案」，
    // 而不是被强行拉去「待处理」
    const { setStage } = renderTabs('done')
    fireEvent.click(screen.getByTestId('prep-section-pack'))
    expect(setStage).toHaveBeenCalledWith('done')
  })

  it('点「收件箱」回到收件箱区段', () => {
    const { setStage } = renderTabs('done')
    fireEvent.click(screen.getByTestId('prep-section-inbox'))
    expect(setStage).toHaveBeenCalledWith('inbox')
  })
})

describe('DeskTabs：材料包二级状态', () => {
  it('收件箱区段不显示二级状态页签', () => {
    renderTabs('inbox')
    expect(screen.queryByTestId('prep-pack-stages')).toBeNull()
    expect(screen.queryByTestId('prep-stage-todo')).toBeNull()
  })

  it('材料包区段显示三个状态页签，各自带计数', () => {
    // 三个角标要一直可见——这正是这里用同级页签而不是下拉的原因：
    // 下拉会把「今天还有几包没处理」这个信息藏起来。
    renderTabs('todo')
    expect(screen.getByTestId('prep-pack-stages')).toBeTruthy()
    expect(screen.getByTestId('prep-stage-todo').textContent).toContain('3')
    expect(screen.getByTestId('prep-stage-done').textContent).toContain('8')
    expect(screen.getByTestId('prep-stage-filed').textContent).toContain('1')
  })

  it('点二级状态切换到该状态', () => {
    const { setStage } = renderTabs('todo')
    fireEvent.click(screen.getByTestId('prep-stage-done'))
    expect(setStage).toHaveBeenCalledWith('done')
  })

  it('当前状态用 aria-current 标记（可访问性，不只靠颜色）', () => {
    renderTabs('done')
    expect(screen.getByTestId('prep-stage-done').getAttribute('aria-current')).toBe('page')
    expect(screen.getByTestId('prep-stage-todo').getAttribute('aria-current')).toBeNull()
  })
})
