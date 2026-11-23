/**
 * 登录方式切换器。
 *
 * 只负责「选哪个方式」，不关心方式怎么渲染——渲染由 LoginPage 按 kind 派发。
 * 只有一个方式（账密）时不渲染，避免出现无意义的单选项。
 */
import { useRef, type KeyboardEvent } from 'react'
import type { NonEmptyArray } from '../login-methods'
import type { LoginMethod } from '../types'

interface Props {
  /** 调用方只在 methods.length > 1 时渲染本组件；非空由类型保证（循环取模才有意义） */
  methods: NonEmptyArray<LoginMethod>
  activeId: string
  onChange: (id: string) => void
}

export function LoginMethodSwitch({ methods, activeId, onChange }: Props) {
  /**
   * 语义是「从几个方式里选一个」，不是标签页：选完下面始终是同一个表单区，
   * 没有各自的 tabpanel / aria-controls 可指，所以用 radiogroup + radio
   * （aria-checked），而不是 tablist + tab（aria-selected）。后者会让读屏
   * 宣布「标签页 1/2」却找不到对应面板。
   *
   * 键盘按 ARIA radiogroup 规范：左右方向键把焦点移到相邻选项并选中（两端循环）；
   * roving tabindex 让 Tab 键在组内只停一次（停在选中项上）。
   */
  const items = useRef<Array<HTMLButtonElement | null>>([])

  const onArrowKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (step === 0) return
    event.preventDefault()
    const nextIndex = (index + step + methods.length) % methods.length
    const next = methods[nextIndex]
    if (!next) return
    onChange(next.id)
    // 焦点必须跟着选中项走：否则它会留在 tabIndex=-1 的旧选项上，下一次 Tab
    // 就从组外跳走，roving tabindex 的「组内只停一次」也就断了。
    items.current[nextIndex]?.focus()
  }

  return (
    <div role="radiogroup" aria-label="登录方式" className="fc-tabs">
      {methods.map((method, index) => {
        const active = method.id === activeId
        return (
          <button
            key={method.id}
            ref={(node) => {
              items.current[index] = node
            }}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            onKeyDown={(event) => onArrowKey(event, index)}
            onClick={() => onChange(method.id)}
            className={`fc-tab${active ? ' fc-tab--on' : ''}`}
          >
            {method.label}
          </button>
        )
      })}
    </div>
  )
}
