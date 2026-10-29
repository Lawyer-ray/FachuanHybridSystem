import { useState } from 'react'
import { toast } from 'sonner'

import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { flattenTree, type PhaseNode } from './special-phase-tree'

/**
 * 两个轻量创建弹窗：**从 0 起草** 与 **新增交付物**。
 *
 * 从 0 起草只问三件事——放到哪个阶段 / 文书名称 / 需求（写给 AI 的话），并提示
 * 「会给 AI 带上本合同信息，不必重复交代背景」。新增交付物只登记一行「待起草」的
 * 计划项，不改阶段结构。两者都只列**叶子**阶段：起草产出的是具体文书，挂在有子阶段
 * 的父节点上没法验收。
 */
export function PhaseDraftDialog({
  open,
  tree,
  targetKey,
  onTarget,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  tree: PhaseNode[]
  targetKey: string | null
  onTarget: (key: string) => void
  onOpenChange: (open: boolean) => void
  /** 提交：目标阶段 + 文书名（父级据此登记计划项并打开编辑器） */
  onSubmit: (phaseKey: string, name: string) => void
}) {
  const [name, setName] = useState('')
  const [need, setNeed] = useState('')

  const submit = () => {
    if (!targetKey) {
      toast.error('先选一个目标阶段')
      return
    }
    if (!name.trim()) {
      toast.error('请填写文书名称')
      return
    }
    if (!need.trim()) {
      toast.error('请说清楚要起草什么')
      return
    }
    onSubmit(targetKey, name.trim())
    setName('')
    setNeed('')
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(520px,calc(100vw-40px))] max-w-none gap-3 p-5 sm:max-w-none">
        <DialogTitle className="text-[15px] font-[680]">从 0 起草</DialogTitle>
        <p className="text-[12px] leading-[1.7] text-muted-foreground">会给 AI 带上本合同信息，不必重复交代背景。</p>
        <Field label="放到哪个阶段">
          <PhaseSelect tree={tree} value={targetKey} onChange={onTarget} />
        </Field>
        <Field label="文书名称">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="《文书名称》"
            className="w-full rounded-[7px] border border-border bg-card px-2.5 py-2 text-[13px] outline-none focus:border-input"
          />
        </Field>
        <Field label="需求">
          <textarea
            value={need}
            onChange={(e) => setNeed(e.target.value)}
            rows={3}
            placeholder="写给 AI 的话：要写什么、按什么口径、突出什么"
            className="w-full resize-y rounded-[7px] border border-border bg-card px-2.5 py-2 text-[13px] leading-[1.65] outline-none focus:border-input"
          />
        </Field>
        <Footer onCancel={() => onOpenChange(false)} onSubmit={submit} submitText="起草并打开" />
      </DialogContent>
    </Dialog>
  )
}

/** 新增交付物：只登记一行计划项（不改阶段结构） */
export function PhaseAddDeliverableDialog({
  open,
  tree,
  targetKey,
  onTarget,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  tree: PhaseNode[]
  targetKey: string | null
  onTarget: (key: string) => void
  onOpenChange: (open: boolean) => void
  onSubmit: (phaseKey: string, name: string) => void
}) {
  const [name, setName] = useState('')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(460px,calc(100vw-40px))] max-w-none gap-3 p-5 sm:max-w-none">
        <DialogTitle className="text-[15px] font-[680]">新增交付物</DialogTitle>
        <Field label="放到哪个阶段">
          <PhaseSelect tree={tree} value={targetKey} onChange={onTarget} />
        </Field>
        <Field label="交付物名称">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="《文书名称》"
            className="w-full rounded-[7px] border border-border bg-card px-2.5 py-2 text-[13px] outline-none focus:border-input"
          />
        </Field>
        <p className="text-[11.5px] leading-[1.6] text-muted-foreground">
          先作为「待起草」的计划项入表；在编辑器里起草或上传文件后才变成实际交付物。
        </p>
        <Footer
          onCancel={() => onOpenChange(false)}
          disabled={!targetKey || !name.trim()}
          submitText="记入"
          onSubmit={() => {
            if (targetKey && name.trim()) onSubmit(targetKey, name.trim())
            setName('')
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-[11.5px] font-[600] text-muted-foreground">
      {label}
      {children}
    </label>
  )
}

function Footer({
  onCancel,
  onSubmit,
  submitText,
  disabled,
}: {
  onCancel: () => void
  onSubmit: () => void
  submitText: string
  disabled?: boolean
}) {
  return (
    <div className="flex justify-end gap-2">
      <button
        type="button"
        onClick={onCancel}
        className="inline-flex h-[27px] cursor-pointer items-center rounded-[7px] border border-border bg-card px-2.5 text-[11.5px] text-secondary-foreground transition-colors hover:bg-secondary"
      >
        取消
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={onSubmit}
        className="inline-flex h-[27px] cursor-pointer items-center rounded-[7px] border border-foreground bg-foreground px-3 text-[11.5px] font-[600] text-background transition-opacity hover:opacity-85 disabled:opacity-50"
      >
        {submitText}
      </button>
    </div>
  )
}

/** 阶段下拉：只列**叶子**阶段（没有子阶段时退回全部） */
function PhaseSelect({ tree, value, onChange }: { tree: PhaseNode[]; value: string | null; onChange: (key: string) => void }) {
  const flat = flattenTree(tree)
  const leaves = flat.filter((x) => x.node.folders.length === 0)
  const usable = leaves.length > 0 ? leaves : flat
  return (
    <select
      value={value ?? usable[0]?.node.key ?? ''}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-[7px] border border-border bg-card px-2.5 py-2 text-[13px] outline-none focus:border-input"
    >
      {usable.map((x) => (
        <option key={x.node.key} value={x.node.key}>
          {`${x.no.replace(/\./g, ' · ')} ${x.node.name}`}
        </option>
      ))}
    </select>
  )
}
