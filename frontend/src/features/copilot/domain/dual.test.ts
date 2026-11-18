/**
 * 同题双答的纯逻辑：事件分流键、栏标签、转录分组。
 *
 * 这三块错了都不会报错，只会「看起来正常但内容不对」：分错栏 → 两栏内容一样；
 * 标签错 → 律师以为在看两个不同模型的意见；分组错 → 双答被渲染成单栏。
 */

import { describe, expect, it } from 'vitest'

import { agentLabel, agentOf, DEFAULT_AGENT_KIND, groupAnswerRuns, runIdOf } from './dual'
import type { ChatMessage } from '../types'

describe('agentOf（事件 → 栏）', () => {
  it('带 agent 的事件原样取用', () => {
    expect(agentOf({ type: 'delta', content: 'x', agent: 'dsh' })).toBe('dsh')
  })

  it('缺 agent 时按 pi 处理（旧数据口径）', () => {
    // 引入 agent 字段之前的后端事件、以及单后端轮次都可能没有它
    expect(agentOf({ type: 'delta', content: 'x' })).toBe(DEFAULT_AGENT_KIND)
  })

  it('空串 agent 同样按 pi 处理（不当成「无来源」）', () => {
    expect(agentOf({ type: 'delta', agent: '' })).toBe(DEFAULT_AGENT_KIND)
  })
})

describe('runIdOf', () => {
  it('带 run_id 时原样返回', () => {
    expect(runIdOf({ run_id: 's-1:pi:1' })).toBe('s-1:pi:1')
  })

  it('缺 run_id 时返回空串（不抛、不编造）', () => {
    expect(runIdOf({ type: 'delta' })).toBe('')
  })
})

describe('agentLabel', () => {
  it('已知 kind 给中文/产品名', () => {
    expect(agentLabel('pi')).toBe('Pi')
    expect(agentLabel('dsh')).toBe('DeepSeek Harness')
  })

  it('未知 kind 直接显示 kind 本身（新后端不至于显示成空白）', () => {
    expect(agentLabel('claude')).toBe('claude')
  })
})

describe('groupAnswerRuns（转录 → 渲染项）', () => {
  const user = (id: string): ChatMessage => ({ id, role: 'user', content: '问' })
  const answer = (id: string, agentKind?: string): ChatMessage => ({
    id,
    role: 'assistant',
    content: '答',
    ...(agentKind ? { agentKind } : {}),
  })

  it('单条 assistant 也成组（调用方一个形状处理）', () => {
    const groups = groupAnswerRuns([user('u1'), answer('a1')])
    expect(groups.map((g) => g.answers.map((a) => a.id))).toEqual([['u1'], ['a1']])
  })

  it('相邻的两条 assistant 合成一组（双答）', () => {
    const groups = groupAnswerRuns([user('u1'), answer('a1', 'pi'), answer('a2', 'dsh')])
    expect(groups).toHaveLength(2)
    expect(groups[1]!.answers.map((a) => a.agentKind)).toEqual(['pi', 'dsh'])
  })

  it('被用户消息隔开的两条 assistant 不合并（不是同一轮）', () => {
    const groups = groupAnswerRuns([answer('a1', 'pi'), user('u1'), answer('a2', 'dsh')])
    expect(groups.map((g) => g.answers.length)).toEqual([1, 1, 1])
  })

  it('tool 行打断 assistant 相邻：不把工具行吞进双答栏', () => {
    const tool: ChatMessage = { id: 't1', role: 'tool', content: '', toolName: 'x' }
    const groups = groupAnswerRuns([answer('a1', 'pi'), tool, answer('a2', 'dsh')])
    expect(groups.map((g) => g.answers[0]!.role)).toEqual(['assistant', 'tool', 'assistant'])
  })

  it('空转录返回空（不造空组）', () => {
    expect(groupAnswerRuns([])).toEqual([])
  })
})
