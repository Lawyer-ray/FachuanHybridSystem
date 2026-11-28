// @vitest-environment jsdom
/**
 * `useUiPendingAction`（jsdom）：页面挂载的那一刻取走排队动作，且只取一次。
 *
 * 这条不变量是「先跳过去、再继续做」机制的收尾：取多一次 = 写类动作被执行两次，
 * 取少一次 = 律师看到「AI 已经操作了」而页面没动。
 */
import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { queuePageAction, takePageActions } from '../ui-tools'
import type { UiActionRequest } from '../ui-tools'
import { useUiPendingAction } from './use-ui-pending-action'

const PAGE = '/material-prep'

function request(callId: string, page: string = PAGE): UiActionRequest {
  return { callId, action: 'ui_material_prep_set_stage', args: { stage: 'todo' }, route: page }
}

describe('useUiPendingAction', () => {
  it('挂载时把本页排队的请求按入队顺序交给 handler', () => {
    queuePageAction(PAGE, request('call-1'))
    queuePageAction(PAGE, request('call-2'))
    const handle = vi.fn()

    renderHook(() => useUiPendingAction(PAGE, handle))

    expect(handle).toHaveBeenCalledTimes(2)
    expect(handle.mock.calls[0]?.[0]).toEqual(request('call-1'))
    expect(handle.mock.calls[1]?.[0]).toEqual(request('call-2'))
    // 取出即清：页面重挂载不会把同一条请求再执行一次
    expect(takePageActions(PAGE)).toEqual([])
  })

  it('不碰别的页面的队列（那条请求仍等着它自己的页面）', () => {
    queuePageAction('/projects', request('call-other', '/projects'))
    const handle = vi.fn()

    renderHook(() => useUiPendingAction(PAGE, handle))

    expect(handle).not.toHaveBeenCalled()
    expect(takePageActions('/projects').map((req) => req.callId)).toEqual(['call-other'])
  })

  it('队列为空时挂载不报错、也不调 handler', () => {
    const handle = vi.fn()
    expect(() => renderHook(() => useUiPendingAction('/never-queued', handle))).not.toThrow()
    expect(handle).not.toHaveBeenCalled()
  })
})
