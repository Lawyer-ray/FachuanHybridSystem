// @vitest-environment jsdom
/**
 * 「登录 Qoder」弹窗 + 菜单里的登录入口（jsdom）。
 *
 * 必须成立的事实：
 * 1. **需要登录的行给得出动作**：`action="login"` 的行渲染「登录 Qoder」按钮，
 *    点它打开弹窗——只置灰不给入口，用户唯一的结论是「这功能坏了」；
 * 2. **授权链接必须能点开、能复制**：链接是设备授权的一次性 challenge，被弹窗
 *    拦截或截断就等于白点（服务器与律师的机器常常不是同一台）；
 * 3. **轮询到成功要自动通知调用方刷新清单**：否则用户登录完回到菜单，那一行
 *    仍然是置灰的，只能刷新页面；
 * 4. **失败停在原地并可重试**（不是关掉让用户自己再找入口）；
 * 5. **关闭途径**：Escape / 关闭按钮 / 点遮罩——**不**包括成功（成功也关，但同时
 *    刷新清单）。
 *
 * 网络全部 mock（`../api`），本用例不碰后端、不起 CLI。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AgentBackendOption, QoderLoginState } from '../types'

vi.mock('../api', () => ({
  startQoderLogin: vi.fn(),
  fetchQoderLoginStatus: vi.fn(),
  fetchQoderByok: vi.fn(),
  registerQoderByok: vi.fn(),
  deleteQoderByok: vi.fn(),
}))

import { fetchQoderLoginStatus, startQoderLogin } from '../api'
import { AgentLoginDialog } from './AgentLoginDialog'
import { AgentRow } from './AgentRow'

const startMock = vi.mocked(startQoderLogin)
const statusMock = vi.mocked(fetchQoderLoginStatus)

const URL_SAMPLE = 'https://qoder.com/device/selectAccounts?challenge=abc&client_id=e88'

function loginState(over: Partial<QoderLoginState> = {}): QoderLoginState {
  return { login_id: 'L1', state: 'waiting', url: URL_SAMPLE, message: '', account: '', ...over }
}

function option(over: Partial<AgentBackendOption> = {}): AgentBackendOption {
  return {
    kind: 'qoder',
    label: 'Qoder',
    description: 'Qoder Agent SDK',
    available: false,
    reason: '未登录 Qoder',
    capabilities: {},
    models: [],
    default_model: null,
    action: 'login',
    action_label: '登录 Qoder',
    ...over,
  }
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('AgentRow 的登录入口', () => {
  it('action=login 的行渲染登录按钮，点了把 kind 交回调用方', () => {
    const onLogin = vi.fn()
    render(
      <AgentRow
        option={option()}
        picked={false}
        isDefault={false}
        blockedByLimit={false}
        model=""
        onToggle={() => {}}
        onSelectModel={() => {}}
        onLogin={onLogin}
      />,
    )
    const button = screen.getByTestId('agent-login-qoder')
    expect(button.textContent).toContain('登录 Qoder')
    fireEvent.click(button)
    expect(onLogin).toHaveBeenCalledWith('qoder')
  })

  it('不需要登录的行不出现登录按钮（避免每行都挂一个死入口）', () => {
    render(
      <AgentRow
        option={option({ kind: 'pi', label: 'Pi', available: true, reason: '', action: '', action_label: '' })}
        picked={false}
        isDefault
        blockedByLimit={false}
        model=""
        onToggle={() => {}}
        onSelectModel={() => {}}
        onLogin={() => {}}
      />,
    )
    expect(screen.queryByTestId('agent-login-pi')).toBeNull()
  })
})

describe('AgentLoginDialog', () => {
  it('打开即发起授权，渲染可点开 / 可复制的链接', async () => {
    startMock.mockResolvedValue(loginState())
    statusMock.mockResolvedValue(loginState())
    render(<AgentLoginDialog kind="qoder" label="Qoder" onClose={() => {}} onDone={() => {}} />)

    const link = await screen.findByRole('link', { name: /打开授权页/ })
    expect(link.getAttribute('href')).toBe(URL_SAMPLE)
    expect(link.getAttribute('target')).toBe('_blank')
    // 复制用的是完整链接（截断的 challenge 授权必然失败）
    expect((screen.getByLabelText('授权链接') as HTMLInputElement).value).toBe(URL_SAMPLE)
  })

  it('轮询到 success 时通知调用方刷新清单', async () => {
    startMock.mockResolvedValue(loginState())
    statusMock.mockResolvedValue(loginState({ state: 'success', message: '已登录 Qoder' }))
    const onDone = vi.fn()
    render(<AgentLoginDialog kind="qoder" label="Qoder" onClose={() => {}} onDone={onDone} />)

    await waitFor(() => expect(onDone).toHaveBeenCalled(), { timeout: 4000 })
    expect(screen.getByText(/已登录 Qoder/)).toBeTruthy()
  })

  it('授权失败时停在原地并给出「重新登录」', async () => {
    startMock.mockResolvedValue(loginState())
    statusMock.mockResolvedValue(loginState({ state: 'expired', message: '授权超时，请重新登录。' }))
    const onDone = vi.fn()
    render(<AgentLoginDialog kind="qoder" label="Qoder" onClose={() => {}} onDone={onDone} />)

    const retry = await screen.findByRole('button', { name: '重新登录' }, { timeout: 4000 })
    expect(onDone).not.toHaveBeenCalled()
    fireEvent.click(retry)
    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(2))
  })

  it('发起失败时显示后端给的原因（不是一句「服务器错误」）', async () => {
    startMock.mockRejectedValue(new Error('未找到 qodercli（请安装 qoder-agent-sdk）'))
    render(<AgentLoginDialog kind="qoder" label="Qoder" onClose={() => {}} onDone={() => {}} />)

    expect(await screen.findByText(/未找到 qodercli/)).toBeTruthy()
  })

  it('Escape 关闭', async () => {
    startMock.mockResolvedValue(loginState())
    statusMock.mockResolvedValue(loginState())
    const onClose = vi.fn()
    render(<AgentLoginDialog kind="qoder" label="Qoder" onClose={onClose} onDone={() => {}} />)
    await screen.findByRole('dialog')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
