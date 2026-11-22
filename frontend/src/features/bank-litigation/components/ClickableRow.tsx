/**
 * 可点击的清单行（`<ul>` 里的 `<li>`）。
 *
 * ═══ 为什么需要它 ═══
 * 这一屏里「整行点开抽屉」的行很多（签字核对 / 金额差异 / 归案邮件 / 缺件通知…）。
 * 原先每处都写成 `<li onClick className="… cursor-pointer …">`：
 * 鼠标能点，但键盘 Tab 不到、回车不触发、屏幕阅读器读不出「这是可点的」。
 * 鼠标路径不变，这里只补键盘通道与角色。
 *
 * ═══ 用法约束 ═══
 * 1. 只用在 `<ul>` / `<ol>` 的直接子元素位置（渲染出来是 `<li>`）。
 * 2. 行内如果有自己的按钮/勾选框/下拉框，必须在那个控件上 `stopPropagation`，
 *    否则点它等于点整行（本组件的 Enter/Space 也走同一个 `onClick`）；
 *    同时要传 `nestedControl`，原因见下面的参数说明。
 * 3. `className` 原样透传，行的排版（flex/grid、padding）与条件底色由调用方决定。
 */

import type { KeyboardEvent, ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function ClickableRow({
  onClick,
  className,
  children,
  nestedControl,
}: {
  onClick: () => void
  className?: string
  children: ReactNode
  /**
   * 行内自带按钮 / 勾选框 / 下拉框时传 `true`。
   *
   * 此时**不加** `role="button"`：ARIA 不允许 `button` 里套按钮，屏幕阅读器还会
   * 把行内控件的文字算进行按钮的可及名（测试里 `name: /指定归属/` 会同时命中行与按钮）。
   * 键盘通道（`tabIndex` + Enter/Space）照旧生效，行仍保持 `listitem` 语义。
   */
  nestedControl?: boolean
}) {
  /** Enter / Space 是按钮的标准触发键；其余键原样放行（不拦方向键/Tab） */
  function onKeyDown(e: KeyboardEvent<HTMLLIElement>) {
    if (e.key !== 'Enter' && e.key !== ' ') return
    // Space 的默认行为是滚页面，不拦掉就没法当「按下」用
    e.preventDefault()
    onClick()
  }

  return (
    <li
      role={nestedControl ? undefined : 'button'}
      tabIndex={0}
      onClick={onClick}
      onKeyDown={onKeyDown}
      className={cn('cursor-pointer transition-colors hover:bg-secondary/40', className)}
    >
      {children}
    </li>
  )
}
