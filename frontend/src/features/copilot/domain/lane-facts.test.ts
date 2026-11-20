/**
 * 栏头体检事实（纯逻辑）。
 *
 * 必须成立的事实：
 * 1. **只算事实**：引用条数 / 是否核验 / 截断 / 失败 / 零工具都能从消息本身读出来，
 *    且没有一个是分数或评价；
 * 2. **不编数**：流式中的「还没有」不算事实，`citations` 缺失按 0 条计；
 * 3. **零数据不画**：没有任何可报事实时徽标正文是空串（栏头不许出现空方块）；
 * 4. **核验只认闭集**：名字里带 check 的无关工具（凭证检查、归档清单）不算核验。
 */

import { describe, expect, it } from 'vitest'

import type { AgentHistoryMessage, ChatMessage } from '../types'
import { distinctAgentKinds, groupAnswerRuns, mergeAgentAnswers } from './dual'
import { laneFactsBadge, laneFactsDetail, laneFactsOf } from './lane-facts'
import { historyToMessages } from './transcript'

function assistant(over: Partial<ChatMessage> = {}): ChatMessage {
  return { id: 'a-1', role: 'assistant', content: '答', agentKind: 'pi', ...over }
}

function tool(name: string): ChatMessage {
  return { id: `t-${name}`, role: 'tool', content: '{}', toolName: name, agentKind: 'pi' }
}

function citationsOf(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    citeNo: i + 1,
    kind: 'statute' as const,
    name: `《民法典》第${i + 1}条`,
  }))
}

describe('laneFactsOf（消息 → 事实）', () => {
  it('全空消息：五项都是「没有」，且已收尾；流式中不算收尾', () => {
    expect(laneFactsOf(assistant())).toEqual({
      citationCount: 0,
      verificationTools: [],
      toolCount: 0,
      truncated: false,
      failed: false,
      settled: true,
    })
    expect(laneFactsOf(assistant({ streaming: true })).settled).toBe(false)
  })

  it('引用/工具条数直接取数组长度（零工具是「查了 0 个」的数据源）', () => {
    expect(laneFactsOf(assistant({ citations: citationsOf(3) })).citationCount).toBe(3)
    expect(laneFactsOf(assistant({ tools: [tool('mcp__fachuan__search_cases'), tool('list_lawyers')] })).toolCount).toBe(2)
    expect(laneFactsOf(assistant({ tools: [] })).toolCount).toBe(0)
  })

  it('核验类工具带 mcp 前缀也认得出，同一个调两次只记一次', () => {
    const facts = laneFactsOf(
      assistant({
        tools: [
          tool('mcp__fachuan__verify_citations'),
          tool('verify_citations'),
          tool('mcp__fachuan__check_law_references'),
          tool('asean_law_verify'),
        ],
      }),
    )
    expect(facts.verificationTools).toEqual([
      'verify_citations',
      'check_law_references',
      'asean_law_verify',
    ])
    expect(facts.toolCount).toBe(4)
  })

  it('名字里带 check 的无关工具不算核验（只认闭集，不做模式匹配）', () => {
    const facts = laneFactsOf(
      assistant({ tools: [tool('check_oa_credential'), tool('get_archive_checklist'), tool('search_cases')] }),
    )
    expect(facts.verificationTools).toEqual([])
    expect(facts.toolCount).toBe(3)
  })

  it('截断 / 失败只认 true（透传三态里 undefined 是「没这个记录」）', () => {
    expect(laneFactsOf(assistant({ truncated: true })).truncated).toBe(true)
    expect(laneFactsOf(assistant({ failed: true })).failed).toBe(true)
    expect(laneFactsOf(assistant({ truncated: undefined })).truncated).toBe(false)
  })

  it('字段是闭集：不出现分数/评级这类评价性字段', () => {
    expect(Object.keys(laneFactsOf(assistant())).sort()).toEqual([
      'citationCount',
      'failed',
      'settled',
      'toolCount',
      'truncated',
      'verificationTools',
    ])
  })
})

describe('laneFactsBadge（栏头正文）', () => {
  it('零数据不画：没引用、没工具、没截断/失败 → 空串（不许出现空方块）', () => {
    expect(laneFactsBadge(laneFactsOf(assistant()))).toBe('')
    expect(laneFactsBadge(laneFactsOf(assistant({ streaming: true })))).toBe('')
  })

  it('引用条数 + 核验；查了工具却没引来源 → 明写「无引」；有引用没调工具 → 「无工具」', () => {
    const cited = laneFactsOf(
      assistant({ citations: citationsOf(3), tools: [tool('mcp__fachuan__verify_citations')] }),
    )
    expect(laneFactsBadge(cited)).toBe('引 3 · 核验')
    expect(laneFactsBadge(laneFactsOf(assistant({ tools: [tool('search_cases')] })))).toBe('无引')
    expect(laneFactsBadge(laneFactsOf(assistant({ citations: citationsOf(2) })))).toBe('引 2 · 无工具')
  })

  it('截断与引用并列写；被截断时不写「无引/无工具」（没跑完，数还在路上）', () => {
    const cut = laneFactsOf(
      assistant({ truncated: true, citations: citationsOf(1), tools: [tool('search_cases')] }),
    )
    expect(laneFactsBadge(cut)).toBe('截断 · 引 1')
    expect(laneFactsBadge(laneFactsOf(assistant({ truncated: true })))).toBe('截断')
  })

  it('失败栏只说「未做」（其余三项是没跑起来的副产品，列出来像在给空栏打分）', () => {
    expect(laneFactsBadge(laneFactsOf(assistant({ failed: true })))).toBe('未做')
    const failedWithData = assistant({ failed: true, truncated: true, citations: citationsOf(1) })
    expect(laneFactsBadge(laneFactsOf(failedWithData))).toBe('未做')
  })

  it('流式中的缺席不写，已经在长的引用照常显示', () => {
    expect(
      laneFactsBadge(laneFactsOf(assistant({ streaming: true, tools: [tool('search_cases')] }))),
    ).toBe('')
    expect(
      laneFactsBadge(laneFactsOf(assistant({ streaming: true, citations: citationsOf(1) }))),
    ).toBe('引 1')
  })
})

describe('laneFactsDetail（悬停明细）', () => {
  it('把缩写还原成完整一句（含 0 与核验工具名）', () => {
    const plain = laneFactsDetail(laneFactsOf(assistant({ tools: [tool('search_cases')] })))
    expect(plain).toContain('引用 0 条')
    expect(plain).toContain('未用核验工具')
    expect(plain).toContain('工具 1 个')
    const verified = laneFactsDetail(
      laneFactsOf(assistant({ tools: [tool('mcp__fachuan__verify_citations'), tool('asean_law_verify')] })),
    )
    expect(verified).toContain('核验工具 verify_citations / asean_law_verify')
  })

  it('截断写明可能不完整、流式写明还在累计、失败只写本轮未做', () => {
    expect(laneFactsDetail(laneFactsOf(assistant({ truncated: true })))).toContain('回答被截断')
    expect(laneFactsDetail(laneFactsOf(assistant({ streaming: true })))).toContain('仍在流式')
    expect(laneFactsDetail(laneFactsOf(assistant({ failed: true })))).toBe('本轮未做（该栏没跑成）')
  })

  it('明细里没有打分口径（评分/得分/质量/好/差）', () => {
    const detail = laneFactsDetail(
      laneFactsOf(assistant({ citations: citationsOf(2), tools: [tool('verify_citations')] })),
    )
    expect(detail).not.toMatch(/评分|得分|分数|质量|好|差/)
  })
})

/**
 * 刷新前后一致：事实只依赖消息字段，而历史回放把 citations / truncated 从落库
 * metadata 重建、工具按 agentKind 归位到各栏（与实时同一套 domain 变换）。所以
 * 同一轮的徽标文字在两条路径上必须逐字相同——否则「重开会话看到另一套体检」会让
 * 律师怀疑数据坏了。
 */
describe('刷新前后：事实来自消息本身', () => {
  it('同一轮三栏（有引用且核验 / 查了没引 / 被截断）在历史与实时得到同一行徽标', () => {
    // 落库形状：工具先于正文、两栏交错（真实顺序，见 multiagent-refresh.test.ts）
    const specs: Array<Pick<AgentHistoryMessage, 'role' | 'content'> & Partial<AgentHistoryMessage>> = [
      { role: 'user', content: '这份合同有效吗' },
      { role: 'tool', content: '{}', tool_name: 'mcp__fachuan__verify_citations', agent_kind: 'pi' },
      { role: 'tool', content: '{}', tool_name: 'mcp__fachuan__search_cases', agent_kind: 'dsh' },
      {
        role: 'assistant',
        content: '有引用的回答',
        agent_kind: 'pi',
        metadata: {
          citations: [
            { cite_no: 1, kind: 'statute', name: '《民法典》第577条' },
            { cite_no: 2, kind: 'case', name: '合成案号-样例' },
          ],
        },
      },
      { role: 'assistant', content: '查了没引的回答', agent_kind: 'dsh' },
      { role: 'assistant', content: '被停止的回答', agent_kind: 'openai-agents', metadata: { truncated: true } },
    ]
    const rows = specs.map((spec, index) => ({
      message_id: index + 1,
      tool_name: '',
      agent_kind: '',
      created_at: `2026-11-19T12:00:0${index}Z`,
      metadata: {},
      ...spec,
    }))

    // 只取最后一轮：AnswerGroupView 也是按轮分组后把一组 answers 交给
    // mergeAgentAnswers，整份转录不是它的输入
    const historical = historyToMessages(rows)
    const turn = groupAnswerRuns(historical).at(-1)!.answers
    const lanes = mergeAgentAnswers(turn, distinctAgentKinds(turn))
    const byKind = new Map(lanes.map((lane) => [lane.agentKind ?? '', lane]))
    const badges = (lane: ChatMessage) => laneFactsBadge(laneFactsOf(lane))
    expect(badges(byKind.get('pi')!)).toBe('引 2 · 核验')
    expect(badges(byKind.get('dsh')!)).toBe('无引')
    expect(badges(byKind.get('openai-agents')!)).toBe('截断')

    // 实时视图带同一份字段（引用 / 归位后的工具 / 截断）→ 同一行文字
    expect(badges(assistant({ citations: citationsOf(2), tools: [tool('mcp__fachuan__verify_citations')] }))).toBe(
      '引 2 · 核验',
    )
    expect(badges(assistant({ tools: [tool('mcp__fachuan__search_cases')] }))).toBe('无引')
    expect(badges(assistant({ truncated: true }))).toBe('截断')
  })
})
