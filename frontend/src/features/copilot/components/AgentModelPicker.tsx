/**
 * 单栏的模型下拉（多选菜单里每一行右侧那一个）。
 *
 * ## 为什么不是 AnswerAgentMenu 里再来一枚独立菜单
 *
 * 后端选择在 AnswerAgentMenu 里只有一张清单、一种形状（勾选框 + 名字）；模型
 * 只是选中那一行的属性，所以是卡在行右侧的一枚窄 chip（`[kimi-2.6 ▾]`）——再
 * 开一张「宽条 + 两行说明 + 列表常驻」的单选下拉当菜单，四行并排时就会吃掉
 * 勾选框与名字的位置。
 *
 * ## 清单为空 = 不渲染
 *
 * `models` 为空（后端还没上线该字段 / 平台没配可选模型）时**整枚下拉消失**，
 * 后端清单菜单照常可用——多选 agent 本身不该因为「选不了模型」而失效。这也是
 * 唯一的降级路径：不做「禁用状态的空下拉」，那只会让人以为功能坏了。
 */

import { useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'

/** 触发按钮：窄、单行、截断（模型名可以很长） */
const TRIGGER_CLASS =
  'flex h-6 max-w-[132px] flex-none items-center gap-0.5 rounded-[6px] border border-border px-1 text-[11px] transition-colors'

export function AgentModelPicker({
  models,
  value,
  defaultModel,
  label,
  disabled,
  disabledHint,
  onChange,
}: {
  /** 可选模型清单（后端 `models` 字段；空数组 = 不渲染本控件） */
  models: string[]
  /** 当前指定的模型；空串 = 未指定，用平台默认 */
  value: string
  /** 未指定时预填的模型（后端 `default_model`；未知时为空串） */
  defaultModel: string
  /** 这一行是谁（无障碍名里带上，四个下拉在一屏里才不会互相认错） */
  label: string
  /** 未勾选该行：选了模型也没意义，置灰 */
  disabled: boolean
  /** 置灰原因（悬停提示） */
  disabledHint: string
  onChange: (model: string) => void
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  // 点击别处收起。菜单本身没有遮罩（它浮在输入框上方，加遮罩会挡住正在写的
  // 正文），所以收起只能靠这个监听。
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  if (models.length === 0) return null

  // 律师点过的那次选择优先；否则显示后端给的默认模型（README 里「默认预填
  // default_model」）。都没有时写「默认模型」——比空白清楚「这里可以点」。
  const shown = value || defaultModel
  const triggerText = shown || '默认模型'

  return (
    <div ref={rootRef} className="relative flex-none" data-testid={`model-picker-${label}`}>
      <button
        type="button"
        className={`${TRIGGER_CLASS} ${
          disabled
            ? 'cursor-not-allowed border-border/60 text-muted-foreground opacity-55'
            : 'border-border text-muted-foreground hover:bg-secondary hover:text-foreground'
        }`}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label} 使用的模型：${triggerText}`}
        title={disabled ? disabledHint : `指定 ${label} 本轮使用的模型（当前：${triggerText}）`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="truncate">{triggerText}</span>
        <ChevronDown className="h-3 w-3 flex-none" aria-hidden />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label={`${label} 的模型`}
          className="absolute top-full right-0 z-[130] mt-0.5 max-h-56 w-44 overflow-y-auto rounded-[10px] border border-border bg-popover p-1 shadow-md"
        >
          {models.map((model) => (
            <button
              key={model}
              type="button"
              role="option"
              aria-selected={model === shown}
              // 再点已选项 = 撤销指定（回到平台默认）。所以已选项不能 disabled：
              // 一旦禁用，用户就没有「改回默认」的入口了。
              className={`block w-full rounded-[7px] px-1.5 py-1 text-left text-[11.5px] transition-colors hover:bg-secondary ${
                model === shown ? 'bg-secondary/60 font-medium text-foreground' : 'text-muted-foreground'
              }`}
              onClick={() => {
                onChange(model)
                setOpen(false)
              }}
            >
              <span className="block truncate" title={model}>
                {model}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
