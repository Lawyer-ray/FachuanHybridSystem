// @vitest-environment jsdom
/**
 * InboxRowSkeleton（收件箱骨架行）单测（jsdom）。
 *
 * 真行 InboxRowItem 要拉附件预览链路（pdf.js / 附件字节），在 jsdom 里渲染代价高；
 * 这里只钉骨架自己必须成立的两条：行数与**结构类**（决定行高，见组件头注释的
 * 算术），以及「占位块全是装饰、没有任何可读文本」。
 *
 * 结构类这一串是 InboxRowItem `<li>` 的结构部分（flex / 对齐 / 内边距）。
 * 哪天真行把它改了，这条用例会红——提醒同改 `INBOX_ROW_SHELL`，否则
 * 加载完成那一下列表会跳。
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { InboxRowSkeleton } from './InboxRowSkeleton'

/** 与 InboxRowItem 的 `<li>` 同源的结构类：flex / 对齐 / 间距 / 内边距 */
const EXPECTED_ROW_SHELL = 'flex w-full items-start gap-3 px-4 py-3'

describe('InboxRowSkeleton', () => {
  it('按 count 渲染占位行，行容器用与真行一致的结构类', () => {
    const { container } = render(<InboxRowSkeleton count={8} />)
    const rows = Array.from(container.querySelectorAll('[data-skeleton-row="inbox"]'))
    expect(rows).toHaveLength(8)
    for (const row of rows) {
      expect(row.className).toBe(EXPECTED_ROW_SHELL)
    }
  })

  it('分隔线用真列表同一个类（不然骨架是连成一片的灰）', () => {
    const { container } = render(<InboxRowSkeleton count={2} />)
    const list = container.firstElementChild as HTMLElement
    expect(list.tagName).toBe('UL')
    expect(list.className).toContain('divide-y')
    expect(list.className).toContain('divide-border/70')
  })

  it('占位块全是装饰：整块没有任何可读文本', () => {
    const { container } = render(<InboxRowSkeleton count={2} />)
    expect(container.textContent).toBe('')
    // 每行 6 块：图标位 / 主题 / 来源徽章 / 副标题 / 时间 / 附件胶囊
    const blocks = container.querySelectorAll('[data-slot="skeleton"]')
    expect(blocks).toHaveLength(2 * 6)
    for (const block of blocks) {
      expect(block.getAttribute('aria-hidden')).toBe('true')
    }
  })
})
