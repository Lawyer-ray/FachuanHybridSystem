/**
 * 登录方式切换器。
 *
 * 只负责「选哪个方式」，不关心方式怎么渲染——渲染由 LoginPage 按 kind 派发。
 * 只有一个方式（账密）时不渲染，避免出现无意义的单选项。
 */
import type { LoginMethod } from '../login-methods'

interface Props {
  methods: LoginMethod[]
  activeId: string
  onChange: (id: string) => void
}

export function LoginMethodSwitch({ methods, activeId, onChange }: Props) {
  return (
    <div role="tablist" aria-label="登录方式" className="mb-5 flex gap-1 rounded-[10px] bg-secondary p-1">
      {methods.map((method) => {
        const active = method.id === activeId
        return (
          <button
            key={method.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(method.id)}
            className={`flex-1 cursor-pointer rounded-[7px] px-2 py-[7px] text-[12.5px] font-medium whitespace-nowrap transition-colors ${
              active ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {method.label}
          </button>
        )
      })}
    </div>
  )
}
