import { useRef, useState } from 'react'

/**
 * 行内新建 / 重命名输入框。
 *
 * **为什么不只是 Enter 确认**：早先失焦即取消，触屏上没有 Enter 可依赖，点一下
 * 别处（甚至只是滚动一下）刚敲的名字就没了；鼠标用户也常点偏。现在三件事都能收：
 * - Enter / ✓：提交
 * - Esc / ✕：取消
 * - 失焦：**内容有变就提交**，没变或为空才取消（点别处不该白敲一遍）
 *
 * 提交是幂等的：✓ 按下会让输入框先失焦，两条路径同时触发也只执行一次。
 */
export function EntryInput({
  initial = '',
  placeholder,
  onConfirm,
  onCancel,
}: {
  initial?: string
  placeholder: string
  onConfirm: (name: string) => void
  onCancel: () => void
}) {
  const [v, setV] = useState(initial)
  /** 只收一次尾：blur 与按钮点击会先后到达 */
  const doneRef = useRef(false)
  const finish = (fn: () => void) => {
    if (doneRef.current) return
    doneRef.current = true
    fn()
  }
  const commit = () => {
    const name = v.trim()
    if (name && name !== initial) finish(() => onConfirm(name))
    else finish(onCancel)
  }
  const cancel = () => finish(onCancel)

  return (
    <div className="flex items-center gap-1">
      <input
        autoFocus
        value={v}
        placeholder={placeholder}
        onChange={(e) => setV(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
          else if (e.key === 'Escape') cancel()
        }}
        onClick={(e) => e.stopPropagation()}
        className="min-w-0 flex-1 rounded-[6px] border border-input bg-background px-2 py-1 text-[12.5px] text-secondary-foreground outline-none focus:border-foreground/40"
      />
      {/* onPointerDown + preventDefault：不让按钮抢焦点，避免「先 blur 提交」把
          「取消」变成「提交」 */}
      <button
        type="button"
        aria-label="确认"
        title="确认（Enter）"
        onPointerDown={(e) => {
          e.preventDefault()
          commit()
        }}
        className="grid size-5 flex-none place-items-center rounded-[5px] text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        ✓
      </button>
      <button
        type="button"
        aria-label="取消"
        title="取消（Esc）"
        onPointerDown={(e) => {
          e.preventDefault()
          cancel()
        }}
        className="grid size-5 flex-none place-items-center rounded-[5px] text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        ✕
      </button>
    </div>
  )
}
