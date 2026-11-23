/**
 * ④ 文书 —— 委托合同条款逐条审核
 *
 * 自动填充只是**起点**：24 个字段里总有几项得律师自己定（特别授权最典型，
 * 授到什么程度直接决定能不能代签和解）。所以这里每一条都点得开、改得了，
 * 改过的打「已修改」，没填的整行泛黄提醒。
 *
 * 编辑态只在抽屉里：列表行上直接塞输入框会让这张表变成表单，
 * 一屏 8 条同时闪光标，看不出哪条是重点。
 */

import { useState } from 'react'
import { AlertTriangle, FileText, PencilLine } from 'lucide-react'

import { DEMO_CONTRACT_GEN, DEMO_CONTRACT_TERMS, type ContractTermRow } from '../demo-data'
import { pendingTermCount, type TermDraft } from './contract-terms'
import { ClickableRow } from '../ClickableRow'
import { ActionButton, InsetBlock, Pill, SectionTitle, WorkCard } from '../ui'
import { cn } from '@/lib/utils'
import { DetailDrawer } from '@/components/shared/DetailDrawer'

export function ContractTermsCard({
  drafts,
  onEdit,
}: {
  drafts: Record<string, TermDraft>
  onEdit: (clause: string) => void
}) {
  const pending = pendingTermCount(drafts)
  const editedCount = Object.values(drafts).filter((d) => d.edited).length

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle
          title="委托合同条款逐条审核"
          hint="律师核对后定稿"
          className="w-full"
          action={
            <>
              {editedCount > 0 ? <Pill tone="blue">已改 {editedCount}</Pill> : null}
              {pending > 0 ? <Pill tone="yellow">待定 {pending}</Pill> : <Pill tone="green">全部确认</Pill>}
            </>
          }
        />
      </div>
      <ul className="divide-y divide-border-light">
        {DEMO_CONTRACT_TERMS.map((t) => {
          const d = drafts[t.clause] ?? { value: t.value, edited: false }
          const stillPending = !t.filled && !d.edited
          return (
            <li
              key={t.clause}
              className={cn(
                'flex items-center gap-3 px-5 py-2',
                stillPending && 'bg-status-yellow-bg/40',
              )}
            >
              <span className="w-[84px] flex-none text-[11.5px] text-muted-foreground">{t.clause}</span>
              <span className="min-w-0 flex-1 truncate text-[12px] font-medium" title={d.value}>
                {d.value}
              </span>
              {stillPending ? (
                <span className="flex flex-none items-center gap-1 text-[10px] text-status-yellow">
                  <AlertTriangle className="size-3" />
                  未填
                </span>
              ) : null}
              <span className="w-[120px] flex-none truncate text-[10px] text-muted-foreground" title={t.source}>
                {t.source}
              </span>
              <span className="flex w-[124px] flex-none items-center justify-end gap-1.5">
                {d.edited ? <Pill tone="blue">已修改</Pill> : <Pill tone={t.filled ? 'green' : 'yellow'}>{t.filled ? '已填' : '待定'}</Pill>}
                <ActionButton sm onClick={() => onEdit(t.clause)}>
                  <PencilLine className="size-3" />
                  编辑
                </ActionButton>
              </span>
            </li>
          )
        })}
      </ul>
    </WorkCard>
  )
}

/**
 * 单条条款的编辑抽屉：改完保存回列表。
 *
 * 面板里这个抽屉是**常驻挂载**的（`clause` 为 null 时渲染成空），所以草稿不能留在
 * 这一层：`TermEditDrawerBody` 才是按 clause 取 key 的内容层，换一条 = 换实例，
 * 上一条改了没保存的字不会跟到下一条的输入框里（也不会被「保存修改」写到新条目上）。
 * 手法同 contract-review 的 ReviewLaunchDrawer / 本目录 returned/MailboxConfig。
 */
export function TermEditDrawer({
  clause,
  drafts,
  onSave,
  onClose,
}: {
  clause: string | null
  drafts: Record<string, TermDraft>
  onSave: (clause: string, value: string) => void
  onClose: () => void
}) {
  const term = clause ? DEMO_CONTRACT_TERMS.find((t) => t.clause === clause) : undefined

  if (term == null) return null

  return (
    <TermEditDrawerBody
      key={term.clause}
      term={term}
      value={drafts[term.clause]?.value ?? term.value}
      edited={drafts[term.clause]?.edited ?? false}
      onSave={onSave}
      onClose={onClose}
    />
  )
}

/** 内容层：抽屉打开时才挂载，输入框的草稿活在这里 */
function TermEditDrawerBody({
  term,
  value,
  edited,
  onSave,
  onClose,
}: {
  term: ContractTermRow
  /** 这一条的当前值（改过就是草稿值，没改就是自动填充值） */
  value: string
  edited: boolean
  onSave: (clause: string, value: string) => void
  onClose: () => void
}) {
  /** 输入框的值提到这一层：保存按钮在 footer，得拿到最新文本 */
  const [text, setText] = useState(value)

  return (
    <DetailDrawer
      open
      onClose={onClose}
      width={480}
      title={`${term.clause} · 编辑`}
      subtitle={term.source}
      badge={edited ? <Pill tone="blue">已修改</Pill> : null}
      footer={
        <>
          <ActionButton dark onClick={() => onSave(term.clause, text.trim() || term.value)}>
            保存修改
          </ActionButton>
          <ActionButton onClick={onClose}>取消</ActionButton>
        </>
      }
    >
      <TermEditBody
        current={value}
        source={term.source}
        filled={term.filled}
        text={text}
        onChange={setText}
      />
    </DetailDrawer>
  )
}

/** 编辑体：受控输入，初值由内容层给（那条的自动填充值，不是上一条的草稿） */
function TermEditBody({
  current,
  source,
  filled,
  text,
  onChange,
}: {
  current: string
  source: string
  filled: boolean
  /** 正在编辑的文本（草稿在内容层，保存按钮要拿最新那份） */
  text: string
  onChange: (value: string) => void
}) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <div className="mb-1 text-[10.5px] text-muted-foreground">条款内容</div>
        <textarea
          value={text}
          rows={3}
          onChange={(e) => onChange(e.target.value)}
          className="w-full resize-y rounded-[8px] border border-border bg-background px-2.5 py-2 text-[12px] leading-[1.6] outline-none focus:border-foreground/40"
        />
      </div>

      <InsetBlock>
        <div className="text-[10px] text-muted-foreground">自动填充值（供对照）</div>
        <p className="mt-1 text-[11.5px] font-medium">{current}</p>
        <div className="mt-1 text-[10px] text-muted-foreground">来源：{source}</div>
      </InsetBlock>

      {!filled ? (
        <InsetBlock className="border-status-yellow/40 bg-status-yellow-bg/50">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-[1px] size-3 flex-none text-status-yellow" />
            <p className="text-[10.5px] leading-[1.65] text-muted-foreground">
              这一条自动填充拿不准（特别授权授到什么程度要律所自己定）。
              改完保存才会从「待定」变成「已修改」，不影响利冲判定。
            </p>
          </div>
        </InsetBlock>
      ) : null}
    </div>
  )
}

/** 生成的委托材料 + 逐行模板下拉 */
export function ContractGenCard({
  generating,
  onGenerate,
  templates,
  onTemplateChange,
  onOpenDoc,
}: {
  generating: boolean
  onGenerate: () => void
  templates: Record<string, string>
  onTemplateChange: (docName: string, template: string) => void
  onOpenDoc: (docName: string) => void
}) {
  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle
          title="自动生成的委托材料"
          hint="按案件数据套模板 · 每份可换模板"
          className="w-full"
          action={
            <ActionButton sm disabled={generating} onClick={onGenerate}>
              {generating ? '生成中…' : '生成文书'}
            </ActionButton>
          }
        />
      </div>
      <ul className="divide-y divide-border-light">
        {DEMO_CONTRACT_GEN.map((d) => (
          <ClickableRow
            key={d.name}
            nestedControl
            onClick={() => onOpenDoc(d.name)}
            className="flex items-center gap-3 px-5 py-2.5"
          >
            <FileText className="size-3.5 flex-none text-muted-foreground" />
            <span className="min-w-0 flex-1">
              <span className="block text-[12.5px] font-medium">{d.name}</span>
              <span className="mt-0.5 block text-[10.5px] text-muted-foreground">{d.source}</span>
            </span>
            <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">{d.pages} 页</span>
            <Pill tone={d.status === 'generated' ? 'green' : 'yellow'}>
              {d.status === 'generated' ? '已生成' : '待生成'}
            </Pill>
            {/* 模板下拉只切模板、不开行：鼠标靠 stopPropagation，键盘由 ClickableRow 按事件源放行 */}
            <select
              aria-label={`${d.name} 模板`}
              value={templates[d.name] ?? 'v3.2'}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => onTemplateChange(d.name, e.target.value)}
              className="h-[27px] flex-none rounded-[7px] border border-border bg-card px-1.5 text-[11px] text-secondary-foreground outline-none hover:border-input"
            >
              <option value="v3.2">模板 v3.2</option>
              <option value="v2.8">模板 v2.8</option>
              <option value="custom">自定义</option>
            </select>
          </ClickableRow>
        ))}
      </ul>
    </WorkCard>
  )
}
