// @vitest-environment jsdom
/**
 * workbench/index.ts 出口测试（jsdom）。
 *
 * 这一层是 feature 的对外契约，函数体虽小但决定了懒加载拆包是否生效：
 * - 两个 preload 加载器必须是真正的动态 import（返回 Promise，且能拿到组件）
 * - 两个 Lazy 组件必须是 React.lazy（typeof === 'object' 且带 $$typeof）
 *
 * 这里直接调用加载器验证 chunk 可取，并对 Lazy 做类型断言，
 * 不渲染真实页面（那会连带拉入整域依赖）。
 */
import { describe, expect, it } from 'vitest'

import {
  DealDetailPageLazy,
  EditProjectPageLazy,
  preloadDealDetailPage,
  preloadEditProjectPage,
  preloadWorkbenchPage,
  WorkbenchPageLazy,
} from './index'

describe('workbench/index 出口', () => {
  it('preloadWorkbenchPage 返回 Promise 并能取到 WorkbenchPage', async () => {
    const p = preloadWorkbenchPage()
    expect(typeof p.then).toBe('function')
    const mod = await p
    expect(typeof mod.WorkbenchPage).toBe('function')
  })

  // 这条会把整个详情页依赖图（含 pdfjs）动态拉一遍：并行跑测试时 5s 默认超时
  // 经常不够，给到 20s——它验的是「chunk 能取到」，不是速度
  it('preloadDealDetailPage 返回 Promise 并能取到 DealDetailPage', async () => {
    const p = preloadDealDetailPage()
    expect(typeof p.then).toBe('function')
    const mod = await p
    expect(typeof mod.DealDetailPage).toBe('function')
  }, 20000)

  it('WorkbenchPageLazy 是合法的 React.lazy 组件', () => {
    expect(WorkbenchPageLazy).toBeTruthy()
    // React.lazy 返回带 $$typeof 的对象
    expect((WorkbenchPageLazy as unknown as { $$typeof?: symbol }).$$typeof).toBeTypeOf('symbol')
  })

  it('DealDetailPageLazy 是合法的 React.lazy 组件', () => {
    expect(DealDetailPageLazy).toBeTruthy()
    expect((DealDetailPageLazy as unknown as { $$typeof?: symbol }).$$typeof).toBeTypeOf('symbol')
  })

  it('preloadEditProjectPage 返回 Promise 并能取到 ProjectEditPage', async () => {
    const p = preloadEditProjectPage()
    expect(typeof p.then).toBe('function')
    const mod = await p
    expect(typeof mod.ProjectEditPage).toBe('function')
  })

  it('EditProjectPageLazy 是合法的 React.lazy 组件', () => {
    expect((EditProjectPageLazy as unknown as { $$typeof?: symbol }).$$typeof).toBeTypeOf('symbol')
  })

  it('两个加载器复用同一 import()（模块缓存只下载一次）', async () => {
    const a = await preloadWorkbenchPage()
    const b = await preloadWorkbenchPage()
    // 动态 import 命中模块缓存，两次拿到同一个模块对象
    expect(a).toBe(b)
  })
})
