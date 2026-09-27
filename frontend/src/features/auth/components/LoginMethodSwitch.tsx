/**
 * 登录方式切换器。
 *
 * 只负责「选哪个方式」，不关心方式怎么渲染——渲染由 LoginPage 按 kind 派发。
 * 只有一个方式（账密）时不渲染，避免出现无意义的单选项。
 */
import type { KeyboardEvent } from 'react'
import type { LoginMethod } from '../login-methods'

interface Props {
  methods: LoginMethod[]
  activeId: string
  onChange: (id: string) => void
}

export function LoginMethodSwitch({ methods, activeId, onChange }: Props) {
  /**
   * ARIA tabs 模式：左右方向键循环切换。
   *
   * 刻意不动 tabIndex——保留每个 tab 都能被 Tab 键逐个聚焦的能力，
   * 比 roving tabindex 更宽容（键盘用户两条路径都能用）。
   */
  const onArrowKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (step === 0) return
    event.preventDefault()
    onChange(methods[(index + step + methods.length) % methods.length].id)
  }

  return (
    <div role="tablist" aria-label="登录方式" className="fc-tabs">
      {methods.map((method, index) => {
        const active = method.id === activeId
        return (
          <button
            key={method.id}
            type="button"
            role="tab"
            aria-selected={active}
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
