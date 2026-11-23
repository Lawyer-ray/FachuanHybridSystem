// @vitest-environment jsdom
/**
 * 机器人执行录像抽屉（`BotReplayDrawer`）单测（jsdom）。
 *
 * - 打开即播第 1 帧，逐帧推进到最后一帧
 * - 点时间轴能跳帧；未打开时不渲染画面
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DEMO_X3_BROWSER_FRAMES } from '../demo-data'
import { BotReplayDrawer } from './BotReplayDrawer'

describe('BotReplayDrawer', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('打开即播第 1 帧，逐帧推进到最后一帧', () => {
    render(<BotReplayDrawer open onClose={() => {}} />)
    expect(screen.getByText(/第 1 \/ 5 帧/)).toBeTruthy()
    expect(screen.getByText(DEMO_X3_BROWSER_FRAMES[0]!.url)).toBeTruthy()

    // 帧时长最多 1600ms，一次推 2 秒稳过一帧
    for (let i = 1; i < DEMO_X3_BROWSER_FRAMES.length; i++) {
      act(() => void vi.advanceTimersByTime(2000))
    }
    expect(screen.getByText(`第 ${DEMO_X3_BROWSER_FRAMES.length} / 5 帧`)).toBeTruthy()
    expect(screen.getByText('机器人已放弃点击')).toBeTruthy()
  })

  it('点时间轴可跳到指定帧', () => {
    render(<BotReplayDrawer open onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: '跳到第 4 帧' }))
    expect(screen.getByText('第 4 / 5 帧')).toBeTruthy()
    expect(screen.getByText(DEMO_X3_BROWSER_FRAMES[3]!.action)).toBeTruthy()
  })

  it('未打开时不渲染画面', () => {
    render(<BotReplayDrawer open={false} onClose={() => {}} />)
    expect(screen.queryByText(/帧/)).toBeNull()
  })
})
