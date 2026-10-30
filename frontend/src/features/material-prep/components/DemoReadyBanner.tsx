import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { ArrowRight, Sparkles, X } from 'lucide-react'

import { createApiClient } from '@/lib/api'
import { cn } from '@/lib/utils'

/**
 * 演示就绪提示条 —— 演示按钮铺完数据后浮在页面顶部。
 *
 * ═══ 为什么是提示条而不是自动跳转 ═══
 * 演示按钮刚做完两件事：整包 PDF 已进收件箱、案件已建好。
 * 这时**不该自动跳到案件页** —— 律师的第一动作应该是「把刚进来的材料包拆开」，
 * 而分段操作就在当前页。自动跳走会打断这个顺序。
 *
 * 所以这里只做一件事：告诉用户「案件也已经建好了，随时可以去」，
 * 给一个跳转入口，不替他做决定。
 */
export function DemoReadyBanner({ caseId }: { caseId: number | null }) {
  const [name, setName] = useState<string | null>(null)
  const [closed, setClosed] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (caseId == null) {
      setName(null)
      return
    }
    let alive = true
    const api = createApiClient({ prefix: '/api/v1/cases' })
    api
      .get(`cases/${caseId}`)
      .json<{ name?: string }>()
      .then((c) => {
        if (alive) setName(c?.name ?? `案件 #${caseId}`)
      })
      .catch(() => {
        if (alive) setName(`案件 #${caseId}`)
      })
    return () => {
      alive = false
    }
  }, [caseId])

  if (caseId == null || closed || name == null) return null

  return (
    <div
      className={cn(
        'mb-3 flex items-center gap-2 rounded-[9px] border border-status-blue/40 bg-status-blue-bg px-3 py-2',
      )}
    >
      <Sparkles className="size-3.5 flex-none text-status-blue" />
      <span className="min-w-0 flex-1 truncate text-[12px] text-status-blue" title={name}>
        演示数据已就绪：材料包已进「待处理」，案件「{name}」也已建好
      </span>
      <button
        type="button"
        onClick={() => void navigate(`/bank-litigation/${caseId}`)}
        className="flex flex-none items-center gap-1 rounded-[6px] bg-status-blue px-2 py-1 text-[11.5px] font-medium text-white transition-opacity hover:opacity-90"
      >
        进入立案工作台
        <ArrowRight className="size-3" />
      </button>
      <button
        type="button"
        onClick={() => setClosed(true)}
        aria-label="关闭提示"
        className="flex size-5 flex-none items-center justify-center rounded-[5px] text-status-blue/70 hover:bg-status-blue/10 hover:text-status-blue"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}
