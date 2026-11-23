/**
 * 策展提升对话框的草稿状态与跨层派生值：目标层 / 团队 / 已选来源 / 规则正文 / 类型 /
 * 律所层确认。
 *
 * 从 `MemoryPromoteDialog` 拆出（后者单函数超软红线）。**跨层修正全在渲染期派生**
 * （不是 useEffect）：三条互相纠正的 effect 要多渲染一趟才收敛，还容易与候选查询的
 * enabled 判定错位；派生值同时用于显示与提交，保证「界面显示什么就提交什么」。
 *
 * 保留的唯一 effect 是「打开时落到第一个可策展目标」——它只是一次初始化。
 */

import { useEffect, useState } from 'react'

import type { MemoryKind, MemoryScopes } from '../../types'
import { LAW_FIRM_KINDS } from './labels'

export function usePromoteDraft({ open, scopes }: { open: boolean; scopes: MemoryScopes | undefined }) {
  const [target, setTarget] = useState<'team' | 'law_firm'>('team')
  const [pickedTeamId, setTeamId] = useState<number | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [content, setContent] = useState('')
  const [pickedKind, setKind] = useState<MemoryKind>('procedure')
  // 律所层影响全所，需显式确认（与后端 acknowledged_firm_wide 对应）
  const [firmAck, setFirmAck] = useState(false)

  const curatableTeams = scopes?.teams.filter((t) => t.can_curate) ?? []
  const canFirm = scopes?.law_firm.can_curate ?? false
  const firstTeamId = curatableTeams[0]?.id ?? null

  // 唯一保留的 effect：打开时落到第一个可策展目标，避免律师先看一个空面板。
  // 依赖里刻意不带 curatableTeams——否则 scopes 一到就重跑，把律师已选的团队冲掉。
  useEffect(() => {
    if (!open) return
    if (firstTeamId !== null) {
      setTarget('team')
      setTeamId((prev) => prev ?? firstTeamId)
    } else if (canFirm) {
      setTarget('law_firm')
      setTeamId(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // 三条跨层修正都在渲染期派生：律所层不带 teamId（后端按 scope 校验，混传会被拒）、
  // 律所层不允许「事实」（非法类型拉回惯例）、离开律所层不认之前的确认
  // （避免「在团队层勾过、切到律所层后忘了」这种假确认）
  const teamId = target === 'law_firm' ? null : (pickedTeamId ?? firstTeamId)
  const kind = target === 'law_firm' && !LAW_FIRM_KINDS.includes(pickedKind) ? 'procedure' : pickedKind
  const effectiveFirmAck = target === 'law_firm' && firmAck

  /** 换目标：换团队/换层都要清空已选（旧候选的 id 不属于新池） */
  const changeTarget = (next: 'team' | 'law_firm', nextTeamId: number | null) => {
    setTarget(next)
    setTeamId(nextTeamId)
    setSelected([])
  }

  const toggleSelected = (id: string, checked: boolean) => {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((item) => item !== id)))
  }

  return {
    target,
    teamId,
    canFirm,
    kind,
    setKind,
    content,
    setContent,
    selected,
    toggleSelected,
    firmAck: effectiveFirmAck,
    setFirmAck,
    changeTarget,
  }
}
