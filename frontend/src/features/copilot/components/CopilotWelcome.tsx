/**
 * 空态欢迎页：渐变 orb 身份 + 可点的快捷任务卡（点击即发送）。
 *
 * 2026 AI 产品的空态不是「无数据」占位，而是第一次引导——把「它能干什么」
 * 变成可点的卡片，比一行「问点什么」的转化率高得多。建议项按业务范围
 * （案件/合同内 vs 全局助手）分两套，点击直接走 store.send（与回车同路径）。
 */

import { Briefcase, CalendarClock, FileText, FolderSearch, Inbox, ListTodo, Scale, Sparkles, Wallet, type LucideIcon } from 'lucide-react'

import { useCopilot } from '../store'

type Suggestion = { icon: LucideIcon; label: string; prompt: string }

const CONTEXT_SUGGESTIONS: Suggestion[] = [
  { icon: FolderSearch, label: '梳理材料', prompt: '请浏览绑定文件夹的全部材料，梳理案情要点与现有证据，给我一份摘要。' },
  { icon: ListTodo, label: '进展与下一步', prompt: '总结本案目前的进展，并列出下一步行动建议与对应的期限。' },
  { icon: Scale, label: '对方风险检索', prompt: '请检索各方当事人的公开涉诉与经营风险信息，重点看对方当事人。' },
  { icon: FileText, label: '文书起草思路', prompt: '结合现有材料，为下一步程序起草一份文书思路和提纲。' },
]

const GENERAL_SUGGESTIONS: Suggestion[] = [
  { icon: Briefcase, label: '我的案件', prompt: '列一下我名下的在办案件和各自的最新进展。' },
  { icon: CalendarClock, label: '到期期限', prompt: '近两周有哪些到期的期限？按紧急程度排一下。' },
  { icon: Wallet, label: '未收款汇总', prompt: '汇总一下未收款的合同和对应金额。' },
  { icon: Inbox, label: '今日待跟进', prompt: '我今天有什么该跟进的事？' },
]

export function CopilotWelcome() {
  const context = useCopilot((s) => s.context)
  const send = useCopilot((s) => s.send)
  const unit = context ? (context.origin === 'case' ? '本案' : '本委托') : null
  const suggestions = context ? CONTEXT_SUGGESTIONS : GENERAL_SUGGESTIONS

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-5 py-8 text-center">
      <div className="relative flex items-center justify-center">
        <div aria-hidden className="copilot-glow absolute h-24 w-24 rounded-full" />
        <span className="copilot-orb relative flex h-11 w-11 items-center justify-center rounded-[14px]">
          <Sparkles className="h-5 w-5 text-white" strokeWidth={2.2} />
        </span>
      </div>
      <div className="max-w-72">
        <p className="text-[14.5px] font-semibold text-foreground">你好，我是法穿SI超级助理</p>
        <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">
          {unit
            ? `已就位——${unit}的材料、日志、当事人与系统数据，直接问。`
            : '案件 · 合同 · 期限 · 财务，系统数据直接问，也支持把文件拖进来。'}
        </p>
      </div>
      <div className="grid w-full max-w-sm grid-cols-2 gap-1.5">
        {suggestions.map((s) => (
          <button
            key={s.label}
            type="button"
            className="group flex items-center gap-2.5 rounded-[12px] border border-border bg-card px-3 py-2.5 text-left shadow-sm transition-all hover:-translate-y-px hover:border-primary/25 hover:shadow-[0_6px_16px_-8px_rgba(24,24,27,0.2)]"
            onClick={() => void send(s.prompt)}
            aria-label={s.label}
            title={s.prompt}
          >
            <span className="copilot-orb flex h-7 w-7 flex-none items-center justify-center rounded-[8px] opacity-90 transition-opacity group-hover:opacity-100">
              <s.icon className="h-3.5 w-3.5 text-white" strokeWidth={2.2} />
            </span>
            <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-foreground">{s.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
