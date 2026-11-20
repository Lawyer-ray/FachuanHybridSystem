// @vitest-environment jsdom
/**
 * `MentionMenu`（jsdom）：a11y 契约 + 焦点不掉。
 *
 * 断言的是「读屏与键盘用户实际依赖的东西」，不是类名：
 * - `role="listbox"` 在滚动容器上，`aria-activedescendant` 指向**高亮那一行**的 id；
 * - 行是 `role="option"` + `aria-selected`；
 * - 行用 `onMouseDown`（不是 click）：`fireEvent.mouseDown` 返回 false 表示
 *   `preventDefault()` 被调用过 —— 这正是「点选时 textarea 不丢焦点」的机制，
 *   丢焦点会连带丢 selectionStart，选完引用光标就跳到末尾；
 * - 全套键盘流程（`@` → ↓ → Enter）跑在真实 textarea 上，选完焦点仍在输入框。
 */
import { fireEvent, render, waitFor, within } from '@testing-library/react'
import { useRef, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { applyMention, makeMentionInsert, mentionOptionId, type MentionCandidate, type MentionSource } from '../domain'
import { useMentionMenu } from '../hooks/use-mention-menu'
import { MentionMenu } from './MentionMenu'

const LISTBOX = 'test-mention-listbox'

const doc = (label: string, subpath = `1-一审/${label}`): MentionCandidate => ({
  kind: 'document',
  label,
  sublabel: '1-一审 · 12KB',
  subpath,
  owner: { kind: 'contract', id: 5 },
})

const readyGroups = [
  { key: 'case', title: '案件', status: 'ready' as const, items: [{ kind: 'case' as const, label: '张三诉李四' }] },
  { key: 'document', title: '文书', status: 'ready' as const, items: [doc('起诉状.pdf'), doc('证据清单.pdf')] },
]

describe('MentionMenu：结构与 a11y', () => {
  it('listbox 在滚动容器上，aria-activedescendant 指向高亮行', () => {
    const { container } = render(
      <MentionMenu
        id={LISTBOX}
        groups={readyGroups}
        highlight={{ key: 'document', index: 1 }}
        onHover={vi.fn()}
        onPick={vi.fn()}
      />,
    )
    const listbox = within(container).getByRole('listbox')
    expect(listbox.id).toBe(LISTBOX)
    expect(listbox.getAttribute('aria-activedescendant')).toBe(mentionOptionId('document', 1))
    const options = within(listbox).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(['张三诉李四', '起诉状.pdf1-一审 · 12KB', '证据清单.pdf1-一审 · 12KB'])
    // 只有高亮那一行 aria-selected=true
    expect(options.map((o) => o.getAttribute('aria-selected'))).toEqual(['false', 'false', 'true'])
    // 分组标题分组展示（读屏按组播报）
    expect(within(listbox).getAllByRole('group').map((g) => g.getAttribute('aria-label'))).toEqual(['案件', '文书'])
  })

  it('一行一个 id：id 与高亮位置一一对应（扁平下标会错位）', () => {
    const { container } = render(
      <MentionMenu id={LISTBOX} groups={readyGroups} highlight={null} onHover={vi.fn()} onPick={vi.fn()} />,
    )
    expect(within(container).getByRole('listbox').hasAttribute('aria-activedescendant')).toBe(false)
    expect(container.querySelector(`#${mentionOptionId('document', 0)}`)?.textContent).toContain('起诉状.pdf')
  })

  it('mousedown 被 preventDefault（保 textarea 焦点）+ 上报选中位置', () => {
    const onPick = vi.fn()
    const { container } = render(
      <MentionMenu id={LISTBOX} groups={readyGroups} highlight={null} onHover={vi.fn()} onPick={onPick} />,
    )
    const option = container.querySelector(`#${mentionOptionId('document', 0)}`) as HTMLElement
    // fireEvent 返回 false = 默认行为已被阻止（焦点不会被按钮抢走）
    expect(fireEvent.mouseDown(option)).toBe(false)
    expect(onPick).toHaveBeenCalledWith({ key: 'document', index: 0 })
  })

  it('已就绪但空的组不占位；全空时给一句可操作的空态', () => {
    const { container } = render(
      <MentionMenu
        id={LISTBOX}
        groups={[{ key: 'case', title: '案件', status: 'ready', items: [] }]}
        highlight={null}
        onHover={vi.fn()}
        onPick={vi.fn()}
      />,
    )
    expect(within(container).queryAllByRole('option')).toHaveLength(0)
    expect(container.textContent).toContain('没有匹配的引用对象')
  })

  it('还在拉取的组显示「搜索中…」（可区分「在搜」与「没有」）', () => {
    const { container } = render(
      <MentionMenu
        id={LISTBOX}
        groups={[{ key: 'case', title: '案件', status: 'pending', items: [] }]}
        highlight={null}
        onHover={vi.fn()}
        onPick={vi.fn()}
      />,
    )
    expect(within(container).getByRole('status').textContent).toContain('搜索中')
  })
})

/** 迷你输入区：真实 textarea + 管线 + 菜单，模拟 Composer 的接线顺序 */
const source: MentionSource = {
  key: 'document',
  trigger: '@',
  title: '文书',
  load: () => Promise.resolve([doc('起诉状.pdf'), doc('证据清单.pdf')]),
  toInsert: makeMentionInsert,
}

function Harness({ onPicked }: { onPicked?: (label: string) => void }) {
  const [text, setText] = useState('')
  const [caret, setCaret] = useState(0)
  const ref = useRef<HTMLTextAreaElement>(null)
  const menu = useMentionMenu({
    text,
    caret,
    sources: [source],
    onPick: (insert, token) => {
      const next = applyMention(text, token, insert)
      setText(next.text)
      setCaret(next.caret)
      onPicked?.(insert.label)
      requestAnimationFrame(() => {
        ref.current?.focus()
        ref.current?.setSelectionRange(next.caret, next.caret)
      })
    },
  })
  return (
    <div>
      <textarea
        ref={ref}
        value={text}
        aria-controls={menu.open ? LISTBOX : undefined}
        aria-expanded={menu.open}
        onChange={(e) => {
          setText(e.target.value)
          setCaret(e.target.selectionStart ?? 0)
        }}
        onKeyDown={(e) => {
          if (menu.onKeyDown(e) === 'consumed') e.preventDefault()
        }}
      />
      {menu.open && (
        <MentionMenu
          id={LISTBOX}
          groups={menu.groups}
          highlight={menu.highlight}
          onHover={menu.onHover}
          onPick={(target) => menu.pick(target)}
        />
      )}
    </div>
  )
}

describe('MentionMenu：键盘全流程（焦点始终在 textarea）', () => {
  it('`@` → ↓ → Enter：改写草稿为内联引用文本，菜单收起，焦点留在输入框', async () => {
    const onPicked = vi.fn()
    const { container, getByRole } = render(<Harness onPicked={onPicked} />)
    const box = getByRole('textbox') as HTMLTextAreaElement

    fireEvent.change(box, { target: { value: '@起诉' } })
    await waitFor(() => expect(container.querySelector('[role="listbox"]')).not.toBeNull())
    // 打开时 textarea 上的 aria-expanded/aria-controls 跟着开
    expect(box.getAttribute('aria-expanded')).toBe('true')
    expect(box.getAttribute('aria-controls')).toBe(LISTBOX)
    // 先等行真的到位：菜单壳子一开就按 ↓ 时 options 还是空的（pending 组没有行），
    // 那是产品预期行为（不选陈旧行），但会让「↓ 移高亮」的断言测不到东西
    await waitFor(() => expect(within(container).getAllByRole('option')).toHaveLength(2))

    // 初始高亮是第一行 → ↓ 到第二行，aria-activedescendant 同步
    fireEvent.keyDown(box, { key: 'ArrowDown' })
    await waitFor(() =>
      expect(container.querySelector('[role="listbox"]')?.getAttribute('aria-activedescendant')).toBe(
        mentionOptionId('document', 1),
      ),
    )

    fireEvent.keyDown(box, { key: 'Enter' })
    await waitFor(() => expect(onPicked).toHaveBeenCalledWith('证据清单.pdf'))
    // 草稿里只留人能读的 `@名字 `，协议块不进来（否则一行正文被十几个字符打断）
    expect(box.value).toBe('@证据清单.pdf ')
    expect(container.querySelector('[role="listbox"]')).toBeNull()
    expect(box.getAttribute('aria-expanded')).toBe('false')
    await waitFor(() => expect(document.activeElement).toBe(box))
  })

  it('Esc 收起菜单，草稿原样不动（不误改、也不发送）', async () => {
    const { container, getByRole } = render(<Harness />)
    const box = getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '@起诉' } })
    await waitFor(() => expect(within(container).getAllByRole('option')).toHaveLength(2))
    fireEvent.keyDown(box, { key: 'Escape' })
    await waitFor(() => expect(container.querySelector('[role="listbox"]')).toBeNull())
    expect(box.value).toBe('@起诉')
  })

  it('鼠标点选行：焦点仍在 textarea（mousedown + preventDefault 的效果）', async () => {
    const onPicked = vi.fn()
    const { container, getByRole } = render(<Harness onPicked={onPicked} />)
    const box = getByRole('textbox') as HTMLTextAreaElement
    box.focus()
    fireEvent.change(box, { target: { value: '@起诉' } })
    await waitFor(() => expect(within(container).getAllByRole('option')).toHaveLength(2))

    const option = container.querySelector(`#${mentionOptionId('document', 0)}`) as HTMLElement
    expect(fireEvent.mouseDown(option)).toBe(false)
    await waitFor(() => expect(onPicked).toHaveBeenCalledWith('起诉状.pdf'))
    expect(box.value).toBe('@起诉状.pdf ')
    expect(document.activeElement).toBe(box)
  })
})
