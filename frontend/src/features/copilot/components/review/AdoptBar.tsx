/**
 * 采纳条：采纳某一栏 / 标为合并 / 填理由 → `POST /agent/reviews/{id}/adopt`。
 *
 * ## 三条已经写进后端契约的语义
 *
 * 1. **采纳是独立记录，不是改 `Review`**：`Review` 是判定快照，不变；所以成功后
 *    只更新本条的本地回显，不整页重取评审（重取也拿不到采纳态）。
 * 2. **回显走 `GET .../adoption`**：刷新/重开面板时读回同一条记录；`adoption: null`
 *    与 404 都表示「还没人采纳」，是正常态——静默、不弹错、不阻塞渲染。
 * 3. **`lane === null && merged === true` 是「标为合并采纳」**：合并没有栏，文案里
 *    不能出现空栏名；`lane === null && merged === false` 不是有效裁决，映射层
 *    直接当没有记录（见 `domain/adoption`）。
 *
 * ## 影子模式
 *
 * 本批 `stage` 只有 `shadow`：采纳只落一条留痕，**不会**自动改写任何答案或文件。
 * 条上必须写明这一点，否则「已采纳」会被读成「已经按它改了」。
 */

import { useEffect, useState } from 'react'

import { adoptReview, fetchReviewAdoption } from '../../api'
import { adoptionSummary, toAdoptionView, type AdoptionView, type LaneView } from '../../domain'

const BUTTON_CLASS =
  'flex-none rounded-[4px] border border-border bg-background px-1.5 py-0.5 text-[11px] text-foreground/80 transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50'

export function AdoptBar({ reviewId, lanes }: { reviewId: string; lanes: LaneView[] }) {
  const [adoption, setAdoption] = useState<AdoptionView | null>(null)
  const [note, setNote] = useState('')
  const [adopting, setAdopting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setAdoption(null)
    fetchReviewAdoption(reviewId)
      .then((envelope) => {
        if (!cancelled) setAdoption(toAdoptionView(envelope.adoption))
      })
      // 404 = 还没有采纳记录（正常态）；网络失败同样降级为「没记录」
      .catch(() => {
        if (!cancelled) setAdoption(null)
      })
    return () => {
      cancelled = true
    }
  }, [reviewId])

  const submit = async (lane: string | null, merged: boolean) => {
    setAdopting(true)
    setError(null)
    try {
      const receipt = await adoptReview(reviewId, { lane, merged, note: note.trim() })
      const next = toAdoptionView(receipt)
      // 回执里既没选栏也没标合并：按契约不可能出现，按失败处理而不是静默
      if (!next) {
        setError('采纳失败：服务端回执没有有效的采纳对象')
        return
      }
      setAdoption(next)
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '采纳失败，请稍后重试')
    } finally {
      setAdopting(false)
    }
  }

  const labelOf = (lane: string) => lanes.find((item) => item.lane === lane)?.label ?? lane
  const summary = adoption ? adoptionSummary(adoption, labelOf) : ''

  return (
    <div data-testid="adopt-bar" className="mt-2 border-t border-border pt-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span
          className="flex-none text-[11px] text-muted-foreground"
          title="影子模式：采纳只落一条留痕记录，不会自动改写任何答案或文件"
        >
          裁决
        </span>
        {lanes.map((lane) => (
          <button
            key={lane.lane}
            type="button"
            disabled={adopting}
            aria-pressed={adoption?.lane === lane.lane}
            onClick={() => void submit(lane.lane, false)}
            className={BUTTON_CLASS}
          >
            采纳 {lane.label}
          </button>
        ))}
        <button
          type="button"
          disabled={adopting}
          aria-pressed={adoption?.lane === null && adoption.merged}
          onClick={() => void submit(null, true)}
          className={BUTTON_CLASS}
        >
          标为合并
        </button>
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          aria-label="采纳理由"
          placeholder="理由（可选，留痕用）"
          className="min-w-0 flex-1 rounded-[4px] border border-border bg-background px-1.5 py-0.5 text-[11px]"
        />
      </div>
      {summary && (
        <p data-testid="adopt-state" className="mt-1 text-[11px] text-muted-foreground">
          {summary}
          {adoption?.note ? ` · 理由：${adoption.note}` : ''}
          <span className="opacity-70">（影子模式：只留痕，不改写内容）</span>
        </p>
      )}
      {error && (
        <p role="alert" className="mt-1 text-[11px] text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
