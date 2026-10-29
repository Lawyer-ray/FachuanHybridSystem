import { useState } from 'react'
import { toast } from 'sonner'

import { cn } from '@/lib/utils'
import { Field, IconBtn, SmallDash, TextInput } from './PhaseDesignParts'
import { addDeliverable, removeDeliverable } from './special-phase-crud'
import { deliverableStateLabel } from './special-phase-state'
import {
  MAX_DEPTH,
  appendChild,
  appendPhase,
  blankPhase,
  findByKey,
  flattenTree,
  indentPhase,
  insertAfter,
  moveBy,
  outdentPhase,
  patchPhase,
  removePhase,
  renamePhase,
  type PhaseNode,
} from './special-phase-tree'

/**
 * 「手工设计」页签：左侧阶段主线 + 右侧选中阶段细节（54 号原型第十一轮的两栏编辑器）。
 *
 * **为什么两栏而不是一列长表单**：阶段是主线，细节是支线。5 个阶段的完整细节摊成
 * 一列会有 40+ 个输入框，改第 1 阶段要滚过后面 4 个。左栏一屏看完主线、右栏专注
 * 当前这一个，是这类编辑器的通行解法。
 *
 * 弹窗宽度 960（见 PhaseDesignDialog）：620 宽会把《债权债务清理方案》这类长文书名
 * 截成前 8 个字，律师没法核对清单。
 */
export function PhaseDesignPane({
  draft,
  selKey,
  onChange,
  onSelect,
}: {
  draft: PhaseNode[]
  selKey: string | null
  /** 整树替换（结构操作都走纯函数，这里只把结果交上去） */
  onChange: (next: PhaseNode[]) => void
  onSelect: (key: string | null) => void
}) {
  const flat = flattenTree(draft)
  const sel = selKey ? (findByKey(draft, selKey)?.node ?? null) : null

  const addPhase = () => {
    const node = blankPhase('')
    const next = selected(draft, sel) ? insertAfter(draft, sel!.key, node) : appendPhase(draft, node)
    onChange(next)
    onSelect(node.key)
  }

  return (
    <div className="grid min-h-[440px] grid-cols-[268px_minmax(0,1fr)] gap-[22px] max-[720px]:grid-cols-1">
      {/* 左：阶段主线 */}
      <div className="flex min-w-0 flex-col pr-3.5 max-[720px]:border-r-0 max-[720px]:border-b max-[720px]:border-border-light max-[720px]:pb-3">
        <div className="mb-2 flex items-baseline gap-2 text-[12px] font-[650] text-secondary-foreground">
          阶段主线
          <span className="text-[11px] font-[400] text-muted-foreground tabular-nums">{flat.length}</span>
        </div>
        <div className="mb-2.5 flex max-h-[360px] flex-col gap-1 overflow-y-auto pr-0.5">
          {flat.length === 0 ? (
            <div className="px-1 py-5 text-[12px] text-muted-foreground">还没有阶段</div>
          ) : (
            flat.map((item) => {
              const on = item.node.key === sel?.key
              const docs = item.node.deliverables.length
              return (
                <button
                  key={item.node.key}
                  type="button"
                  onClick={() => onSelect(item.node.key)}
                  className={cn(
                    'flex cursor-pointer items-center gap-[9px] rounded-[8px] border px-2.5 py-[9px] text-left transition-colors',
                    on ? 'border-foreground bg-card shadow-[inset_0_0_0_1px_var(--foreground)]' : 'border-transparent hover:bg-secondary',
                    item.depth === 2 && 'bg-secondary/30',
                    item.depth === 3 && 'bg-secondary/50',
                  )}
                >
                  <span className="block shrink-0" style={{ width: (item.depth - 1) * 14 }} />
                  <span className="w-4 shrink-0 text-right text-[11px] text-muted-foreground tabular-nums">{item.no}</span>
                  <span className="flex min-w-0 flex-1 flex-col gap-px">
                    <b
                      className={cn(
                        'line-clamp-2 text-[13px] leading-[1.45] font-[620]',
                        item.depth > 1 && 'text-[12px] font-[600]',
                      )}
                    >
                      {item.node.name || '未命名阶段'}
                    </b>
                    <span className="text-[11px] text-muted-foreground tabular-nums">
                      {docs} 交付物
                      {item.node.folders.length ? ` · ${item.node.folders.length} 子阶段` : ''}
                    </span>
                  </span>
                  {item.node.acceptance ? (
                    <span className="shrink-0 text-[11px] text-status-green" title="已写验收标准">
                      ✓
                    </span>
                  ) : null}
                </button>
              )
            })
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <SmallDash onClick={addPhase}>＋ 阶段</SmallDash>
        </div>
      </div>

      {/* 右：选中阶段细节 */}
      <div className="flex min-w-0 max-h-[62vh] flex-col gap-[13px] overflow-y-auto pr-1">
        {!sel ? (
          <div className="px-2.5 py-10 text-center text-[12.5px] leading-[1.8] text-muted-foreground">
            左侧还没有阶段。
            <br />
            直接「＋ 阶段」就能开始定义这条主线。
          </div>
        ) : (
          <PhaseDetail draft={draft} phase={sel} onChange={onChange} onSelect={onSelect} />
        )}
      </div>
    </div>
  )
}

function selected(draft: PhaseNode[], sel: PhaseNode | null): boolean {
  return !!sel && !!findByKey(draft, sel.key)
}

/** 右侧细节：名称 / 验收标准 / 交付物清单 / 子阶段 / 层级与顺序动作 */
function PhaseDetail({
  draft,
  phase,
  onChange,
  onSelect,
}: {
  draft: PhaseNode[]
  phase: PhaseNode
  onChange: (next: PhaseNode[]) => void
  onSelect: (key: string | null) => void
}) {
  const [newDoc, setNewDoc] = useState('')
  const hit = findByKey(draft, phase.key)
  const depth = hit?.path.length ?? 1
  const no = hit?.path.map((i) => i + 1).join('.') ?? '1'
  const key = phase.key

  const apply = (result: { tree: PhaseNode[]; ok: boolean; reason?: string }) => {
    if (!result.ok) {
      toast.info(result.reason ?? '这一步做不了')
      return
    }
    onChange(result.tree)
  }

  const addChild = () => {
    const node = blankPhase('')
    const next = appendChild(draft, key, node)
    if (next === draft) {
      toast.info(`最多 ${MAX_DEPTH} 级`)
      return
    }
    onChange(next)
    onSelect(node.key)
  }

  const del = () => {
    if (phase.folders.length > 0 && !window.confirm(`「${phase.name}」下面还有 ${phase.folders.length} 个子阶段，一起删除？`)) {
      return
    }
    const next = removePhase(draft, key)
    onChange(next)
    onSelect(flattenTree(next)[0]?.node.key ?? null)
  }

  const commitDoc = () => {
    if (!newDoc.trim()) return
    onChange(addDeliverable(draft, key, newDoc))
    setNewDoc('')
  }

  return (
    <>
      <div className="flex items-baseline gap-2 text-[12px] font-[650] text-secondary-foreground">
        第 {no} 阶段
        <span className="rounded-[5px] border border-border-light bg-secondary px-1.5 text-[11px] font-[620] text-muted-foreground tabular-nums">
          {depth} 级 / 最多 {MAX_DEPTH} 级
        </span>
        <span className="ml-auto flex gap-1">
          <IconBtn label="降一级（挂到上一个同级阶段下）" disabled={depth >= MAX_DEPTH} onClick={() => apply(indentPhase(draft, key))}>
            →
          </IconBtn>
          <IconBtn label="升一级" disabled={depth <= 1} onClick={() => apply(outdentPhase(draft, key))}>
            ←
          </IconBtn>
          <span className="mx-0.5 h-3.5 w-px self-center bg-border" />
          <IconBtn label="同级上移" onClick={() => onChange(moveBy(draft, key, -1))}>
            ↑
          </IconBtn>
          <IconBtn label="同级下移" onClick={() => onChange(moveBy(draft, key, 1))}>
            ↓
          </IconBtn>
          <IconBtn label="删除阶段" danger onClick={del}>
            ✕
          </IconBtn>
        </span>
      </div>

      <Field label="阶段名称">
        <TextInput value={phase.name} placeholder="如：职工沟通" onChange={(v) => onChange(renamePhase(draft, key, v))} />
      </Field>

      <Field label="验收标准" note="写清「到什么程度算这一步做完」">
        <TextInput
          value={phase.acceptance}
          placeholder="如：《职工安置方案》定稿并经客户书面确认"
          onChange={(v) => onChange(patchPhase(draft, key, { acceptance: v }))}
        />
      </Field>

      <Field label="本阶段交付物" note="逐行一份，与左栏交付物表同源">
        <div className="flex flex-col gap-1">
          {phase.deliverables.length === 0 ? (
            <div className="text-[12px] text-muted-foreground">还没有交付物</div>
          ) : (
            phase.deliverables.map((d) => (
              <div
                key={d.id}
                className="flex items-center gap-1.5 rounded-[7px] border border-border-light bg-secondary/40 px-2.5 py-1.5"
              >
                <span className="min-w-0 flex-1 text-[13px] leading-[1.5] break-words">{d.name}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">{deliverableStateLabel(d)}</span>
                <IconBtn label="移除" danger onClick={() => onChange(removeDeliverable(draft, key, d.id))}>
                  ✕
                </IconBtn>
              </div>
            ))
          )}
        </div>
        <div className="mt-1.5 flex items-center gap-1.5">
          <input
            value={newDoc}
            placeholder="《文书名称》，回车添加"
            onChange={(e) => setNewDoc(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                commitDoc()
              }
            }}
            className="min-w-0 flex-1 rounded-[7px] border border-border bg-card px-2.5 py-1.5 text-[12.5px] outline-none focus:border-input"
          />
          <IconBtn label="添加" onClick={commitDoc}>
            ＋
          </IconBtn>
        </div>
      </Field>

      <div className="flex flex-wrap items-center gap-[7px] border-t border-border-light pt-2.5">
        <span className="text-[11.5px] font-[650] text-muted-foreground">子阶段 · {phase.folders.length}</span>
        {depth < MAX_DEPTH ? (
          <SmallDash onClick={addChild}>＋ 在下面加子阶段</SmallDash>
        ) : (
          <span className="text-[11px] text-muted-foreground">已达 {MAX_DEPTH} 级上限</span>
        )}
        {phase.folders.length > 0 && (
          <div className="flex w-full flex-wrap gap-1.5">
            {phase.folders.map((c) => (
              <span
                key={c.key}
                className="rounded-full border border-border-light bg-secondary px-2 py-px text-[11px] text-secondary-foreground"
              >
                {c.name || '未命名阶段'}
              </span>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
