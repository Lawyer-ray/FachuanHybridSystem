/**
 * 单个关键字段的校对：原文 3 行上下文 + 置信度 + 可手工改正
 *
 * 「AI 说合同写的是 4.90%」—— 律师要确认的不是这个数，而是**这个数在原件哪一句里**。
 * 所以这里给的是上下文 3 行（命中行高亮）、抽取口径、以及沿用的置信度；
 * 认错了就地改，改动记进字段修订历史，不回写原件。
 */

import { useState } from 'react'

import { DEMO_UNDERSTAND_FIELDS, DEMO_X1_FIELD_LOCATES } from '../demo-data'
import type { X1FieldLocateRow } from '../demo-data'
import { ActionButton, InsetBlock, KeyValueRow, Pill } from '../ui'
import { cn } from '@/lib/utils'
import { DetailDrawer } from './DetailDrawer'

export function FieldDrawer({
  picked,
  onClose,
  overrides,
  onSave,
}: {
  picked: { doc: string; field: string } | null
  onClose: () => void
  overrides: Record<string, string>
  onSave: (key: string, value: string) => void
}) {
  const field = picked ? DEMO_UNDERSTAND_FIELDS.find((f) => f.doc === picked.doc && f.field === picked.field) : null
  const locate: X1FieldLocateRow | null = picked
    ? (DEMO_X1_FIELD_LOCATES.find((l) => l.doc === picked.doc && l.field === picked.field) ?? null)
    : null
  const key = picked ? `${picked.doc}-${picked.field}` : ''
  const [draft, setDraft] = useState('')

  return (
    <DetailDrawer
      open={field != null}
      onClose={onClose}
      width={480}
      title={picked ? `${picked.doc} · ${picked.field}` : ''}
      subtitle={locate ? `原文位置 P${locate.page}` : '无原文定位样本'}
      badge={
        field ? (
          <Pill tone={field.confidence >= 0.95 ? 'green' : 'yellow'}>{(field.confidence * 100).toFixed(0)}%</Pill>
        ) : null
      }
      footer={
        field ? (
          <>
            <ActionButton
              dark
              onClick={() => {
                if (draft.trim()) onSave(key, draft.trim())
                onClose()
              }}
            >
              保存修正
            </ActionButton>
            <ActionButton onClick={onClose}>保持原值</ActionButton>
          </>
        ) : null
      }
    >
      {field ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="抽取值">{overrides[key] ?? field.value}</KeyValueRow>
            <KeyValueRow label="置信度">
              <span className={field.confidence >= 0.95 ? 'text-status-green' : 'text-status-yellow'}>
                {(field.confidence * 100).toFixed(0)}%
              </span>
            </KeyValueRow>
            <KeyValueRow label="来源">{field.source}</KeyValueRow>
          </dl>

          {locate ? (
            <InsetBlock className="bg-secondary/25">
              <div className="text-[10px] text-muted-foreground">原文上下文（命中行在中间）</div>
              <div className="mt-1 flex flex-col gap-[1px] font-mono text-[10.5px] leading-[1.7]">
                {locate.context.map((line, i) => (
                  <span
                    key={i}
                    className={cn(
                      'rounded-[3px] px-1',
                      i === 1 ? 'bg-status-yellow-bg/70 text-foreground' : 'text-muted-foreground',
                    )}
                  >
                    {i === 1 && locate.hit ? highlight(line, locate.hit) : line}
                  </span>
                ))}
              </div>
              <div className="mt-1.5 text-[10px] leading-[1.6] text-muted-foreground">抽取口径：{locate.rule}</div>
            </InsetBlock>
          ) : null}

          <div>
            <label htmlFor="x1-field-fix" className="text-[10.5px] text-muted-foreground">
              手工改正（会记进字段修订历史）
            </label>
            <input
              id="x1-field-fix"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={overrides[key] ?? field.value}
              className="mt-1 h-[30px] w-full rounded-[7px] border border-border bg-background px-2 text-[12px] outline-none focus:border-input"
            />
            {overrides[key] ? <div className="mt-1 text-[10px] text-status-green">已改为「{overrides[key]}」</div> : null}
          </div>
        </div>
      ) : null}
    </DetailDrawer>
  )
}

/** 把命中片段标出来（纯文本匹配，不拼 HTML） */
function highlight(line: string, hit: string): React.ReactNode {
  const at = line.indexOf(hit)
  if (at < 0) return line
  return (
    <>
      {line.slice(0, at)}
      <mark className="rounded-[2px] bg-status-yellow/40 px-[1px] text-foreground">{hit}</mark>
      {line.slice(at + hit.length)}
    </>
  )
}
