// @vitest-environment jsdom
/**
 * 会话行的鼠标手势（jsdom）：单击进入 / 双击重命名 / 右键直接弹删除确认。
 *
 * 锁的是用户的三个原话诉求，以及两个「看起来也能跑」的错法：
 * 1. **单击**行只切会话，不弹删除、不进编辑；
 * 2. **双击**行进编辑态，输入框是原标题且**已全选**——否则律师想改名还得先手动删掉
 *    旧标题，等于双击白给；
 * 3. **右键**行调用一次 `onRequestDelete`，并且该 `contextmenu` 事件
 *    `defaultPrevented === true`（「无需默认右键网页菜单」的唯一实现方式）。
 *    只在本行 `preventDefault`，不做全局屏蔽——正文区右键的复制/翻译/检查不能被吃掉；
 * 4. **右键子按钮**不额外弹删除确认（否则行容器再收一次事件，等于弹两次）；
 * 5. **双击子按钮**不误进重命名（否则双击垃圾桶顺带改名）；
 * 6. 编辑态 Enter 提交、Esc 取消（双击引入的新入口不能破坏旧键盘路径）。
 */

import { createEvent } from '@testing-library/dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AgentSession } from '../../types'
import { SessionRow } from './SessionRow'

const TITLE = '第一份委托的对话'

function session(over: Partial<AgentSession> = {}): AgentSession {
  return {
    session_id: 's-1',
    title: TITLE,
    status: 'active',
    llm_model: '',
    agent_kind: 'pi',
    created_at: '2026-10-20T09:00:00',
    updated_at: '2026-10-20T10:00:00',
    ...over,
  }
}

function renderRow(over: Partial<AgentSession> = {}) {
  const onSwitch = vi.fn()
  const onRequestDelete = vi.fn()
  const onRename = vi.fn()
  render(
    <SessionRow
      session={session(over)}
      active={false}
      compact={false}
      onSwitch={onSwitch}
      onRequestDelete={onRequestDelete}
      onRename={onRename}
    />,
  )
  const row = screen.getByText(TITLE).closest('[role="button"]') as HTMLElement
  return { row, onSwitch, onRequestDelete, onRename }
}

describe('SessionRow：单击进入', () => {
  it('单击行只切会话：onSwitch 一次，不弹删除、不进编辑', () => {
    const { row, onSwitch, onRequestDelete } = renderRow()

    fireEvent.click(row)

    expect(onSwitch).toHaveBeenCalledTimes(1)
    expect(onRequestDelete).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox')).toBeNull()
  })
})

describe('SessionRow：双击重命名', () => {
  it('双击行进编辑态，输入框是原标题且文本已全选', () => {
    const { row, onRequestDelete } = renderRow()

    fireEvent.doubleClick(row)

    const input = screen.getByRole('textbox') as HTMLInputElement
    expect(input.value).toBe(TITLE)
    // 全选：起点 0、终点为标题长度（用户直接打字就是覆盖旧标题）
    expect([input.selectionStart, input.selectionEnd]).toEqual([0, TITLE.length])
    expect(document.activeElement).toBe(input)
    expect(onRequestDelete).not.toHaveBeenCalled()
  })
})

describe('SessionRow：右键删除', () => {
  it('右键行触发一次删除确认，并屏蔽浏览器默认菜单', () => {
    const { row, onRequestDelete, onSwitch } = renderRow()

    const ev = createEvent.contextMenu(row)
    fireEvent(row, ev)

    expect(onRequestDelete).toHaveBeenCalledTimes(1)
    expect(ev.defaultPrevented).toBe(true)
    // 右键不是「进入」手势
    expect(onSwitch).not.toHaveBeenCalled()
  })
})

describe('SessionRow：子按钮隔离', () => {
  it('右键铅笔 / 垃圾桶：不冒泡到行，不额外弹删除确认', () => {
    const { onRequestDelete } = renderRow()
    const pencil = screen.getByRole('button', { name: '重命名' })
    const trash = screen.getByRole('button', { name: '删除对话' })

    const pencilEv = createEvent.contextMenu(pencil)
    fireEvent(pencil, pencilEv)
    expect(onRequestDelete).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox')).toBeNull()

    const trashEv = createEvent.contextMenu(trash)
    fireEvent(trash, trashEv)
    expect(onRequestDelete).not.toHaveBeenCalled()

    // 按钮上只拦冒泡、不拦浏览器默认：右键按钮时系统菜单照常
    expect([pencilEv.defaultPrevented, trashEv.defaultPrevented]).toEqual([false, false])
  })

  it('双击铅笔 / 垃圾桶：不误进重命名', () => {
    const { onRequestDelete } = renderRow()

    fireEvent.doubleClick(screen.getByRole('button', { name: '删除对话' }))
    expect(screen.queryByRole('textbox')).toBeNull()

    fireEvent.doubleClick(screen.getByRole('button', { name: '重命名' }))
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(onRequestDelete).not.toHaveBeenCalled()
  })

  it('单击垃圾桶仍走删除（隔离没有吃掉按钮自己的 click）', () => {
    const { onRequestDelete, onSwitch } = renderRow()

    fireEvent.click(screen.getByRole('button', { name: '删除对话' }))

    expect(onRequestDelete).toHaveBeenCalledTimes(1)
    expect(onSwitch).not.toHaveBeenCalled()
  })
})

describe('SessionRow：编辑态提交', () => {
  it('Enter 提交 onRename(id, 新标题)', () => {
    const { row, onRename } = renderRow()

    fireEvent.doubleClick(row)
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: '改过的标题' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(onRename).toHaveBeenCalledWith('s-1', '改过的标题')
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('Escape 退出且不提交', () => {
    const { row, onRename } = renderRow()

    fireEvent.doubleClick(row)
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: '改了但不保存' } })
    fireEvent.keyDown(input, { key: 'Escape' })

    expect(onRename).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox')).toBeNull()
    // 回到列表行，标题原样
    expect(screen.getByText(TITLE)).toBeTruthy()
  })
})
