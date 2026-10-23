// @vitest-environment jsdom
/**
 * CopilotWelcome 空态欢迎页单测（jsdom）。
 * 全局（无 context）与业务范围内（case）两套快捷任务；点击即发送。
 * store 直接 setState 注入，send 用 vi.fn 替身。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCopilot } from '../store'
import { CopilotWelcome } from './CopilotWelcome'

describe('CopilotWelcome 空态欢迎页', () => {
  beforeEach(() => {
    const send = vi.fn()
    useCopilot.setState({ context: null, messages: [], streaming: false, send })
  })

  it('全局助手：问候语 + 4 张通用快捷卡', () => {
    render(<CopilotWelcome />)
    expect(screen.getByText('你好，我是法穿SI超级助理')).toBeTruthy()
    for (const name of ['我的案件', '到期期限', '未收款汇总', '今日待跟进']) {
      expect(screen.getByRole('button', { name })).toBeTruthy()
    }
  })

  it('业务范围内（案件）：切换为案件域快捷卡 + 本案副标题', () => {
    useCopilot.setState({ context: { origin: 'case', refId: 390, title: '某某公司执行异议之诉' } })
    render(<CopilotWelcome />)
    expect(screen.getByText(/已就位——本案的材料、日志、当事人与系统数据/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '梳理材料' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '文书起草思路' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '我的案件' })).toBeNull()
  })

  it('点击快捷卡直接发送对应提示词', () => {
    render(<CopilotWelcome />)
    fireEvent.click(screen.getByRole('button', { name: '到期期限' }))
    expect(useCopilot.getState().send).toHaveBeenCalledWith('近两周有哪些到期的期限？按紧急程度排一下。')
  })
})
