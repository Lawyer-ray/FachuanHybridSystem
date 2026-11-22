/**
 * 多答的纯逻辑：事件分流键、栏标签、转录分组、同栏合并、栏数上限。
 *
 * 这几块错了都不会报错，只会「看起来正常但内容不对」：分错栏 → 各栏内容一样；
 * 标签错 → 律师以为在看两个不同模型的意见；分组/合并错 → 一轮被渲染成 1 栏或
 * 凭空多出一栏。
 */

import { describe, expect, it } from 'vitest'

import {
  agentLabel,
  agentOf,
  attachedToolIds,
  DEFAULT_AGENT_KIND,
  groupAnswerRuns,
  MAX_ANSWERS,
  mergeAgentAnswers,
  runIdOf,
} from './dual'
import type { CitationRef } from './knowledge'
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

  it('相邻的两条 assistant 合成一组（多答）', () => {
    const groups = groupAnswerRuns([user('u1'), answer('a1', 'pi'), answer('a2', 'dsh')])
    expect(groups).toHaveLength(2)
    expect(groups[1]!.answers.map((a) => a.agentKind)).toEqual(['pi', 'dsh'])
  })

  it('被用户消息隔开的两条 assistant 不合并（不是同一轮）', () => {
    const groups = groupAnswerRuns([answer('a1', 'pi'), user('u1'), answer('a2', 'dsh')])
    expect(groups.map((g) => g.answers.length)).toEqual([1, 1, 1])
  })

  it('tool 行不打断同一轮：一轮 = 一段连续的非 user 消息', () => {
    // **这条曾经断言的是相反的结果**（`['assistant','tool','assistant']`，即工具
    // 各自成组）。那个行为就是用户报的两个 bug 的成因：
    //   1. 工具单独成组 → 走「单条」分支 → 全宽 ToolRow 堆在底部，分不清谁查的；
    //   2. assistant 被工具隔开 → 三个 agent 被切成多组 → 刷新后 3 栏变 2 栏。
    // 真实的落库顺序是**交错**的（工具先于正文），所以「连续 assistant」这个前提
    // 本身就不成立。现在按轮次语义切：工具属于它那一轮，组内再按 agentKind 分栏。
    const tool: ChatMessage = { id: 't1', role: 'tool', content: '', toolName: 'x', agentKind: 'pi' }
    const groups = groupAnswerRuns([answer('a1', 'pi'), tool, answer('a2', 'dsh')])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.answers.map((m) => m.role)).toEqual(['assistant', 'tool', 'assistant'])
  })

  it('user 消息始终是轮次边界', () => {
    const tool: ChatMessage = { id: 't1', role: 'tool', content: '', toolName: 'x', agentKind: 'pi' }
    const groups = groupAnswerRuns([answer('a1', 'pi'), tool, user('u1'), answer('a2', 'dsh')])
    // 前三条（assistant + tool）一轮；user 自己一组；后面一条又开始一轮
    expect(groups.map((g) => g.answers.length)).toEqual([2, 1, 1])
    expect(groups[1]!.answers[0]!.role).toBe('user')
  })

  it('空转录返回空（不造空组）', () => {
    expect(groupAnswerRuns([])).toEqual([])
  })
})

describe('MAX_ANSWERS（与后端同口径的上限）', () => {
  it('上限是 4：成本线性增长，四栏并排已是可读性极限', () => {
    expect(MAX_ANSWERS).toBe(5)
  })
})

describe('mergeAgentAnswers（同栏多段合成一条）', () => {
  const answer = (id: string, agentKind: string, content: string, extra?: Partial<ChatMessage>): ChatMessage => ({
    id,
    role: 'assistant',
    content,
    agentKind,
    ...extra,
  })

  it('同一个 agent 的多段拼成一条，位置取首次出现处', () => {
    const merged = mergeAgentAnswers(
      [answer('a1', 'pi', '前段'), answer('a2', 'dsh', '次答'), answer('a3', 'pi', '后段')],
      ['pi', 'dsh'],
    )
    expect(merged.map((m) => m.agentKind)).toEqual(['pi', 'dsh'])
    expect(merged[0]!.content).toBe('前段后段')
    expect(merged[1]!.content).toBe('次答')
  })

  it('思考过程一并拼接；任一段在流则合并结果仍在流', () => {
    const merged = mergeAgentAnswers(
      [
        answer('a1', 'pi', '正文1', { thinking: '想1', streaming: true }),
        answer('a2', 'pi', '正文2', { thinking: '想2' }),
      ],
      ['pi'],
    )
    expect(merged).toHaveLength(1)
    expect(merged[0]!.thinking).toBe('想1想2')
    expect(merged[0]!.streaming).toBe(true)
  })

  it('只有一段时原样返回同一个对象（不白造新对象，memo 才能 bail out）', () => {
    const only = answer('a1', 'pi', '正文')
    expect(mergeAgentAnswers([only], ['pi'])[0]).toBe(only)
  })

  it('栏清单之外的 agent 不参与合并（各成一条，不擅自拼接）', () => {
    const merged = mergeAgentAnswers(
      [answer('a1', 'pi', 'A'), answer('a2', 'oai', 'B'), answer('a3', 'oai', 'C')],
      ['pi', 'dsh'],
    )
    expect(merged.map((m) => m.id)).toEqual(['a1', 'a2', 'a3'])
  })

  it('栏清单为空时原样返回（不知道本轮跑了几家就不动转录）', () => {
    const answers = [answer('a1', 'pi', 'A'), answer('a2', 'pi', 'B')]
    expect(mergeAgentAnswers(answers, [])).toBe(answers)
  })

  it('缺 agentKind 的旧数据按 pi 合并（与渲染口径一致）', () => {
    const merged = mergeAgentAnswers(
      [{ id: 'a1', role: 'assistant', content: '旧1' }, { id: 'a2', role: 'assistant', content: '旧2' }],
      ['pi'],
    )
    expect(merged).toHaveLength(1)
    expect(merged[0]!.content).toBe('旧1旧2')
  })
})

describe('mergeAgentAnswers：同栏多段不丢字段', () => {
  // `...prev` 合并只保前段字段：后段的 citations / truncated / failed 会静默丢失，
  // 表现为栏头徽标少算引用、被停过的那一段看不出截断。
  const answer = (id: string, agentKind: string, content: string, extra?: Partial<ChatMessage>): ChatMessage => ({
    id,
    role: 'assistant',
    content,
    agentKind,
    ...extra,
  })
  const cite = (citeNo: number, name: string): CitationRef => ({ citeNo, kind: 'file', name })

  it('两段都有 citations：取并集、按 citeNo 去重、顺序按首次出现', () => {
    const merged = mergeAgentAnswers(
      [
        answer('a1', 'pi', '前段', { citations: [cite(1, '甲.pdf'), cite(2, '乙.pdf')] }),
        answer('a2', 'pi', '后段', { citations: [cite(2, '乙.pdf（补页码）'), cite(3, '丙.pdf')] }),
      ],
      ['pi'],
    )
    expect(merged).toHaveLength(1)
    expect(merged[0]!.content).toBe('前段后段')
    expect(merged[0]!.citations?.map((citation) => citation.citeNo)).toEqual([1, 2, 3])
    // 同号后到为准（与 mergeCitations 同口径：补页码/原文时不会丢）
    expect(merged[0]!.citations?.[1]?.name).toBe('乙.pdf（补页码）')
  })

  it('只有后段带引用也不丢（`...prev` 时代会整批丢掉）', () => {
    const merged = mergeAgentAnswers(
      [answer('a1', 'pi', '前段'), answer('a2', 'pi', '后段', { citations: [cite(4, '丁.pdf')] })],
      ['pi'],
    )
    expect(merged[0]!.citations?.map((citation) => citation.name)).toEqual(['丁.pdf'])
  })

  it('只有前段带引用时保留（不会被后段的缺省覆盖）', () => {
    const merged = mergeAgentAnswers(
      [answer('a1', 'pi', '前段', { citations: [cite(1, '甲.pdf')] }), answer('a2', 'pi', '后段')],
      ['pi'],
    )
    expect(merged[0]!.citations?.map((citation) => citation.citeNo)).toEqual([1])
  })

  it('truncated / failed 任一为真即真（任一段被截/失败，整栏都要标）', () => {
    const forward = mergeAgentAnswers(
      [answer('a1', 'pi', '前段', { truncated: true }), answer('a2', 'pi', '后段')],
      ['pi'],
    )
    expect(forward[0]!.truncated).toBe(true)

    const backward = mergeAgentAnswers(
      [answer('a1', 'pi', '前段'), answer('a2', 'pi', '后段', { failed: true })],
      ['pi'],
    )
    expect(backward[0]!.failed).toBe(true)
  })

  it('两段都没有时不凭空写 false / 空数组（缺字段 = 没引 / 旧数据）', () => {
    const merged = mergeAgentAnswers([answer('a1', 'pi', 'A'), answer('a2', 'pi', 'B')], ['pi'])
    expect('citations' in merged[0]!).toBe(false)
    expect('truncated' in merged[0]!).toBe(false)
    expect('failed' in merged[0]!).toBe(false)
  })
})

describe('多答：工具调用归到各自的栏', () => {
  // 真实反馈（2026-11-19 截图）：三轮 agent 同时调工具时，转录里这些 tool 消息
  // 交错相邻，平铺渲染成一坨分不清谁的工具条，还占满整行。修复后每个 agent 的
  // 工具挂在它自己的回答下面。
  const mk = (id: string, role: ChatMessage['role'], agentKind?: string, extra = {}) =>
    ({ id, role, content: '', agentKind, ...extra }) as ChatMessage

  it('每个 agent 的工具只挂在自己那栏', () => {
    const messages: ChatMessage[] = [
      mk('t1', 'tool', 'pi', { toolName: 'get_current_user' }),
      mk('t2', 'tool', 'dsh', { toolName: 'tool_search' }),
      mk('t3', 'tool', 'pi', { toolName: 'list_lawyers' }),
      mk('a1', 'assistant', 'pi', { content: '我是 pi' }),
      mk('a2', 'assistant', 'dsh', { content: '我是 dsh' }),
    ]

    const merged = mergeAgentAnswers(messages, ['pi', 'dsh'])

    // 只剩两栏（工具不再各自成组平铺）
    expect(merged).toHaveLength(2)
    const pi = merged.find((m) => m.agentKind === 'pi')!
    const dsh = merged.find((m) => m.agentKind === 'dsh')!
    // pi 有两个工具、dsh 有一个，互不串栏
    expect(pi.tools?.map((t) => t.toolName)).toEqual(['get_current_user', 'list_lawyers'])
    expect(dsh.tools?.map((t) => t.toolName)).toEqual(['tool_search'])
  })

  it('工具按到达顺序保留（不重排）', () => {
    const messages: ChatMessage[] = [
      mk('t1', 'tool', 'pi', { toolName: 'a' }),
      mk('t2', 'tool', 'pi', { toolName: 'b' }),
      mk('t3', 'tool', 'pi', { toolName: 'c' }),
      mk('a1', 'assistant', 'pi', { content: 'x' }),
      mk('a2', 'assistant', 'dsh', { content: 'y' }),
    ]
    const merged = mergeAgentAnswers(messages, ['pi', 'dsh'])
    expect(merged[0]!.tools?.map((t) => t.toolName)).toEqual(['a', 'b', 'c'])
  })

  it('只有工具没有正文的栏不会多出一坨无主工具条', () => {
    // 某栏工具跑了但正文还没到（流式中）——工具已经挂到 byAgent 以待合并，
    // 不该在结果里再出现一条游离的 tool 消息。
    const messages: ChatMessage[] = [
      mk('t1', 'tool', 'pi', { toolName: 'x' }),
      mk('a1', 'assistant', 'pi', { content: 'pi 的话' }),
      mk('a2', 'assistant', 'dsh', { content: 'dsh 的话' }),
    ]
    const merged = mergeAgentAnswers(messages, ['pi', 'dsh'])
    expect(merged.filter((m) => m.role === 'tool')).toHaveLength(0)
  })
})

describe('attachedToolIds / 归位后不再平铺', () => {
  // 正文未到时，未完成的工具行如果既挂在栏的 tools 上、又作为转录流独立行渲染，
  // 界面上就是「气泡里一条『正在查 XX』+ 外面一条『调用中 · XX』」——两处重复，
  // 正是本次要消灭的形状。
  const mk = (id: string, role: ChatMessage['role'], agentKind?: string, extra = {}) =>
    ({ id, role, content: '', agentKind, ...extra }) as ChatMessage

  it('未完成的工具也挂到栏上，且不再作为独立 tool 行出现', () => {
    const messages: ChatMessage[] = [
      mk('t1', 'tool', 'pi', { toolName: 'get_current_user' }),
      mk('t2', 'tool', 'dsh', { toolName: 'tool_search' }),
      mk('a1', 'assistant', 'pi', { content: '', streaming: true }),
      mk('a2', 'assistant', 'dsh', { content: '', streaming: true }),
    ]
    const merged = mergeAgentAnswers(messages, ['pi', 'dsh'])

    // 两条工具都已归位：转录流里不再有 tool 行（单栏那条路径不受影响）
    expect(merged.filter((m) => m.role === 'tool')).toHaveLength(0)
    expect(merged[0]!.tools?.map((t) => t.id)).toEqual(['t1'])
    expect(merged[1]!.tools?.map((t) => t.id)).toEqual(['t2'])
  })

  it('attachedToolIds 收齐各栏 tools 的 id（Activity / chip 的同一份判据）', () => {
    const merged = mergeAgentAnswers(
      [
        mk('t1', 'tool', 'pi', { toolName: 'a' }),
        mk('t2', 'tool', 'dsh', { toolName: 'b', content: '结果' }),
        mk('a1', 'assistant', 'pi', { content: 'x' }),
        mk('a2', 'assistant', 'dsh', { content: 'y' }),
      ],
      ['pi', 'dsh'],
    )
    expect([...attachedToolIds(merged)].sort()).toEqual(['t1', 't2'])
  })

  it('单栏回答（没有 tools 字段）返回空集：历史工具行照旧平铺', () => {
    expect(attachedToolIds([{ id: 'a1', role: 'assistant', content: 'x' }]).size).toBe(0)
  })
})
