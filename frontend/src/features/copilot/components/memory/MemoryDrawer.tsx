/**
 * 记忆抽屉：律师查看/新增/删除自己的记忆，确认 AI 自动抽取的待确认项。
 *
 * ## 设计取舍
 *
 * 1. **按作用域分组，但只读别人的层**。个人层可增删改；团队/律所层只展示
 *    （写入必须走策展提升，见 `MemoryPromoteDialog`）——后端
 *    `create_memory` 也拒绝非 lawyer 作用域，两侧口径一致。
 * 2. **待确认项单独置顶**。自动抽取（会话结束）与行为推断产出的记忆默认
 *    `pending`，不确认不进上下文。把它折叠在列表里等于让这个闸门形同虚设。
 * 3. **删除是软删**。列表里不展示已删项，但后端保留记录可恢复；这里不提供
 *    恢复入口（律师删了就是不想看，恢复属于运维动作）。
 * 4. **不提供"编辑"**。记忆是「一句话事实」，改写它等于换了一条记忆，
 *    走「删除 + 新增」语义更清楚，也避免悄悄改掉 AI 的认识来源。
 *
 * 本文件只留外壳（queries / mutations / 策展入口）；待确认区、新增表单、分组列表
 * 分别在 `memory/` 下，类型名等常量在 `memory/labels.ts`。
 *
 * 拆分记录：已生效记忆的分组列表在 `ActiveMemoryList`，策展入口提示在 `CuratePrompt`，
 * 三个写入动作在 `use-memory-mutations`。
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Brain } from 'lucide-react'

import { fetchMemoryScopes, listMemories } from '../../memory-api'
import type { MemoryKind } from '../../types'
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { ActiveMemoryList } from './ActiveMemoryList'
import { CuratePrompt } from './CuratePrompt'
import { MemoryComposer } from './MemoryComposer'
import { MemoryPromoteDialog } from './MemoryPromoteDialog'
import { PendingMemorySection } from './PendingMemorySection'
import { useMemoryMutations } from './use-memory-mutations'

export function MemoryDrawer({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [draft, setDraft] = useState('')
  const [draftKind, setDraftKind] = useState<MemoryKind>('preference')
  const [promoteOpen, setPromoteOpen] = useState(false)

  const memoriesQuery = useQuery({
    queryKey: ['copilot', 'memory', 'list'],
    queryFn: () => listMemories({ limit: 300 }),
    enabled: open,
    staleTime: 30_000,
  })

  const scopesQuery = useQuery({
    queryKey: ['copilot', 'memory', 'scopes'],
    queryFn: fetchMemoryScopes,
    enabled: open,
    staleTime: 300_000,
  })

  const { createMutation, forgetMutation, confirmMutation, invalidate } = useMemoryMutations({
    onCreated: () => setDraft(''),
  })

  const all = memoriesQuery.data ?? []
  const pending = all.filter((m) => m.status === 'pending')
  const active = all.filter((m) => m.status === 'active')

  const canCurate =
    (scopesQuery.data?.law_firm.can_curate ?? false) || (scopesQuery.data?.teams.some((t) => t.can_curate) ?? false)

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="max-w-[min(560px,calc(100vw-1.75rem))]">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Brain className="h-4 w-4 opacity-70" />
            助手记忆
          </SheetTitle>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            跨会话生效。AI 会据此调整表达与做法，但
            <strong className="font-medium text-foreground">不会</strong>
            拿它当案件事实——涉及案号、金额、期限仍以系统数据为准。
          </p>
        </SheetHeader>

        <SheetBody className="px-6 pt-4">
          <PendingMemorySection
            pending={pending}
            pendingBusy={confirmMutation.isPending}
            onConfirm={(ids, accept) => confirmMutation.mutate({ ids, accept })}
          />

          <MemoryComposer
            draft={draft}
            onDraftChange={setDraft}
            kind={draftKind}
            onKindChange={setDraftKind}
            creating={createMutation.isPending}
            error={createMutation.isError ? createMutation.error.message : null}
            onSubmit={() => createMutation.mutate({ content: draft.trim(), kind: draftKind })}
          />

          {/* 已生效：按作用域分组 */}
          <ActiveMemoryList
            active={active}
            loading={memoriesQuery.isLoading}
            onForget={(id) => forgetMutation.mutate(id)}
            forgetting={forgetMutation.isPending}
          />

          {canCurate && <CuratePrompt onOpen={() => setPromoteOpen(true)} />}

          {memoriesQuery.isError && (
            <p className="mt-4 text-[12px] text-destructive">加载失败：{memoriesQuery.error.message}</p>
          )}
        </SheetBody>
      </SheetContent>

      <MemoryPromoteDialog
        open={promoteOpen}
        onOpenChange={setPromoteOpen}
        scopes={scopesQuery.data}
        onPromoted={() => {
          setPromoteOpen(false)
          invalidate()
        }}
      />
    </Sheet>
  )
}
