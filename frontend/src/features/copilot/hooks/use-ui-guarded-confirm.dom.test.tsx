// @vitest-environment jsdom
/**
 * `useUiGuardedConfirm`（jsdom）：**真的渲染出**一个对话框，并且两个按钮分别回 `false` / `true`。
 *
 * ## 为什么要一条真实的 DOM 测试
 *
 * 这条 hook 的挂载方式是命令式 React root（`createRoot` 到一个挂在 `body` 下的容器里，
 * 见该文件头）。纯逻辑测试只能证明「注册了一个 handler」，证明不了「律师真的看得见、
 * 点得到」——而这一层坏掉的样子是：guarded 动作永远被 fail closed 拒掉（因为没有宿主
 * 在处理），律师只看到「AI 什么都不做」，日志里却只有一句 warn。
 *
 * 三个场景对应三种真实结局：
 * A. 点「取消」→ `false`（不执行，但弹框必须自己收掉）；
 * B. 点「确认执行」→ `true`；
 * C. 还在等律师点时宿主卸载（面板收起 / 路由切走）→ `false`，绝不能让 store 的写锁
 *    永远等一个已经不存在的对话框。
 */

import { act, cleanup, fireEvent, renderHook, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { askGuardedConfirm } from '../store/ui-guarded-confirm'
import type { GuardedConfirmRequest } from '../store/ui-guarded-confirm'
import { useUiGuardedConfirm } from './use-ui-guarded-confirm'

function request(overrides: Partial<GuardedConfirmRequest> = {}): GuardedConfirmRequest {
  return {
    action: 'ui_material_prep_delete_pack',
    title: '删除材料包（不可恢复）',
    args: { packId: 812 },
    callId: 'call-dom-1',
    ...overrides,
  }
}

/** 打开一次确认；返回那个「等律师点一下」的 Promise（不 await，先让对话框渲染出来） */
function ask(req: GuardedConfirmRequest): Promise<boolean> {
  let pending: Promise<boolean> | null = null
  act(() => {
    pending = askGuardedConfirm(req)
  })
  if (pending === null) throw new Error('askGuardedConfirm 没有返回 Promise')
  return pending
}

afterEach(() => {
  // renderHook 的树 + 本 hook 自己挂的 root 都由它一起清掉（后者在卸载 effect 里 dispose）
  cleanup()
  vi.restoreAllMocks()
})

describe('useUiGuardedConfirm：真的渲染、真的回话', () => {
  it('点「取消」→ 回 false，弹框收掉（没同意就不执行）', async () => {
    renderHook(() => useUiGuardedConfirm())

    const pending = ask(request())
    const dialog = await screen.findByRole('dialog')

    // 律师必须能认出「是哪一条、对象是谁」：标题 + 参数预览都要在
    expect(dialog.textContent).toContain('需要你确认：删除材料包（不可恢复）')
    expect(screen.getByTestId('ui-guarded-confirm-args').textContent).toContain('"packId": 812')

    fireEvent.click(screen.getByRole('button', { name: '取消' }))

    await expect(pending).resolves.toBe(false)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('点「确认执行」→ 回 true（这一下只放行本地执行，不是批准凭据）', async () => {
    renderHook(() => useUiGuardedConfirm())

    const pending = ask(request({ callId: 'call-dom-2' }))
    await screen.findByRole('dialog')

    fireEvent.click(screen.getByRole('button', { name: '确认执行' }))

    await expect(pending).resolves.toBe(true)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('参数预览截到 400 字（弹框只用来认对象，不把整份参数糊在屏幕上）', async () => {
    renderHook(() => useUiGuardedConfirm())

    const long = 'x'.repeat(1000)
    const pending = ask(request({ callId: 'call-dom-3', args: { packId: 812, note: long } }))
    await screen.findByRole('dialog')

    const preview = screen.getByTestId('ui-guarded-confirm-args').textContent ?? ''
    expect(preview.length).toBeLessThanOrEqual(401)
    expect(preview.endsWith('…')).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    await expect(pending).resolves.toBe(false)
  })

  it('还在等律师点时宿主卸载（面板收起 / 路由切走）→ 按「没同意」结账', async () => {
    const { unmount } = renderHook(() => useUiGuardedConfirm())

    const pending = ask(request({ callId: 'call-dom-4' }))
    await screen.findByRole('dialog')

    act(() => {
      unmount()
    })

    await expect(pending).resolves.toBe(false)
    expect(document.querySelector('[data-ui-guarded-confirm-host]')).toBeNull()
  })

  it('没有挂载宿主时 fail closed：回 false 并 warn（不弹框，也没人可问）', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    await expect(askGuardedConfirm(request({ callId: 'call-dom-5' }))).resolves.toBe(false)
    expect(warn.mock.calls.some((call) => String(call[0]).includes('[ui-guarded-confirm]'))).toBe(true)
  })
})
