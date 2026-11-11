// @vitest-environment jsdom
/**
 * 立案会话共用呈现单测（jsdom）。
 *
 * 这一份被 OA 立案与一张网立案两侧共用，是「后台到底跑成什么样」的唯一出口：
 * - PHASE_META：轮询阶段 → 语气 / 文案（idle..timeout 五种全覆盖）
 * - pillTone：把 StatusBadge 的 Tone 窄化成 Pill 接受的五种
 * - SessionResult：idle 不渲染；失败展示后端原话；超时给「别重复提交」的告警
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PHASE_META, SessionResult, pillTone } from './filing-session'

describe('PHASE_META', () => {
  it('五个阶段各有语气与文案，一句都不重复', () => {
    const phases = ['idle', 'submitting', 'running', 'done', 'timeout'] as const
    expect(Object.keys(PHASE_META).sort()).toEqual([...phases].sort())

    expect(PHASE_META.idle).toEqual({ tone: 'neutral', text: '待启动' })
    expect(PHASE_META.submitting).toEqual({ tone: 'blue', text: '正在提交' })
    expect(PHASE_META.running).toEqual({ tone: 'blue', text: '执行中' })
    // done 是中性色：终态不预设成功或失败，成败看后端 status
    expect(PHASE_META.done).toEqual({ tone: 'neutral', text: '已结束' })
    expect(PHASE_META.timeout).toEqual({ tone: 'yellow', text: '等待超时' })

    const texts = phases.map((p) => PHASE_META[p].text)
    expect(new Set(texts).size).toBe(phases.length)
  })
})

describe('pillTone', () => {
  it('purple 窄化成 neutral（Pill 不收 purple），其余原样透传', () => {
    expect(pillTone('purple')).toBe('neutral')
    expect(pillTone('green')).toBe('green')
    expect(pillTone('red')).toBe('red')
    expect(pillTone('yellow')).toBe('yellow')
    expect(pillTone('blue')).toBe('blue')
    expect(pillTone('neutral')).toBe('neutral')
  })
})

describe('SessionResult', () => {
  it('idle 阶段什么都不渲染（还没提交过，不该占屏）', () => {
    const { container } = render(<SessionResult error={null} status="" phase="idle" hint="立案" />)
    expect(container.firstChild).toBeNull()
  })

  it('非 idle 就显示后端原始 status（前端不翻译语义）', () => {
    render(<SessionResult error={null} status="running" phase="running" hint="立案" />)
    expect(screen.getByText('会话状态')).toBeTruthy()
    expect(screen.getByText('running')).toBeTruthy()
  })

  it('后端没回 status 时显示「（未返回）」，不留空胶囊', () => {
    render(<SessionResult error={null} status="" phase="submitting" hint="立案" />)
    expect(screen.getByText('（未返回）')).toBeTruthy()
  })

  it('有 error 时把「<hint>失败：<后端原话>」整句摆出来', () => {
    render(<SessionResult error="OA 凭证未配置" status="failed" phase="done" hint="立案" />)
    expect(screen.getByText('立案失败：OA 凭证未配置')).toBeTruthy()
  })

  it('没有 error 时不出现「失败」字样（不能把正常结束说成失败）', () => {
    render(<SessionResult error={null} status="success" phase="done" hint="立案" />)
    expect(screen.queryByText(/失败/)).toBeNull()
  })

  it('timeout 阶段给出「可能仍在后台跑、别重复提交」的告警', () => {
    render(<SessionResult error={null} status="running" phase="timeout" hint="立案" />)
    expect(screen.getByText(/等待超过 15 分钟仍未结束/)).toBeTruthy()
    expect(screen.getByText(/不要重复提交/)).toBeTruthy()
  })

  it('非 timeout 阶段不出现超时告警', () => {
    render(<SessionResult error={null} status="running" phase="running" hint="立案" />)
    expect(screen.queryByText(/等待超过 15 分钟/)).toBeNull()
  })

  it('超时同时带 error 时两块都在（失败原因 + 超时提醒各有各的信息）', () => {
    render(<SessionResult error="最后一次查询失败" status="running" phase="timeout" hint="盖章" />)
    expect(screen.getByText('盖章失败：最后一次查询失败')).toBeTruthy()
    expect(screen.getByText(/不要重复提交/)).toBeTruthy()
  })
})
