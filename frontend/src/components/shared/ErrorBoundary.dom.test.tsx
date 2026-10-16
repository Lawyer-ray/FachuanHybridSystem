// @vitest-environment jsdom
/**
 * ErrorBoundary 组件冒烟（jsdom）。
 *
 * 覆盖：无错误透传 children、渲染抛错 → fallback UI + console.error 上报点位、
 * chunk 加载错误的专属文案、PageErrorBoundary 按路由切换复位（resetKey=pathname）
 * 且健康时不重挂子树（同一子树跨 pathname 保持本地状态——否则每次切路由整页
 * 重建，正是导航闪烁与 /material-prep ↔ /:id 丢状态的源头）。
 * 「重新加载」按钮走 window.location.reload（jsdom 不实现导航），不在冒烟范围。
 */
import { Link, MemoryRouter, Route, Routes } from 'react-router'
import { fireEvent, render, screen } from '@testing-library/react'
import { useState, type ReactNode } from 'react'
import { type MockInstance, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ErrorBoundary, PageErrorBoundary } from './ErrorBoundary'

function Boom({ message }: { message: string }): ReactNode {
  throw new Error(message)
}

let errorSpy: MockInstance<(...args: unknown[]) => void>

beforeEach(() => {
  // 静音 React 的真实报错输出，只留断言用
  errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  errorSpy.mockRestore()
})

describe('ErrorBoundary', () => {
  it('无错误时透传 children', () => {
    render(
      <ErrorBoundary>
        <div>正常内容</div>
      </ErrorBoundary>,
    )
    expect(screen.getByText('正常内容')).toBeTruthy()
    expect(errorSpy).not.toHaveBeenCalled()
  })

  it('子组件渲染抛错：展示兜底 UI，且 console.error 上报点位被调用', () => {
    render(
      <ErrorBoundary>
        <Boom message="渲染炸了" />
      </ErrorBoundary>,
    )
    expect(screen.getByText('页面出错了')).toBeTruthy()
    expect(screen.getByText('重新加载')).toBeTruthy()
    // componentDidCatch 的上报：('[ErrorBoundary]', error, componentStack)
    const boundaryCall = errorSpy.mock.calls.find((c) => c[0] === '[ErrorBoundary]')
    expect(boundaryCall).toBeDefined()
    expect(boundaryCall?.[1]).toBeInstanceOf(Error)
    expect((boundaryCall?.[1] as Error).message).toBe('渲染炸了')
    expect(typeof boundaryCall?.[2]).toBe('string')
  })

  it('懒加载 chunk 失败的报错：走「页面资源加载失败」专属文案', () => {
    render(
      <ErrorBoundary>
        <Boom message="Failed to fetch dynamically imported module: /assets/x.js" />
      </ErrorBoundary>,
    )
    expect(screen.getByText('页面资源加载失败')).toBeTruthy()
    expect(
      screen.getByText('可能是应用刚发布了新版本，本地缓存的旧资源已失效。刷新一次通常即可恢复。'),
    ).toBeTruthy()
    expect(screen.queryByText('页面出错了')).toBeNull()
  })
})

describe('PageErrorBoundary 路由级复位', () => {
  it('单页崩溃后切到其他路由：边界按 pathname 复位，新页面正常渲染', () => {
    render(
      <MemoryRouter initialEntries={['/crash']}>
        <Routes>
          <Route
            path="/crash"
            element={
              <PageErrorBoundary>
                <Boom message="页面级崩溃" />
              </PageErrorBoundary>
            }
          />
          <Route
            path="/ok"
            element={
              <PageErrorBoundary>
                <div>完好的页面</div>
              </PageErrorBoundary>
            }
          />
        </Routes>
        <Link to="/ok">去完好页面</Link>
      </MemoryRouter>,
    )
    expect(screen.getByText('页面出错了')).toBeTruthy()

    fireEvent.click(screen.getByText('去完好页面'))
    expect(screen.getByText('完好的页面')).toBeTruthy()
    expect(screen.queryByText('页面出错了')).toBeNull()
  })

  it('页面健康时切路由：子树不重挂，本地状态跨 pathname 保留', () => {
    function Counter() {
      const [n, setN] = useState(0)
      return (
        <button type="button" onClick={() => setN((v) => v + 1)}>
          count:{n}
        </button>
      )
    }
    render(
      <MemoryRouter initialEntries={['/list']}>
        {/* 边界放在路由之外、跨路由常驻（与 AppShell 的用法一致） */}
        <PageErrorBoundary>
          <Counter />
          <Routes>
            <Route path="/list" element={<div>列表</div>} />
            <Route path="/list/7" element={<div>详情 7</div>} />
          </Routes>
        </PageErrorBoundary>
        <Link to="/list/7">去详情</Link>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByText('count:0'))
    expect(screen.getByText('count:1')).toBeTruthy()

    fireEvent.click(screen.getByText('去详情'))
    expect(screen.getByText('详情 7')).toBeTruthy()
    // key=pathname 的旧实现会在这里把 Counter 重挂回 count:0
    expect(screen.getByText('count:1')).toBeTruthy()
    expect(errorSpy).not.toHaveBeenCalled()
  })
})
