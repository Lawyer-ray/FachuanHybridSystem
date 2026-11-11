/**
 * 回扫 —— 手动归案向导：搜案件 → 选归入槽位 → 确认（带进度）。
 *
 * 三个步骤的状态（搜什么、选中哪个案、归到哪个槽位）只在这个弹窗里有意义，
 * 所以收在组件内部；归案执行态（进度 / 日志）由面板持有，
 * 因为跑完之后面板还要能把结果说出来。
 */
import { useState } from 'react'

import { cn } from '@/lib/utils'
import { DEMO_X2_ASSIGN_CANDIDATES, type AssignCandidate } from '../../demo-data'
import { ActionButton, InsetBlock, Pill } from '../../ui'
import { DetailDrawer } from '../DetailDrawer'
import type { useStageAction } from '../use-stage-action'

/** 手动归案弹窗：搜案件 → 选中 → 选归入槽位 → 确认（带进度） */
export function AssignDrawer({
  subject,
  onClose,
  assign,
}: {
  subject: string | null
  onClose: () => void
  assign: ReturnType<typeof useStageAction<void>>
}) {
  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState<AssignCandidate | null>(null)
  const [slot, setSlot] = useState('')

  const open = subject != null
  const candidates = DEMO_X2_ASSIGN_CANDIDATES.filter(
    (c) => query.trim() === '' || c.name.includes(query.trim()) || c.caseNo.includes(query.trim()),
  )
  const running = assign.phase === 'running'

  return (
    <DetailDrawer
      open={open}
      onClose={onClose}
      title="指定归属"
      subtitle={subject ?? undefined}
      badge={assign.phase === 'done' ? <Pill tone="green">已归案</Pill> : <Pill tone="yellow">待人工</Pill>}
      width={480}
      footer={
        <>
          <ActionButton
            dark
            disabled={!picked || slot === '' || running}
            onClick={() => {
              if (picked) void assign.execute()
            }}
          >
            {running ? `归案中 ${assign.percent}%` : '确认归案'}
          </ActionButton>
          <ActionButton onClick={onClose}>取消</ActionButton>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {/* 第 1 步：搜案件 */}
        <div>
          <div className="text-[10px] text-muted-foreground">1. 搜案件名称或案号</div>
          <input
            aria-label="搜案件名称或案号"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setPicked(null)
              setSlot('')
            }}
            placeholder="输入案件名称 / 案号 / 当事人"
            className="mt-1 w-full rounded-[8px] border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground"
          />
          <ul className="mt-1.5 max-h-[190px] overflow-y-auto rounded-[8px] border border-border-light">
            {candidates.map((c) => {
              const selected = picked?.name === c.name
              return (
                <li key={c.name}>
                  <button
                    type="button"
                    aria-pressed={selected}
                    onClick={() => {
                      setPicked(c)
                      setSlot(c.slots[0] ?? '')
                    }}
                    className={cn(
                      'flex w-full items-start gap-2 px-2.5 py-2 text-left transition-colors hover:bg-secondary/50',
                      selected && 'bg-secondary',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-[3px] size-3 flex-none rounded-full border',
                        selected ? 'border-foreground bg-foreground' : 'border-border bg-card',
                      )}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[11.5px] font-medium">{c.name}</span>
                      <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                        {c.caseNo} · {c.court}
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">{c.party}</span>
                    </span>
                  </button>
                </li>
              )
            })}
            {candidates.length === 0 ? (
              <li className="px-2.5 py-3 text-center text-[10.5px] text-muted-foreground">没有匹配的案件</li>
            ) : null}
          </ul>
        </div>

        {/* 第 2 步：选槽位 */}
        <div>
          <div className="text-[10px] text-muted-foreground">2. 选归入槽位</div>
          {picked ? (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {picked.slots.map((s) => (
                <button
                  key={s}
                  type="button"
                  aria-pressed={slot === s}
                  onClick={() => setSlot(s)}
                  className={cn(
                    'h-[24px] rounded-[6px] border px-2 text-[11px] transition-colors',
                    slot === s
                      ? 'border-foreground bg-foreground font-semibold text-background'
                      : 'border-border bg-card font-[550] text-secondary-foreground hover:bg-secondary',
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-1 text-[10.5px] text-muted-foreground">先选一个案件，这里会列出它的槽位</p>
          )}
        </div>

        {/* 第 3 步：确认，带进度 */}
        <div>
          <div className="text-[10px] text-muted-foreground">3. 确认并归案</div>
          <InsetBlock className="mt-1">
            <div className="text-[11px]">
              {picked && slot ? (
                <>
                  「{subject}」→ <span className="font-medium">{picked.name}</span> · {slot}
                </>
              ) : (
                <span className="text-muted-foreground">尚未选齐案件与槽位</span>
              )}
            </div>
            {assign.phase !== 'idle' ? (
              <div className="mt-2">
                <div className="h-[5px] overflow-hidden rounded-full bg-secondary">
                  <div
                    className={cn(
                      'h-full rounded-full transition-[width] duration-200',
                      assign.phase === 'done' ? 'bg-status-green' : 'bg-foreground',
                    )}
                    style={{ width: `${assign.percent}%` }}
                  />
                </div>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span className="min-w-0 flex-1 truncate">
                    {assign.phase === 'done'
                      ? `已归入「${picked?.name ?? ''}」· ${slot}，缺件检测已重跑`
                      : assign.progress || '准备中…'}
                  </span>
                  <span className="tabular-nums">{assign.percent}%</span>
                </div>
                {assign.log.length > 0 ? (
                  <ul className="mt-1.5 flex flex-col gap-0.5">
                    {assign.log.slice(-3).map((l) => (
                      <li key={`${l.at}-${l.text}`} className="truncate text-[10px] text-muted-foreground">
                        <span className="tabular-nums opacity-70">{l.at}</span> {l.text}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </InsetBlock>
        </div>
      </div>
    </DetailDrawer>
  )
}
