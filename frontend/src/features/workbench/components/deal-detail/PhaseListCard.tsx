import { useState } from 'react'
import { toast } from 'sonner'

import { addDeliverable } from './special-phase-crud'
import { PhaseAddDeliverableDialog, PhaseDraftDialog } from './PhaseCreateDialogs'
import { PhaseDesignDialog } from './PhaseDesignDialog'
import { PhaseTable } from './PhaseTable'
import { flattenTree, renamePhase, toggleOpen, type PhaseDeliverable, type PhaseNode } from './special-phase-tree'
import { Card } from './ui'

/**
 * 「阶段与交付物」卡：卡片头（计数 + 三个创建动作）+ 真表格 + 脚注。
 *
 * 三个动作都是**创建**，没有导航型按钮（项目红线：按钮只剩创建）：
 * - 设计阶段 → 960 宽的两栏编辑器（手工 / AI 对话两页签）；
 * - 从 0 起草 → 落到选中阶段 + 直接进编辑器（律师此刻要的是「马上改」）；
 * - 新增交付物 → 只加一行「待起草」的计划项，不改阶段结构。
 */
export function PhaseListCard({
  tree,
  saving,
  isLoading,
  endpointNote,
  fileCountOf,
  onTreeChange,
  onSave,
  onOpenDeliverable,
  onDraftInto,
  note,
}: {
  tree: PhaseNode[]
  saving: boolean
  isLoading: boolean
  /** 阶段接口不可用时的提示（端点未上线也能继续设计，只是不落库） */
  endpointNote: string | null
  fileCountOf: (node: PhaseNode) => number
  /** 表格内的即时改动（折叠 / 改名 / 新增计划项）：本地生效并落库 */
  onTreeChange: (next: PhaseNode[]) => void
  /** 设计器保存（整树提交，与即时改动同一落库入口） */
  onSave: (next: PhaseNode[]) => void
  onOpenDeliverable: (d: PhaseDeliverable) => void
  /** 「＋ 起草」/「从 0 起草」：落到某阶段的计划项，并打开编辑器 */
  onDraftInto: (phaseKey: string, name: string) => void
  note?: string
}) {
  const [designOpen, setDesignOpen] = useState(false)
  const [draftOpen, setDraftOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  /** 起草 / 新增交付物的默认目标阶段（「＋ 起草」在自己行上时选自己） */
  const [targetKey, setTargetKey] = useState<string | null>(null)
  const flat = flattenTree(tree)
  const done = flat.filter((x) => x.node.state === 'done').length

  const openCreate = (key: string | null, which: 'draft' | 'add') => {
    const leaves = flat.filter((x) => x.node.folders.length === 0)
    setTargetKey(key ?? leaves[0]?.node.key ?? flat[0]?.node.key ?? null)
    if (which === 'draft') setDraftOpen(true)
    else setAddOpen(true)
  }

  return (
    <Card>
      <div className="flex items-center gap-2.5 px-5 pt-3.5 pb-0">
        <b className="text-[14px] font-[680]">阶段与交付物</b>
        <span className="text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">{flat.length} 阶段</span>
        <span className="text-[11.5px] text-muted-foreground/70">双击改名 · 与合同文件夹同步</span>
        <span className="ml-auto flex gap-1.5">
          <CardBtn onClick={() => setDesignOpen(true)}>✎ 设计阶段</CardBtn>
          <CardBtn onClick={() => openCreate(null, 'draft')}>✦ 从 0 起草</CardBtn>
          <CardBtn onClick={() => openCreate(null, 'add')}>＋ 新增交付物</CardBtn>
        </span>
      </div>

      {endpointNote && (
        <div className="mx-5 mt-2.5 rounded-[7px] border border-border-light bg-secondary/40 px-2.5 py-1.5 text-[11.5px] leading-[1.6] text-muted-foreground">
          合同阶段接口暂不可用（{endpointNote}）：阶段改动只保存在本页，接口上线后即可落库。
        </div>
      )}

      {flat.length === 0 ? (
        <div className="px-5 py-6 text-[12.5px] leading-relaxed text-muted-foreground">
          {isLoading
            ? '正在读取阶段…'
            : '这份专项还没有阶段。点「设计阶段」定下分成几步、每步交什么，或在合同文件夹里按「序号-阶段名」建子文件夹（如 1-尽职调查）。'}
        </div>
      ) : (
        <div className="mt-2">
          <PhaseTable
            tree={tree}
            fileCountOf={fileCountOf}
            /* 展开/折叠 = 纯 UI 位置，只改本地（每次点行都发 PUT 既慢又会
               被服务端返回的树洗掉 open，表现为「点不开」）；
               改名 = 业务数据，必须落库。 */
            onToggle={(key) => onTreeChange(toggleOpen(tree, key))}
            onRename={(key, name) => onSave(renamePhase(tree, key, name))}
            onOpenDeliverable={onOpenDeliverable}
            onDraft={(key) => openCreate(key, 'draft')}
          />
        </div>
      )}

      {note && (
        <div className="mt-1 flex items-center gap-1 border-t border-border-light px-5 py-2.5 text-[11.5px] text-muted-foreground">
          {note}
          <span className="ml-auto text-[11px] text-muted-foreground/70 tabular-nums">
            已完成 {done} / {flat.length}
          </span>
        </div>
      )}

      <PhaseDesignDialog open={designOpen} tree={tree} saving={saving} onOpenChange={setDesignOpen} onSave={onSave} />

      <PhaseDraftDialog
        open={draftOpen}
        tree={tree}
        targetKey={targetKey}
        onTarget={setTargetKey}
        onOpenChange={setDraftOpen}
        onSubmit={(key, name) => {
          setDraftOpen(false)
          onDraftInto(key, name)
        }}
      />

      <PhaseAddDeliverableDialog
        open={addOpen}
        tree={tree}
        targetKey={targetKey}
        onTarget={setTargetKey}
        onOpenChange={setAddOpen}
        onSubmit={(key, name) => {
          onTreeChange(addDeliverable(tree, key, name))
          setAddOpen(false)
          const phase = flat.find((x) => x.node.key === key)?.node.name ?? ''
          toast.success('已新增交付物 · 待起草', { description: `落在「${phase}」` })
        }}
      />
    </Card>
  )
}

function CardBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-[27px] cursor-pointer items-center rounded-[7px] border border-border bg-card px-2.5 text-[11.5px] font-[550] whitespace-nowrap text-secondary-foreground transition-colors hover:border-input hover:bg-secondary"
    >
      {children}
    </button>
  )
}
