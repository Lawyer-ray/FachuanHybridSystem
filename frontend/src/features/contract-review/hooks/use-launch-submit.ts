import { useCallback, useState } from 'react'

import { errMessage } from '@/lib/errors'
import { confirmParty } from '../api'
import { defaultStepToggles } from '../constants'
import type { PartyKey } from '../domain'

/**
 * 抽屉第三阶段：律师的勾选（步骤 + 特别交代）与提交。
 *
 * 与上传 hook 分开的原因：它们是两条独立的状态机，混在一个 effect 里正是
 * 旧实现 51 行 useEffect 的由来。提交只看「选了什么」和「上传给的 taskId」。
 */
export function useLaunchSubmit(params: {
  /** 上传阶段就绪时才有；确认立场复用它，不重复上传 */
  taskId: string | null
  /** 上传阶段自动推荐 / 律师点选的立场 */
  party: PartyKey | null
  setParty: (p: PartyKey) => void
  partyOptions: Array<{ key: PartyKey; name: string }>
  partyHint?: string
  onStarted: (taskId: string) => void
}) {
  const { taskId, party, setParty, partyOptions, partyHint, onStarted } = params

  const [steps, setSteps] = useState<Record<string, boolean>>(defaultStepToggles)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [submitErr, setSubmitErr] = useState<string | null>(null)

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
      setSubmitErr('至少选一项审查内容')
      return
    }
    if (!party || !taskId) {
      setSubmitErr('请先选择我方代表哪一方')
      return
    }
    setBusy(true)
    setSubmitErr(null)
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
      setSubmitErr(errMessage(e, '发起审查失败'))
    } finally {
      setBusy(false)
    }
  }, [busy, steps, party, taskId, note, onStarted, partyOptions, partyHint])

  return { steps, toggleStep, note, setNote, toggleChip, busy, submitErr, start, party, setParty }
}
