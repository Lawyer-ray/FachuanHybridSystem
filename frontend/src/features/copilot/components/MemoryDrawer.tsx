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
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Brain, Check, Plus, Sparkles, Trash2, X } from 'lucide-react'

import {
  confirmMemories,
  createMemory,
  fetchMemoryScopes,
  forgetMemory,
  listMemories,
  type AgentMemoryItem,
  type MemoryKind,
  type MemoryScope,
} from '../memory-api'
import { MemoryPromoteDialog } from './MemoryPromoteDialog'
import { Button } from '@/components/ui/button'
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'

/** 类型中文名与注入优先级一致：纠正 > 偏好 > 惯例 > 事实 */
const KIND_LABEL: Record<MemoryKind, string> = {
  correction: '纠正',
  preference: '偏好',
  procedure: '惯例',
  fact: '事实',
}

const KIND_OPTIONS: MemoryKind[] = ['preference', 'procedure', 'fact', 'correction']

const SCOPE_LABEL: Record<MemoryScope, string> = {
  lawyer: '我的记忆',
  team: '团队记忆',
  law_firm: '律所记忆',
}

/** 单条记忆的字符上限（与后端 `create_memory` 的 1000 字校验一致） */
const MAX_CONTENT = 1000

export function MemoryDrawer({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const queryClient = useQueryClient()
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

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['copilot', 'memory'] })
  }

  const createMutation = useMutation({
    mutationFn: (payload: { content: string; kind: MemoryKind }) => createMemory(payload.content, payload.kind),
    onSuccess: () => {
      setDraft('')
      invalidate()
    },
  })

  const forgetMutation = useMutation({
    mutationFn: (id: string) => forgetMemory(id),
    onSuccess: invalidate,
  })

  const confirmMutation = useMutation({
    mutationFn: (payload: { ids: string[]; accept: boolean }) => confirmMemories(payload.ids, payload.accept),
    onSuccess: invalidate,
  })

  const all = memoriesQuery.data ?? []
  const pending = all.filter((m) => m.status === 'pending')
  const active = all.filter((m) => m.status === 'active')
  const byScope = (scope: MemoryScope) => active.filter((m) => m.scope === scope)

  const canCurate =
    (scopesQuery.data?.law_firm.can_curate ?? false) || (scopesQuery.data?.teams.some((t) => t.can_curate) ?? false)

  const draftTrimmed = draft.trim()
  const draftTooLong = draftTrimmed.length > MAX_CONTENT

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="max-w-[min(560px,calc(100vw-1.75rem))]">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Brain className="h-4 w-4 opacity-70" />
            助手记忆
          </SheetTitle>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            跨会话生效。AI 会据此调整表达与做法，但**不会**拿它当案件事实——涉及案号、金额、期限仍以系统数据为准。
          </p>
        </SheetHeader>

        <SheetBody className="px-6 pt-4">
          {/* 待确认：自动抽取/行为推断产出，确认后才进上下文 */}
          {pending.length > 0 && (
            <section className="mb-5" aria-label="待确认的记忆">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="flex items-center gap-1.5 text-[12px] font-[650] text-foreground">
                  <Sparkles className="h-3.5 w-3.5 opacity-70" />
                  待确认 {pending.length} 条
                </h3>
                <div className="flex gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-[11px]"
                    disabled={confirmMutation.isPending}
                    onClick={() => confirmMutation.mutate({ ids: pending.map((m) => m.id), accept: false })}
                  >
                    全部忽略
                  </Button>
                  <Button
                    size="sm"
                    className="h-7 px-2 text-[11px]"
                    disabled={confirmMutation.isPending}
                    onClick={() => confirmMutation.mutate({ ids: pending.map((m) => m.id), accept: true })}
                  >
                    全部确认
                  </Button>
                </div>
              </div>
              <ul className="space-y-1.5">
                {pending.map((memory) => (
                  <li
                    key={memory.id}
                    className="rounded-[10px] border border-dashed border-border bg-secondary/40 px-3 py-2.5"
                  >
                    <p className="text-[13px] leading-relaxed text-foreground">{memory.content}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {KIND_LABEL[memory.kind]}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        置信度 {(memory.confidence * 100).toFixed(0)}%
                      </span>
                      <div className="ml-auto flex gap-1">
                        <button
                          type="button"
                          aria-label="忽略这条记忆"
                          className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                          onClick={() => confirmMutation.mutate({ ids: [memory.id], accept: false })}
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          aria-label="确认这条记忆"
                          className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-foreground hover:text-background"
                          onClick={() => confirmMutation.mutate({ ids: [memory.id], accept: true })}
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* 新增：手动录入个人记忆 */}
          <section className="mb-5" aria-label="新增记忆">
            <label htmlFor="memory-draft" className="mb-1.5 block text-[12px] font-[650] text-foreground">
              让助手记住一件事
            </label>
            <Textarea
              id="memory-draft"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="例如：文书先给结论，再给理由；引用法条时附条文原文"
              rows={2}
              className="resize-none text-[13px]"
            />
            <div className="mt-2 flex items-center gap-2">
              <select
                aria-label="记忆类型"
                value={draftKind}
                onChange={(e) => setDraftKind(e.target.value as MemoryKind)}
                className="h-7 rounded-[7px] border border-border bg-card px-2 text-[11px] text-foreground"
              >
                {KIND_OPTIONS.map((kind) => (
                  <option key={kind} value={kind}>
                    {KIND_LABEL[kind]}
                  </option>
                ))}
              </select>
              {draftTooLong && <span className="text-[10px] text-destructive">超出 {MAX_CONTENT} 字</span>}
              <Button
                size="sm"
                className="ml-auto h-7 gap-1 px-2.5 text-[11px]"
                disabled={!draftTrimmed || draftTooLong || createMutation.isPending}
                onClick={() => createMutation.mutate({ content: draftTrimmed, kind: draftKind })}
              >
                <Plus className="h-3 w-3" />
                记住
              </Button>
            </div>
            {createMutation.isError && (
              <p className="mt-1.5 text-[11px] text-destructive">
                保存失败：{createMutation.error.message}
              </p>
            )}
          </section>

          {/* 已生效：按作用域分组 */}
          {(['lawyer', 'team', 'law_firm'] as MemoryScope[]).map((scope) => {
            const items = byScope(scope)
            // 团队/律所层为空且无可策展权限时不占位
            if (items.length === 0 && scope !== 'lawyer') return null
            return (
              <MemoryGroup
                key={scope}
                scope={scope}
                items={items}
                loading={memoriesQuery.isLoading}
                onForget={(id) => forgetMutation.mutate(id)}
                forgetting={forgetMutation.isPending}
              />
            )
          })}

          {canCurate && (
            <div className="mt-5 rounded-[10px] border border-border bg-secondary/30 px-3 py-2.5">
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                你是本团队/律所的管理员，可以把成员的高频记忆提炼为团队级惯例（需改写脱敏，不会原样共享）。
              </p>
              <Button
                size="sm"
                variant="secondary"
                className="mt-2 h-7 px-2.5 text-[11px]"
                onClick={() => setPromoteOpen(true)}
              >
                提炼为团队惯例
              </Button>
            </div>
          )}

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

function MemoryGroup({
  scope,
  items,
  loading,
  onForget,
  forgetting,
}: {
  scope: MemoryScope
  items: AgentMemoryItem[]
  loading: boolean
  onForget: (id: string) => void
  forgetting: boolean
}) {
  return (
    <section className="mb-4" aria-label={SCOPE_LABEL[scope]}>
      <h3 className="mb-1.5 text-[12px] font-[650] text-foreground">
        {SCOPE_LABEL[scope]}
        <span className="ml-1.5 font-normal text-muted-foreground">{items.length}</span>
      </h3>
      {loading && items.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">加载中…</p>
      ) : items.length === 0 ? (
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          还没有记忆。在上方输入，或直接对助手说「记住…」。
        </p>
      ) : (
        <ul className="space-y-1">
          {items.map((memory) => (
            <li
              key={memory.id}
              className="group flex items-start gap-2 rounded-[8px] px-2 py-1.5 transition-colors hover:bg-secondary/60"
            >
              <span className="mt-0.5 flex-none rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {KIND_LABEL[memory.kind]}
              </span>
              <p className="min-w-0 flex-1 text-[13px] leading-relaxed text-foreground">{memory.content}</p>
              {memory.hit_count > 0 && (
                <span
                  className="mt-0.5 flex-none text-[10px] text-muted-foreground/70"
                  title={`已注入上下文 ${memory.hit_count} 次`}
                >
                  {memory.hit_count}
                </span>
              )}
              {scope === 'lawyer' && (
                <button
                  type="button"
                  aria-label="删除这条记忆"
                  disabled={forgetting}
                  className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-[5px] text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive focus:opacity-100"
                  onClick={() => onForget(memory.id)}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
