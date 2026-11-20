/**
 * 正文角标：把 `[Kn]` 渲染成一个可点的上标。
 *
 * 为什么单独成组件：句子里的来源必须**贴着那句话**，不能集中堆在回答末尾
 * （律师读的是结论，翻到末尾再去找对应项等于让他重新对一遍）。所以角标是
 * 行内元素，卡片从角标位置弹出（见 CitationPopover 的定位理由）。
 *
 * 键盘可达性是硬要求，不是加分项：
 * - 触发器是真 `<button>`（Tab 能到、有 aria-label 报出来源名）；
 * - `Enter` / `Space` 显式打开——jsdom 不会像浏览器那样把按键合成 click，
 *   只写 onClick 的组件在自动化里永远是「点不开」，也说明它在某些输入法/
 *   辅助技术下并不可靠；
 * - `Esc` 关闭并把焦点**还给角标**，否则焦点掉回 body，键盘用户要从正文
 *   第一个字重新 Tab 过几十个角标。
 */

import { memo, useCallback, useRef, useState } from 'react'

import type { CitationRef } from '../../domain/knowledge'
import { CitationPopover } from '../CitationPopover'

export const CitationMark = memo(function CitationMark({
  citeNo,
  citation,
}: {
  /** 与正文 `[Kn]` 一致的编号（后端分配，前端不重编） */
  citeNo: number
  citation: CitationRef
}) {
  const [open, setOpen] = useState(false)
  const anchorRef = useRef<HTMLButtonElement>(null)

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false)
    if (restoreFocus) anchorRef.current?.focus()
  }, [])

  return (
    <span className="relative inline-block">
      <button
        ref={anchorRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`查看来源 ${citeNo}：${citation.name}`}
        title={`来源：${citation.name}`}
        // 只负责打开，不做 toggle：Enter 会同时触发 keydown 与浏览器合成的
        // click，toggle 语义下会「打开又立刻关掉」，点开等于没反应
        onClick={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setOpen(true)
          }
        }}
        className="mx-0.5 inline-flex -translate-y-[0.15em] cursor-pointer items-center rounded-[4px] bg-secondary px-1 text-[10px] leading-[1.5] font-medium align-baseline text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        K{citeNo}
      </button>
      <CitationPopover citation={citation} open={open} anchorRef={anchorRef} onClose={close} />
    </span>
  )
})
