/**
 * 策展对话框右栏：规则类型 + 改写框 + 闸门提示（原样提升 / 含敏感信息 / 律所层确认）。
 *
 * 从 MemoryPromoteDialog 拆出（后者超软红线）。改写是**必填且不得与来源原文相同**：
 * 这一条既完成脱敏，也把「具体案件事实」挡在跨人可见层之外。
 */

import { AlertTriangle, ShieldAlert } from 'lucide-react'

import type { MemoryKind } from '../../memory-api'
import { Textarea } from '@/components/ui/textarea'
import { KIND_LABEL, LAW_FIRM_KINDS, MAX_RULE_CHARS, TEAM_KINDS } from './labels'

export function PromoteRuleEditor({
  target,
  kind,
  onKindChange,
  content,
  onContentChange,
  sourceCount,
  sameAsSource,
  draftPii,
  firmAck,
  onFirmAckChange,
}: {
  target: 'team' | 'law_firm'
  /** 已修正过的类型（律所层非法类型在父层已拉回惯例，见 MemoryPromoteDialog） */
  kind: MemoryKind
  onKindChange: (kind: MemoryKind) => void
  content: string
  onContentChange: (text: string) => void
  /** 已选来源条数 */
  sourceCount: number
  /** 与来源原文相同（归一化后比对） */
  sameAsSource: boolean
  /** 改写框命中的敏感模式名 */
  draftPii: string[]
  firmAck: boolean
  onFirmAckChange: (ack: boolean) => void
}) {
  const kindOptions = target === 'law_firm' ? LAW_FIRM_KINDS : TEAM_KINDS
  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-2 flex flex-none items-center gap-1.5">
        <select
          aria-label="规则类型"
          value={kind}
          onChange={(e) => onKindChange(e.target.value as MemoryKind)}
          className="h-7 rounded-[7px] border border-border bg-card px-2 text-[11px]"
        >
          {kindOptions.map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
        <span className="text-[11px] text-muted-foreground">
          {content.trim().length}/{MAX_RULE_CHARS}
        </span>
      </div>

      <Textarea
        aria-label="改写后的规则"
        value={content}
        onChange={(e) => onContentChange(e.target.value)}
        placeholder="例如：劳动争议类案件回复客户时，先确认是否已过仲裁时效，再谈分期方案"
        className="min-h-[140px] flex-1 resize-none text-[13px]"
      />

      <div className="mt-2 flex-none space-y-1.5">
        {sourceCount > 0 && (
          <p className="text-[11px] leading-relaxed text-muted-foreground">来源：{sourceCount} 条成员记忆</p>
        )}
        {sameAsSource && (
          <p className="flex items-start gap-1 text-[11px] leading-relaxed text-amber-600 dark:text-amber-500">
            <AlertTriangle className="mt-0.5 h-3 w-3 flex-none" />
            与来源原文相同——请提炼成适用范围更广的规则
          </p>
        )}
        {draftPii.length > 0 && (
          <p className="flex items-start gap-1 text-[11px] leading-relaxed text-destructive">
            <ShieldAlert className="mt-0.5 h-3 w-3 flex-none" />
            含 {draftPii.join('、')}，请去掉具体信息
          </p>
        )}
        {target === 'law_firm' && (
          <>
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              律所层只接受「惯例」或「偏好」——具体事实不属于全所规范。
            </p>
            <label className="flex cursor-pointer items-start gap-1.5 text-[11px] leading-relaxed text-foreground">
              <input
                type="checkbox"
                className="mt-0.5 h-3 w-3 flex-none"
                checked={firmAck}
                onChange={(e) => onFirmAckChange(e.target.checked)}
              />
              <span>我确认：这条规则将对**全所所有律师**的 AI 助手生效</span>
            </label>
          </>
        )}
      </div>
    </div>
  )
}
