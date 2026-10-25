import { useCallback, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { confirmParty, uploadContract } from '../api'

/**
 * 发起审查抽屉。
 *
 * **顺序很重要**：先定立场、选范围、写交代，再让 AI 跑。
 * 反过来的旧形态（AI 已按某个立场算完再问「是吧？」）会因为立场选错而整批返工——
 * 同一份合同站甲方还是乙方，建议方向是相反的。
 */

export type RepresentedParty = 'party_a' | 'party_b' | 'party_c' | 'party_d'

/** 审查步骤（对应后端 selected_steps） */
const STEPS: Array<{ key: string; label: string; desc: string; on: boolean }> = [
  { key: 'contract_review', label: '条款审查', desc: '付款 · 验收 · 违约 · 终止 · 争议解决', on: true },
  { key: 'typo_check', label: '错别字检测', desc: '逐段比对，产出以修订落盘', on: true },
  { key: 'review_report', label: '评估报告', desc: '整体风险摘要，供回给客户', on: true },
  { key: 'format_document', label: '格式规范化', desc: '字体 · 行距 · 缩进 · 页码 · 标题编号', on: false },
]

/** 常用交代 chips（写进 textarea，律师可继续编辑） */
const DEMAND_CHIPS = [
  { key: '压工期', text: '这单一定要压工期' },
  { key: '控预算', text: '预算不能再加' },
  { key: '别太硬', text: '别把话说太死' },
]

export function ReviewLaunchDrawer({
  open,
  onClose,
  onStarted,
  loadFile,
  fileName,
  partyHint,
  parties,
}: {
  open: boolean
  onClose: () => void
  /** 流水线已触发，带上 taskId 跳复审台 */
  onStarted: (taskId: string) => void
  /**
   * 取合同字节。调用方决定来源——可能是材料包附件（带票据的 preview 端点），
   * 也可能是合同文件夹里的文件（folder-file 端点），抽屉不关心。
   */
  loadFile: () => Promise<ArrayBuffer>
  fileName: string
  /** AI 从文档里认出的当事人，作为立场选项的展示名 */
  parties?: Record<string, string>
  partyHint?: string
}) {
  const [party, setParty] = useState<RepresentedParty>('party_a')
  const [steps, setSteps] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {}
    for (const s of STEPS) init[s.key] = s.on
    return init
  })
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const toggleStep = useCallback((key: string) => {
    setSteps((prev) => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const toggleChip = useCallback((text: string) => {
    setNote((prev) => {
      const parts = prev
        .split(/[，,]/)
        .map((x) => x.trim())
        .filter(Boolean)
      // 先看当前是否已含这一条（判断必须用原始 parts，不能用过滤后的 kept——
      // 那样 includes 永远为 false，chip 只能加不能取消）
      if (parts.includes(text)) {
        return parts.filter((x) => x !== text).join('，')
      }
      return [...parts, text].join('，')
    })
  }, [])

  const start = useCallback(async () => {
    if (busy) return
    const selected = Object.entries(steps)
      .filter(([, on]) => on)
      .map(([k]) => k)
    if (selected.length === 0) {
      setErr('至少选一项审查内容')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      // 取材 → 转 File → 上传（审查流水线只吃 docx）
      const bytes = await loadFile()
      const file = new File([bytes], fileName, {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const task = await uploadContract(file)
      // 立场 + 步骤 + 客户交代一起确认，触发异步流水线。
      // 交代必须真传：以前只弹个 toast，律师写的「一定要压工期」根本没进 prompt。
      await confirmParty(task.task_id, {
        represented_party: party,
        selected_steps: selected,
        reviewer_name: '法穿SI',
        client_note: note.trim(),
        client_demands: note
          .split(/[，,]/)
          .map((x) => x.trim())
          .filter(Boolean),
        our_client_name: parties?.[party] ?? '',
        stance_basis: partyHint ?? '',
      })
      onStarted(task.task_id)
    } catch (e) {
      setErr(e instanceof Error ? e.message : '发起审查失败')
    } finally {
      setBusy(false)
    }
  }, [busy, steps, loadFile, fileName, party, note, onStarted, parties, partyHint])

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-[96] bg-foreground/30" onClick={onClose} />
      <aside className="fixed inset-y-0 right-0 z-[97] flex w-[440px] max-w-[92vw] flex-col bg-card shadow-[-6px_0_32px_rgba(0,0,0,0.1)]">
        <div className="flex flex-none items-start gap-3 border-b border-border px-4.5 py-4">
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-[680]">发起审查</p>
            <p className="mt-0.5 truncate text-[12px] text-muted-foreground" title={fileName}>
              {fileName}
            </p>
          </div>
          <button
            type="button"
            className="grid size-7 flex-none place-items-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            onClick={onClose}
          >
            <X className="size-3.5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4.5">
          {err && (
            <div className="my-3 rounded-[8px] border border-destructive/30 bg-destructive/5 px-3 py-2 text-[11.5px] text-destructive">
              {err}
            </div>
          )}

          {/* ① 立场：决定全部建议方向，必须选 */}
          <section className="border-b border-border-light py-4">
            <div className="mb-2.5 flex items-center gap-2">
              <span className="grid size-[17px] flex-none place-items-center rounded-full bg-secondary text-[10px] font-bold text-secondary-foreground">
                1
              </span>
              <span className="text-[12.5px] font-[650]">我方代表谁？</span>
              <span className="ml-auto rounded-[5px] bg-status-yellow-bg px-1.5 py-0.5 text-[10px] font-[650] text-[#a16207]">
                决定全部建议方向
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              {(['party_a', 'party_b', 'party_c', 'party_d'] as RepresentedParty[]).map((p) => {
                const label = parties?.[p]
                if (p === 'party_c' && !label) return null
                if (p === 'party_d' && !label) return null
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setParty(p)}
                    className={cn(
                      'flex items-center gap-2 rounded-[8px] border px-3 py-2 text-left text-[12.5px] transition-colors',
                      party === p
                        ? 'border-foreground bg-secondary/60'
                        : 'border-border bg-card hover:border-input',
                    )}
                  >
                    <b className="font-[600]">
                      {p === 'party_a' ? '甲方' : p === 'party_b' ? '乙方' : p === 'party_c' ? '丙方' : '丁方'}
                    </b>
                    {label && <span className="truncate text-muted-foreground">{label}</span>}
                  </button>
                )
              })}
            </div>
            {partyHint && (
              <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{partyHint}</p>
            )}
          </section>

          {/* ② 审查内容 */}
          <section className="border-b border-border-light py-4">
            <div className="mb-2.5 flex items-center gap-2">
              <span className="grid size-[17px] flex-none place-items-center rounded-full bg-secondary text-[10px] font-bold text-secondary-foreground">
                2
              </span>
              <span className="text-[12.5px] font-[650]">审查哪些方面？</span>
            </div>
            <div className="flex flex-col gap-1.5">
              {STEPS.map((s) => (
                <label
                  key={s.key}
                  className={cn(
                    'flex cursor-pointer items-start gap-2.5 rounded-[8px] border px-2.5 py-2 transition-colors',
                    steps[s.key] ? 'border-input bg-secondary/60' : 'border-border bg-card hover:border-input',
                  )}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-foreground"
                    checked={!!steps[s.key]}
                    onChange={() => toggleStep(s.key)}
                  />
                  <span className="min-w-0 flex-1">
                    <b className="block text-[12.5px] font-[600]">{s.label}</b>
                    <em className="mt-0.5 block text-[11px] not-italic text-muted-foreground">
                      {s.desc}
                    </em>
                  </span>
                </label>
              ))}
            </div>
          </section>

          {/* ③ 特别交代 */}
          <section className="py-4">
            <div className="mb-2.5 flex items-center gap-2">
              <span className="grid size-[17px] flex-none place-items-center rounded-full bg-secondary text-[10px] font-bold text-secondary-foreground">
                3
              </span>
              <span className="text-[12.5px] font-[650]">特别交代</span>
              <span className="ml-auto text-[11px] text-muted-foreground/70">选填</span>
            </div>
            <textarea
              className="w-full resize-y rounded-[8px] border border-border bg-card px-2.5 py-2 text-[12.5px] leading-[1.6] outline-none focus:border-foreground"
              rows={3}
              placeholder="客户有没有特别在意的点？比如「这单一定要压工期，预算不能再加」"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {DEMAND_CHIPS.map((c) => {
                const on = note.includes(c.text)
                return (
                  <button
                    key={c.key}
                    type="button"
                    onClick={() => toggleChip(c.text)}
                    className={cn(
                      'rounded-full border px-2.5 py-1 text-[11px] transition-colors',
                      on
                        ? 'border-foreground bg-foreground text-background'
                        : 'border-border bg-card text-secondary-foreground hover:border-input',
                    )}
                  >
                    {c.text}
                  </button>
                )
              })}
            </div>
          </section>
        </div>

        <div className="flex flex-none justify-end gap-2 border-t border-border px-4.5 py-3.5">
          <button
            type="button"
            className="h-[31px] rounded-[8px] border border-border bg-card px-3 text-[12.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
            onClick={onClose}
            disabled={busy}
          >
            取消
          </button>
          <button
            type="button"
            className="inline-flex h-[31px] items-center gap-1.5 rounded-[8px] border border-foreground bg-foreground px-4 text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-60"
            onClick={() => void start()}
            disabled={busy}
          >
            {busy && <Loader2 className="size-3.5 animate-spin" />}
            {busy ? '正在发起…' : '开始审查'}
          </button>
        </div>
      </aside>
    </>
  )
}
