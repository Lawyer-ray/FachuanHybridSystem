/**
 * 审批卡里的工具参数详情：按 `shortToolName(approval.toolName)` 分发到特化渲染。
 *
 * 为什么必须特化：后端全链路（`AgentApproval.tool_args` → SSE `approval_request` →
 * 离线 `/approvals/pending`）都**不截断**参数，唯一截断点是
 * `domain/approval.previewToolArgs`（默认 160 字）。`save_user_skill` 的正文动辄几 KB，
 * 律师若只看到 160 字预览就点「同意」，等于批准一段自己没看过的指令——审批卡存在的
 * 意义就没了。所以这里读**原始** `toolArgs` 渲染全文，只有兜底分支才用预览串。
 *
 * 行数约束：`ApprovalCard` 贴着 200 行量级，特化渲染全部放这里，卡片只做分发调用。
 */

import { ShieldAlert } from 'lucide-react'

import { previewToolArgs, shortToolName } from '../domain'

/**
 * `save_user_skill` 的工具短名。
 *
 * `ApprovalCard` 用同一条常量决定「同意」按钮是否被「已阅读全文」勾选锁住——
 * 两处写各自的字面量迟早漂移，而漂移的后果是卡片放行了一段没人读完的指令。
 */
export const SAVE_USER_SKILL_TOOL = 'save_user_skill'

const DELETE_USER_SKILL_TOOL = 'delete_user_skill'
const SUBMIT_SKILL_REVIEW_TOOL = 'submit_skill_for_review'

/** 提交审批的目标作用域人话（未知值原样显示，别把服务端新枚举吃掉） */
const SCOPE_LABELS: Record<string, string> = {
  firm: '所内（全所律师）',
  team: '团队',
}

export interface ApprovalToolDetailProps {
  /** `approval.toolName` 原文（可能带 `mcp__fachuan__` 前缀，统一在这里归一） */
  toolName: string
  /** `approval.toolArgs` 原始对象——**不是** `previewToolArgs` 的截断串 */
  toolArgs: Record<string, unknown>
  /** 仅 `save_user_skill` 用：全文已读勾选（受控，卡片据此解锁「同意」） */
  acknowledged?: boolean
  onAcknowledgedChange?: (acknowledged: boolean) => void
}

/** 取一个字符串参数：非字符串/缺失一律归空串（模型可能传数字或 null） */
function textArg(args: Record<string, unknown>, key: string): string {
  const value = args[key]
  return typeof value === 'string' ? value : ''
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-1.5">
      <span className="flex-none text-[11px] text-muted-foreground">{label}</span>
      <span className={`min-w-0 break-all text-[12px] text-foreground ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

function SaveUserSkillDetail({
  args,
  acknowledged,
  onAcknowledgedChange,
}: {
  args: Record<string, unknown>
  acknowledged: boolean
  onAcknowledgedChange?: (acknowledged: boolean) => void
}) {
  const title = textArg(args, 'title')
  const name = textArg(args, 'name')
  const description = textArg(args, 'description')
  const body = textArg(args, 'body')
  return (
    <div className="mt-1.5 space-y-1">
      <Field label="中文名" value={title || '（未填）'} />
      <Field label="命令名" value={name ? `/skill:${name}` : '（未填）'} mono />
      {description ? <Field label="说明" value={description} /> : null}
      {/* 风险提示必须比参数更醒目：这段指令此后会一直进模型上下文，而不是这一次生效 */}
      <p className="flex items-start gap-1 text-[11px] leading-relaxed text-amber-700 dark:text-amber-400">
        <ShieldAlert className="mt-px h-3 w-3 flex-none" aria-hidden />
        保存后，此后每轮对话都会带着这段指令（个人作用域）
      </p>
      {/* 全文原样渲染：滚动区 + 等宽 + 保留换行，目标是把几 KB 正文一字不落地摆出来 */}
      <div
        data-testid="approval-skill-body"
        className="max-h-[40vh] overflow-auto break-words whitespace-pre-wrap rounded-[6px] border border-border bg-background px-2 py-1.5 font-mono text-[11px] leading-relaxed text-foreground"
      >
        {body || '（正文为空）'}
      </div>
      <label className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-foreground">
        <input type="checkbox" checked={acknowledged} onChange={(e) => onAcknowledgedChange?.(e.target.checked)} />
        已阅读上述指令全文
      </label>
    </div>
  )
}

function SkillRefDetail({ action, args }: { action: string; args: Record<string, unknown> }) {
  const key = textArg(args, 'key')
  const isDelete = action === DELETE_USER_SKILL_TOOL
  const scope = textArg(args, 'target_scope')
  const scopeLabel = SCOPE_LABELS[scope] ?? scope
  return (
    <div className="mt-1.5 space-y-1">
      <Field label="技能" value={key || '（未给出 key）'} mono />
      {!isDelete && scopeLabel ? <Field label="提交到" value={scopeLabel} /> : null}
      {/* 两个写工具的后果完全不同：删除不可恢复、提交不是生效，必须说清 */}
      <p className="text-[11px] leading-relaxed text-destructive">
        {isDelete
          ? '同意后该技能立刻从技能索引消失，正文不可恢复；同名所内版（若有）会重新顶上来。'
          : `同意后该技能进入${scopeLabel || '所内/团队'}审批：审批通过前不生效，审批人能看到正文全文。`}
      </p>
    </div>
  )
}

function ArgsPreview({ args }: { args: Record<string, unknown> }) {
  const preview = previewToolArgs(args)
  if (!preview) return null
  return <p className="mt-1 font-mono text-[11px] break-all text-muted-foreground">{preview}</p>
}

export function ApprovalToolDetail({ toolName, toolArgs, acknowledged = false, onAcknowledgedChange }: ApprovalToolDetailProps) {
  const name = shortToolName(toolName)
  if (name === SAVE_USER_SKILL_TOOL) {
    return (
      <SaveUserSkillDetail args={toolArgs} acknowledged={acknowledged} onAcknowledgedChange={onAcknowledgedChange} />
    )
  }
  if (name === DELETE_USER_SKILL_TOOL || name === SUBMIT_SKILL_REVIEW_TOOL) {
    return <SkillRefDetail action={name} args={toolArgs} />
  }
  return <ArgsPreview args={toolArgs} />
}
