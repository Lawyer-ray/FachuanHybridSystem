import { Copy } from 'lucide-react'
import { toast } from 'sonner'

import { copyText } from '@/lib/clipboard'
import { BADGE_TONE_CLS, type Tone } from '@/lib/tone'
import { cn } from '@/lib/utils'

import type { DraftAssessResult, MissingSeverity, ReadinessMissingItem } from '../types'

/** 结论 → 语义色（红=出不了 / 黄=能出但会留空 / 绿=齐了 / 灰=没判断出来） */
const VERDICT_TONE: Record<DraftAssessResult['verdict'], Tone> = {
  blocked: 'red',
  draftable_with_gaps: 'yellow',
  ready: 'green',
  unknown: 'neutral',
}

/** 缺口分组：顺序就是处理顺序（先补挡住立案的，再谈金额与抗辩） */
const SEVERITY_GROUPS: { key: MissingSeverity; title: string; textCls: string }[] = [
  { key: 'blocking', title: '必须补', textCls: 'text-status-red' },
  { key: 'amount', title: '影响金额', textCls: 'text-status-yellow' },
  { key: 'defense', title: '影响胜诉', textCls: 'text-status-blue' },
]

/** 结论 → 一句话人话。数字口径与后端闸门对齐，见各分支注释。 */
function verdictSentence(result: DraftAssessResult): string {
  switch (result.verdict) {
    case 'blocked':
      // 后端给的就是「挡住起草的那几项」；为空时退回收 severity=blocking 的条数，别显示「缺 0 项」
      return `现在还不能出，缺 ${result.blocking.length || countBlocking(result)} 项`
    case 'draftable_with_gaps':
      // 后端闸门是「matrix 里 missing ≥3」，这个数就是成稿里会留空的位置数；
      // 万一口径变了算出 0，用缺口条数兜底——「有 0 处会留空」比不显示更误导
      return `能出，但有 ${countMissingRequirement(result) || result.missing_materials.length} 处会在成稿里留空`
    case 'ready':
      return '材料齐，可以直接出'
    default:
      // verdict 在后端是 str 不是枚举：出现没见过的值按「没判断出来」处理，绝不假装材料齐
      return '判断没跑成功'
  }
}

function countBlocking(result: DraftAssessResult): number {
  return result.missing_materials.filter((item) => item.severity === 'blocking').length
}

function countMissingRequirement(result: DraftAssessResult): number {
  return result.matrix.filter((row) => row.status === 'missing').length
}

/** 「向谁要 · 形式」这一行：两个字段都可能为空，空的那半不渲染 */
function askingLine(item: ReadinessMissingItem): string {
  return [item.from_whom ? `向${item.from_whom}要` : '', item.form ? `形式：${item.form}` : '']
    .filter(Boolean)
    .join(' · ')
}

/** 复制出去的纯文本：标题（结论）+ 分组 + 条目，不带任何字段名与标记语言 */
function checklistText(result: DraftAssessResult): string {
  const lines = [`立案前判断：${verdictSentence(result)}`]
  for (const group of SEVERITY_GROUPS) {
    const rows = result.missing_materials.filter((item) => item.severity === group.key)
    if (rows.length === 0) continue
    lines.push('', `【${group.title}】`)
    for (const row of rows) {
      const meta = askingLine(row)
      lines.push(`- ${row.item}${row.why ? `：${row.why}` : ''}${meta ? `（${meta}）` : ''}`)
    }
  }
  if (result.questions.length > 0) {
    lines.push('', '【要核实的问题】')
    for (const q of result.questions) {
      const meta = [q.to ? `问${q.to}` : '', q.why].filter(Boolean).join(' · ')
      lines.push(`- ${q.question}${meta ? `（${meta}）` : ''}`)
    }
  }
  if (result.warnings.length > 0) {
    lines.push('', `【${result.verdict === 'unknown' ? '没跑成功的原因' : '判断时的提醒'}】`)
    for (const warning of result.warnings) lines.push(`- ${warning}`)
  }
  return lines.join('\n')
}

/**
 * 立案前判断面板：结论一句话 + 缺口按「必须补 / 影响金额 / 影响胜诉」分组 + 要核实的问题。
 *
 * **为什么不展示 `verdict` / `severity` / `matrix` 这些字段名**：律师要的是「现在能不能出、
 * 缺什么、找谁要」，字段名和要件矩阵是我们排查用的，摆在界面上只会稀释结论。
 *
 * **为什么复制按钮给的是整份清单而不是单条**：律师下一步动作是把清单发给委托人/助理，
 * 复制出来必须自带标题与分组，否则对方收到一串没有上下文的条目。
 */
export function ReadinessPanel({ result }: { result: DraftAssessResult }) {
  // 结论值由后端仲裁枚举约束；万一将来多一档，按中性色渲染，不报错也不染成成功的绿色
  const tone = VERDICT_TONE[result.verdict] ?? 'neutral'

  const copyChecklist = () => {
    void copyText(checklistText(result)).then((ok) => {
      if (ok) toast.success('已复制材料清单')
      else toast.error('复制失败，请手动选中清单文字')
    })
  }

  return (
    <div className="flex flex-col gap-3" data-testid="readiness-panel">
      <div className="flex items-start gap-2">
        <p
          data-testid="readiness-verdict"
          className={cn(
            'flex-1 rounded-[8px] border px-3 py-2 text-[13px] leading-[1.6] font-[620]',
            BADGE_TONE_CLS[tone],
          )}
        >
          {verdictSentence(result)}
        </p>
        <button
          type="button"
          data-testid="readiness-copy"
          title="复制「结论 + 分组 + 条目」纯文本"
          className="inline-flex flex-none items-center gap-1 rounded-[6px] border border-border px-2 py-1.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={copyChecklist}
        >
          <Copy className="size-3" />
          复制清单
        </button>
      </div>

      {result.warnings.length > 0 && (
        <div>
          <h4 className="text-[12px] font-semibold">
            {result.verdict === 'unknown' ? '没跑成功的原因' : '判断时的提醒'}
          </h4>
          <ul className="mt-1 flex flex-col gap-1 text-[11.5px] leading-[1.7] text-muted-foreground">
            {result.warnings.map((warning, i) => (
              <li key={`${warning}-${i}`} className="break-words">
                · {warning}
              </li>
            ))}
          </ul>
        </div>
      )}

      {SEVERITY_GROUPS.map((group) => {
        const rows = result.missing_materials.filter((item) => item.severity === group.key)
        if (rows.length === 0) return null
        return (
          <section key={group.key} aria-label={group.title} className="flex flex-col gap-1.5">
            <h4 className={cn('text-[12px] font-semibold', group.textCls)}>
              {group.title} · {rows.length}
            </h4>
            <ul className="flex flex-col gap-1.5">
              {rows.map((row, i) => {
                const meta = askingLine(row)
                return (
                  <li
                    key={`${row.item}-${i}`}
                    className="rounded-[7px] border border-border-light px-2.5 py-2 text-[12.5px] leading-[1.7]"
                  >
                    <div className="font-medium break-words">{row.item}</div>
                    {row.why && <p className="mt-0.5 text-[11.5px] text-muted-foreground">{row.why}</p>}
                    {meta && <p className="mt-0.5 text-[11.5px] text-muted-foreground">{meta}</p>}
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}

      {result.questions.length > 0 && (
        <section aria-label="要核实的问题" className="flex flex-col gap-1.5">
          <h4 className="text-[12px] font-semibold">要核实的问题 · {result.questions.length}</h4>
          <ul className="flex flex-col gap-1.5">
            {result.questions.map((q, i) => {
              const meta = [q.to ? `问${q.to}` : '', q.why].filter(Boolean).join(' · ')
              return (
                <li key={`${q.question}-${i}`} className="rounded-[7px] border border-border-light px-2.5 py-2">
                  <div className="text-[12.5px] leading-[1.7] break-words">{q.question}</div>
                  {meta && <p className="mt-0.5 text-[11.5px] leading-[1.7] text-muted-foreground">{meta}</p>}
                </li>
              )
            })}
          </ul>
        </section>
      )}
    </div>
  )
}
