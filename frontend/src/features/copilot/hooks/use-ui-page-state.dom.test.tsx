// @vitest-environment jsdom
/**
 * `useUiPageState`（jsdom）：挂载即登记、读到**最新一次渲染**的值、卸载即注销。
 *
 * 三条都是「静默失效」的解药：
 * - 忘登记 → AI 问页面时永远 `no_page_state`，模型只能改问律师；
 * - 忘注销 → 离开页面后仍答旧状态，模型据此操作一个不存在的页面；
 * - 读到注册时的旧值 → 律师看到的是过期快照（比没有更糟，模型会当真）。
 */
import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { readPageState } from '../ui-tools/page-state'
import { useUiPageState } from './use-ui-page-state'

const PAGE = 'material-prep'

describe('useUiPageState', () => {
  it('挂载即登记、读到最新值；卸载后不再声明状态', () => {
    const { rerender, unmount } = renderHook(({ state }) => useUiPageState(PAGE, state), {
      initialProps: { state: { stage: 'todo' } },
    })
    expect(readPageState(PAGE)?.state).toEqual({ stage: 'todo' })

    rerender({ state: { stage: 'done' } })
    expect(readPageState(PAGE)?.state).toEqual({ stage: 'done' })

    unmount()
    expect(readPageState(PAGE)).toBeNull()
  })

  it('同页两个实例：卸载一个后另一个仍能声明状态，全部卸载才没有状态', () => {
    const first = renderHook(() => useUiPageState(PAGE, { v: 'first' }))
    const second = renderHook(() => useUiPageState(PAGE, { v: 'second' }))
    // 最近注册的实例是该页的「当前」实例
    expect(readPageState(PAGE)?.state.v).toBe('second')

    second.unmount()
    expect(readPageState(PAGE)?.state.v).toBe('first')

    first.unmount()
    expect(readPageState(PAGE)).toBeNull()
  })
})
