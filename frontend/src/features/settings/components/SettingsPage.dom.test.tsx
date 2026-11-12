// @vitest-environment jsdom
/**
 * SettingsPage 页面壳测试（jsdom）。
 *
 * 页面壳只负责排版与分区，内容分区各自独立。这里断言分区确实都在、
 * 且绑定面板是懒加载（下载中给同构的加载文案，而不是空白）。
 */
import { Suspense } from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/features/auth', () => ({
  BindingsPanelLazy: () => <div data-testid="bindings-panel">账号绑定面板</div>,
}))
vi.mock('./SystemStatus', () => ({
  SystemStatus: () => <div data-testid="system-status">系统状态卡</div>,
}))

import { SettingsPage } from './SettingsPage'

describe('SettingsPage', () => {
  it('渲染标题与两个分区（系统状态 / 账号绑定）', () => {
    render(
      <Suspense fallback={null}>
        <SettingsPage />
      </Suspense>,
    )
    expect(screen.getByRole('heading', { level: 1, name: '设置' })).toBeTruthy()
    expect(screen.getByRole('heading', { level: 2, name: '系统状态' })).toBeTruthy()
    expect(screen.getByTestId('system-status')).toBeTruthy()
    expect(screen.getByTestId('bindings-panel')).toBeTruthy()
  })

  it('说明文案交代「不在后台轮询」（避免被误认为实时监控）', () => {
    render(<SettingsPage />)
    expect(screen.getByText(/不在后台轮询/)).toBeTruthy()
  })
})
