import { Link2 } from 'lucide-react'

import type { TaskOut } from '../types'

/**
 * 旁线（法院短信）识别任务的只读案件 chip。
 *
 * 与 CaseBindingSection 的「已绑定」态同款视觉，但**不提供换选入口**：
 * 法院短信第一轮已把案件/案件日志定死，日期候选的提醒会挂在那条案件日志上。
 * 如果在这里允许改绑，用户改完看到的还是原案件的日志锚点，日期就写到了
 * 自己以为之外的地方——宁可只读，也不能给出一个假的「已改绑」。
 */
export function PipelineBindingChip({ task }: { task: TaskOut }) {
  const caseName = task.binding?.case_name || ''
  const isBound = Boolean(task.binding?.success)

  if (!isBound) {
    // 管线模式理应已绑定；走到这里说明后端预绑定失效，明确告知而不是静默降级
    return (
      <div className="rounded-[10px] border border-dashed border-status-yellow/50 bg-status-yellow-bg/40 px-3 py-2 text-[11.5px] leading-relaxed text-muted-foreground">
        这条识别任务没有关联到案件（法院短信侧的绑定可能已失效），确认日期会创建独立提醒，不会写进任何案件日志。
      </div>
    )
  }

  return (
    <div className="flex animate-in fade-in slide-in-from-bottom-1 duration-300 items-center gap-2 rounded-[10px] border border-status-green/40 bg-status-green-bg px-3 py-2">
      <Link2 className="h-3.5 w-3.5 flex-none text-status-green" />
      <span className="min-w-0 flex-1 text-[12.5px] font-semibold">
        已由法院短信绑定：{caseName || `案件 ${task.binding?.case_id ?? ''}`}
      </span>
      <span className="flex-none text-[10.5px] text-muted-foreground">日期将写入该案件日志</span>
    </div>
  )
}
