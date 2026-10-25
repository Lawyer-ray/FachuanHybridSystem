import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { confirmParty, uploadContract } from '../api'
import { partyLabel, recommendParty, type PartyKey } from '../domain'

/**
 * 发起审查抽屉。
 *
 * **顺序很重要**：先定立场、选范围、写交代，再让 AI 跑。
 * 反过来的旧形态（AI 已按某个立场算完再问「是吧？」）会因为立场选错而整批返工——
 * 同一份合同站甲方还是乙方，建议方向是相反的。
 */

export type RepresentedParty = PartyKey

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
  clientName,
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
  /**
   * 调用方已知的当事人（可空）。
   *
   * **不再作为唯一来源**：合同可能有甲乙丙丁四方，我方也不一定是甲方
   * （常见「代表客户股东去审」），所以真正的立场选项以**上传后 AI 识别
   * 的结果**为准，这里只用于首屏占位与兜底。
   */
  parties?: Record<string, string>
  /** 我方委托客户名：用于从识别结果里自动推荐「我方是哪一方」 */
  clientName?: string
  partyHint?: string
}) {
  /**
   * 上传后识别出的当事人（`party_a`…`party_d` → 名称）。
   *
   * 初始为空：立场不该在「还没看到合同」时就定死。识别完成后才有选项，
   * 避免把「我方=甲方」这种假设写死——真实场景里有乙方、丙方，
   * 甚至有代表客户股东去审的。
   */
  const [detectedParties, setDetectedParties] = useState<Record<string, string> | null>(null)
  /** 上传状态：idle → uploading → ready | error */
  const [phase, setPhase] = useState<'idle' | 'uploading' | 'ready' | 'error'>('idle')
  /** 上传得到的 taskId（确认立场时复用，不重复上传） */
  const [taskId, setTaskId] = useState<string | null>(null)
  /** 选中的立场；识别完成前为 null */
  const [party, setParty] = useState<RepresentedParty | null>(null)
  const [steps, setSteps] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {}
    for (const s of STEPS) init[s.key] = s.on
    return init
  })
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  /**
   * 打开抽屉即上传并识别当事人（两阶段流程的第一阶段）。
   *
   * **为什么必须先识别再选立场**：立场决定全部建议方向。合同可能是甲乙丙丁
   * 四方、我方也可能是乙方甚至丙方（代表客户股东去审时更是如此）。先让律师
   * 看着「甲方/乙方」两个空标签选，等于让他猜；识别完再选，他看到的是真实
   * 当事人名称。
   */
  /**
   * 上传只跑一次的守卫。
   *
   * **不能把 phase 放进依赖**：`setPhase('uploading')` 会改变 phase → effect
   * 重跑 → cleanup 把 cancelled 置 true → 异步结果被丢弃，界面永远停在
   * 「正在识别」。用 ref 做守卫，依赖只留真正决定「要不要重新识别」的输入。
   */
  const runningRef = useRef(false)

  useEffect(() => {
    if (!open) {
      // 关闭即复位：下次打开换了一份合同，不能沿用上一份的识别结果
      runningRef.current = false
      setPhase('idle')
      setDetectedParties(null)
      setTaskId(null)
      setParty(null)
      return
    }
    if (runningRef.current) return
    runningRef.current = true

    let cancelled = false
    setPhase('uploading')
    void (async () => {
      try {
        const bytes = await loadFile()
        const file = new File([bytes], fileName, {
          type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        })
        const task = await uploadContract(file)
        if (cancelled) return

        // 只保留识别到的方：空值不渲染，丙丁没出现就不占位
        const found: Record<string, string> = {}
        for (const [k, v] of Object.entries(task.parties ?? {})) {
          if (v?.trim()) found[k] = v.trim()
        }
        setDetectedParties(found)
        setTaskId(task.task_id)

        // 自动推荐我方：用委托客户名去匹配某一方；匹配不上就留空让律师选
        const guess = recommendParty(found, clientName)
        setParty(guess)
        setPhase('ready')
      } catch (e) {
        if (cancelled) return
        setErr(e instanceof Error ? e.message : '读取合同失败')
        setPhase('error')
        runningRef.current = false // 允许重开抽屉重试
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, loadFile, fileName, clientName])

  /** 可选的立场项：识别结果优先，未识别时为空 */
  const partyOptions = useMemo(() => {
    const src = detectedParties ?? parties ?? {}
    return (['party_a', 'party_b', 'party_c', 'party_d'] as RepresentedParty[])
      .filter((k) => !!src[k]?.trim())
      .map((k) => ({ key: k, name: (src[k] ?? '').trim() }))
  }, [detectedParties, parties])

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
    if (!party || !taskId) {
      setErr('请先选择我方代表哪一方')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      // 上传已在打开抽屉时完成（第一阶段），这里只确认立场并触发流水线。
      // 交代必须真传：以前只弹个 toast，律师写的「一定要压工期」根本没进 prompt。
      await confirmParty(taskId, {
        represented_party: party,
        selected_steps: selected,
        reviewer_name: '法穿SI',
        client_note: note.trim(),
        client_demands: note
          .split(/[，,]/)
          .map((x) => x.trim())
          .filter(Boolean),
        our_client_name: partyOptions.find((o) => o.key === party)?.name ?? '',
        stance_basis: partyHint ?? '',
      })
      onStarted(taskId)
    } catch (e) {
      setErr(e instanceof Error ? e.message : '发起审查失败')
    } finally {
      setBusy(false)
    }
  }, [busy, steps, party, taskId, note, onStarted, partyOptions, partyHint])

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
            {phase === 'uploading' && (
              <div className="flex items-center gap-2 rounded-[8px] border border-border bg-secondary/40 px-3 py-2.5 text-[12px] text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                正在读取合同、识别当事人…
              </div>
            )}

            {phase === 'error' && (
              <div className="rounded-[8px] border border-destructive/30 bg-destructive/5 px-3 py-2 text-[11.5px] text-destructive">
                读取合同失败，无法识别当事人。请关闭后重试。
              </div>
            )}

            {phase === 'ready' && (
              <>
                <div className="flex flex-col gap-1.5">
                  {partyOptions.map((o) => (
                    <button
                      key={o.key}
                      type="button"
                      onClick={() => setParty(o.key)}
                      className={cn(
                        'flex items-center gap-2 rounded-[8px] border px-3 py-2 text-left text-[12.5px] transition-colors',
                        party === o.key
                          ? 'border-foreground bg-secondary/60'
                          : 'border-border bg-card hover:border-input',
                      )}
                    >
                      <b className="flex-none font-[600]">{partyLabel(o.key)}</b>
                      <span className="truncate text-secondary-foreground" title={o.name}>
                        {o.name}
                      </span>
                    </button>
                  ))}
                </div>

                {partyOptions.length === 0 && (
                  <div className="rounded-[8px] border border-border bg-secondary/40 px-3 py-2.5 text-[11.5px] leading-relaxed text-muted-foreground">
                    没有从合同里认出当事人（可能不是标准「甲方：…乙方：…」格式）。
                    请到复审台后手动指定我方立场。
                  </div>
                )}

                <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                  {party
                    ? `已选：${partyLabel(party)}`
                    : '请选择我方代表哪一方——决定全部建议方向，选错整批返工。'}
                  {partyHint ? ` ${partyHint}` : ''}
                </p>
              </>
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
            // 未选立场 / 还在识别 / 正在提交：三种情况下都不该让人点
            disabled={busy || !party || phase !== 'ready'}
          >
            {busy && <Loader2 className="size-3.5 animate-spin" />}
            {busy ? '正在发起…' : '开始审查'}
          </button>
        </div>
      </aside>
    </>
  )
}
