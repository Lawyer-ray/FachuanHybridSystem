/**
 * 回归：多 agent 会话「刷新后栅数变少 / 工具条混在一起」。
 *
 * 数据从**后端落库形状**（`GET /agent/sessions/{id}/messages` 的 `MessageOut`）出发，
 * 不先造一份整洁的 `ChatMessage[]`。真实会话 268 的落库顺序是交错的：
 *
 *     user
 *     tool(openai-agents) ×2
 *     assistant(pi)
 *     tool(openai-agents) ×2
 *     assistant(dsh)
 *     assistant(openai-agents)
 *
 * 旧分组按「连续 assistant」切轮次，于是 pi 被工具行隔开单独掉出去，
 * dsh + openai-agents 只成两栏，剩下的工具行各自成组、全宽堆在底部。
 *
 * 本文件只依赖 domain 的公开变换（`groupAnswerRuns` / `mergeAgentAnswers` /
 * `attachedToolIds` / `historyToMessages`），并按 `MessageList → AnswerGroupView`
 * 的渲染契约做一次纯函数化的「栅计划」——断言的是律师最终会看到几栏、每栏
 * 归属哪些工具，而不是实现内部怎么切数组。
 */

import { describe, expect, it } from 'vitest'

import type { AgentHistoryMessage, ChatMessage } from '../types'
import { attachedToolIds, DEFAULT_AGENT_KIND, groupAnswerRuns, mergeAgentAnswers } from './dual'
import { historyToMessages } from './transcript'

/** 后端 `MessageOut` 形状的构造器（只填测试关心的字段，其余给后端同款默认值） */
function rowsOf(
  specs: Array<Pick<AgentHistoryMessage, 'role' | 'content'> & Partial<AgentHistoryMessage>>,
): AgentHistoryMessage[] {
  return specs.map((spec, index) => ({
    message_id: index + 1,
    tool_name: '',
    agent_kind: '',
    created_at: `2026-11-19T12:00:${String(index).padStart(2, '0')}Z`,
    metadata: {},
    ...spec,
  }))
}

function kindOf(message: ChatMessage): string {
  return message.agentKind ?? DEFAULT_AGENT_KIND
}

/** 一轮的渲染计划：单栏按原顺序逐条平铺，多栏每栏一条 assistant（工具已挂上） */
type TurnPlan =
  | { mode: 'flat'; items: ChatMessage[] }
  | { mode: 'columns'; columns: ChatMessage[]; loose: ChatMessage[] }

/**
 * 把后端顺序的消息映射成「律师看到的栅」。
 *
 * 判据与渲染侧同口径：一组（一段连续的非 user 消息）里出现 **≥2 个不同的
 * assistant 来源**才分栅；只有一个来源时走引入多栅前的老路径（工具行平铺，
 * 不吸进气泡）。
 */
function renderPlan(messages: ChatMessage[]): TurnPlan[] {
  return groupAnswerRuns(messages).map((group) => {
    const kinds = [
      ...new Set(group.answers.filter((m) => m.role === 'assistant').map(kindOf)),
    ]
    if (kinds.length < 2) return { mode: 'flat', items: group.answers }
    const merged = mergeAgentAnswers(group.answers, kinds)
    return {
      mode: 'columns',
      columns: merged.filter((m) => m.role === 'assistant'),
      loose: merged.filter((m) => m.role !== 'assistant'),
    }
  })
}

function columnTurns(plan: TurnPlan[]): Array<Extract<TurnPlan, { mode: 'columns' }>> {
  return plan.filter((turn): turn is Extract<TurnPlan, { mode: 'columns' }> => turn.mode === 'columns')
}

/** 计划里所有实际可见的工具行（平铺项 + 各栏 tools + 未归位的 loose 行） */
function visibleTools(plan: TurnPlan[]): ChatMessage[] {
  const tools: ChatMessage[] = []
  for (const turn of plan) {
    if (turn.mode === 'flat') {
      tools.push(...turn.items.filter((m) => m.role === 'tool'))
      continue
    }
    tools.push(...turn.columns.flatMap((column) => column.tools ?? []))
    tools.push(...turn.loose.filter((m) => m.role === 'tool'))
  }
  return tools
}

/** 按 agent 取栏（忽略栏的左右顺序）：同一份数据刷新前后必须一一对应 */
function columnsByAgent(plan: TurnPlan[]): Record<string, { content: string; tools: string[] }> {
  const multi = columnTurns(plan)
  if (multi.length !== 1) return {}
  return Object.fromEntries(
    multi[0]!.columns.map((column) => [
      kindOf(column),
      {
        content: column.content,
        tools: (column.tools ?? []).map((tool) => `${kindOf(tool)}:${tool.toolName}`),
      },
    ]),
  )
}

/**
 * 实时（未刷新）的消息顺序：`store/turn.ts` 开流时先把本轮各栏 assistant
 * 气泡全部入列，工具消息在事件到达时才 append，所以工具都在气泡之后。
 * 与后端落库顺序（工具可能插在回答之间）不同，但渲染结果必须一致。
 */
function liveMessagesFrom(rows: AgentHistoryMessage[]): ChatMessage[] {
  const users = rows.filter((row) => row.role === 'user')
  const assistants = rows.filter((row) => row.role === 'assistant')
  const tools = rows.filter((row) => row.role === 'tool')
  // store/turn.ts：只有多栏才给 assistant 气泡登记 agentKind；单栏的 assistant
  // 保持「空 = pi」的老口径，工具行仍带事件里的来源。
  const multiColumn =
    new Set(assistants.map((row) => row.agent_kind || DEFAULT_AGENT_KIND)).size > 1
  let sequence = 0
  return [...users, ...assistants, ...tools].map((row) => {
    sequence += 1
    return {
      id: `live-${sequence}`,
      role: row.role,
      content: row.content,
      toolName: row.tool_name || undefined,
      agentKind:
        row.role === 'assistant'
          ? multiColumn
            ? row.agent_kind || undefined
            : undefined
          : row.role === 'tool'
            ? row.agent_kind || undefined
            : undefined,
      model:
        row.role === 'assistant' && typeof row.metadata.model === 'string'
          ? (row.metadata.model as string)
          : undefined,
    }
  })
}

/** 真实会话 268 的简化序列：工具全部来自 openai-agents，插在 pi 的回答前后 */
const SESSION_268_ROWS = rowsOf([
  { role: 'user', content: '这份合同有效吗？' },
  {
    role: 'tool',
    content: '{"cases":3}',
    tool_name: 'mcp__fachuan__search_cases',
    agent_kind: 'openai-agents',
    metadata: { tool_call_id: 'call_1' },
  },
  {
    role: 'tool',
    content: '{"case_id":393}',
    tool_name: 'mcp__fachuan__get_case',
    agent_kind: 'openai-agents',
    metadata: { tool_call_id: 'call_2' },
  },
  { role: 'assistant', content: 'Pi 的回答', agent_kind: 'pi', metadata: { model: 'kimi-2.6' } },
  {
    role: 'tool',
    content: '{"contracts":2}',
    tool_name: 'mcp__fachuan__list_contracts',
    agent_kind: 'openai-agents',
    metadata: { tool_call_id: 'call_3' },
  },
  {
    role: 'tool',
    content: '合同正文…',
    tool_name: 'mcp__fachuan__read_folder_file',
    agent_kind: 'openai-agents',
    metadata: { tool_call_id: 'call_4' },
  },
  { role: 'assistant', content: 'dsh 的回答', agent_kind: 'dsh', metadata: { model: 'deepseek-v3' } },
  {
    role: 'assistant',
    content: 'openai-agents 的回答',
    agent_kind: 'openai-agents',
    metadata: { model: 'gpt-5' },
  },
])

describe('后端交错落库 → 一轮三栅', () => {
  it('一段连续的非 user 消息就是一轮（工具行不再把 pi 挤出去）', () => {
    const refresh = historyToMessages(SESSION_268_ROWS)
    const groups = groupAnswerRuns(refresh)

    expect(groups).toHaveLength(2)
    expect(groups[0]!.answers.map((m) => m.role)).toEqual(['user'])
    expect(groups[1]!.answers.map((m) => m.role)).toEqual([
      'tool',
      'tool',
      'assistant',
      'tool',
      'tool',
      'assistant',
      'assistant',
    ])
  })

  it('三个来源各占一栅：pi / dsh / openai-agents，工具全归 openai-agents', () => {
    const refresh = historyToMessages(SESSION_268_ROWS)
    const plan = renderPlan(refresh)

    const multi = columnTurns(plan)
    expect(multi).toHaveLength(1)
    const columns = columnsByAgent(plan)
    expect(Object.keys(columns).sort()).toEqual(['dsh', 'openai-agents', 'pi'])
    expect(columns.pi!.content).toBe('Pi 的回答')
    expect(columns.dsh!.content).toBe('dsh 的回答')
    expect(columns['openai-agents']!.content).toBe('openai-agents 的回答')
    // 每栅工具数：Pi / dsh 没调工具，openai-agents 4 条
    expect(columns.pi!.tools).toHaveLength(0)
    expect(columns.dsh!.tools).toHaveLength(0)
    expect(columns['openai-agents']!.tools).toEqual([
      'openai-agents:mcp__fachuan__search_cases',
      'openai-agents:mcp__fachuan__get_case',
      'openai-agents:mcp__fachuan__list_contracts',
      'openai-agents:mcp__fachuan__read_folder_file',
    ])
    // 归位后不能再有独立的工具项（否则底部还会多出四条全宽 ToolRow）
    expect(visibleTools(plan)).toHaveLength(4)
    expect(multi[0]!.loose).toHaveLength(0)
    expect(attachedToolIds(multi[0]!.columns).size).toBe(4)
  })
})

describe('工具各归各栅（真实多后端并发调工具的形状）', () => {
  const rows = rowsOf([
    { role: 'user', content: '查一下这个案子' },
    { role: 'tool', content: '已确认身份', tool_name: 'get_current_user', agent_kind: 'pi' },
    { role: 'tool', content: '找到 2 个工具', tool_name: 'tool_search', agent_kind: 'dsh' },
    { role: 'tool', content: '{"cases":1}', tool_name: 'mcp__fachuan__search_cases', agent_kind: 'openai-agents' },
    { role: 'assistant', content: 'Pi 的回答', agent_kind: 'pi' },
    { role: 'tool', content: '律师名单', tool_name: 'list_lawyers', agent_kind: 'dsh' },
    {
      role: 'tool',
      content: '{"case_id":393}',
      tool_name: 'mcp__fachuan__get_case',
      agent_kind: 'openai-agents',
    },
    { role: 'assistant', content: 'dsh 的回答', agent_kind: 'dsh' },
    {
      role: 'tool',
      content: '合同正文…',
      tool_name: 'mcp__fachuan__read_folder_file',
      agent_kind: 'openai-agents',
    },
    { role: 'assistant', content: 'openai-agents 的回答', agent_kind: 'openai-agents' },
  ])

  it('交错到达的工具按 agentKind 入栏，不串栏也不丢', () => {
    const plan = renderPlan(historyToMessages(rows))
    const multi = columnTurns(plan)

    expect(multi).toHaveLength(1)
    const columns = columnsByAgent(plan)
    expect(Object.keys(columns).sort()).toEqual(['dsh', 'openai-agents', 'pi'])
    expect(columns.pi!.tools).toEqual(['pi:get_current_user'])
    expect(columns.dsh!.tools).toEqual(['dsh:tool_search', 'dsh:list_lawyers'])
    expect(columns['openai-agents']!.tools).toEqual([
      'openai-agents:mcp__fachuan__search_cases',
      'openai-agents:mcp__fachuan__get_case',
      'openai-agents:mcp__fachuan__read_folder_file',
    ])
    expect(visibleTools(plan)).toHaveLength(6)
    expect(multi[0]!.loose).toHaveLength(0)
  })
})

describe('刷新等价性（实时顺序 vs 落库顺序）', () => {
  it('同一批数据，刷新前后的栅数、每栅工具完全相同', () => {
    const live = renderPlan(liveMessagesFrom(SESSION_268_ROWS))
    const refresh = renderPlan(historyToMessages(SESSION_268_ROWS))

    // 栅数不变、每栅内容与工具不变（按 agent 对齐，不依赖栏的左右顺序）
    expect(columnTurns(refresh)).toHaveLength(1)
    expect(columnTurns(live)).toHaveLength(1)
    expect(columnsByAgent(refresh)).toEqual(columnsByAgent(live))
    expect(Object.keys(columnsByAgent(refresh))).toHaveLength(3)
  })

  it('新问题：栏序按 assistant 首次出现，不能被先到的工具带偏', () => {
    // 实时顺序里 assistant 气泡先入列（pi → dsh → openai-agents）；刷新后
    // openai-agents 的工具排在最前，mergeAgentAnswers 会在**工具**首次出现的
    // 位置吐出该栏，于是三栏变成 openai-agents → pi → dsh，整排换位。
    const plan = renderPlan(historyToMessages(SESSION_268_ROWS))
    expect(columnTurns(plan)[0]!.columns.map(kindOf)).toEqual(['pi', 'dsh', 'openai-agents'])
  })
})

describe('空 agentKind 的旧数据', () => {
  // 引入 agent_kind 之前的记录：assistant / tool 都没有来源标注
  const rows = rowsOf([
    { role: 'user', content: '以前问过的问题' },
    { role: 'tool', content: '旧工具结果：案件 393', tool_name: 'mcp__fachuan__get_case' },
    { role: 'tool', content: '旧工具结果：律师名单', tool_name: 'list_lawyers' },
    { role: 'assistant', content: '旧的 Pi 回答' },
  ])

  it('工具消息没有 agentKind 时仍可见，不被多栅归位吞掉', () => {
    const refresh = historyToMessages(rows)
    const plan = renderPlan(refresh)

    // 旧数据只有一个来源 → 不能分栅
    expect(columnTurns(plan)).toHaveLength(0)
    const flat = plan.flatMap((turn) => (turn.mode === 'flat' ? turn.items : []))
    expect(flat.map((m) => m.role)).toEqual(['user', 'tool', 'tool', 'assistant'])
    expect(flat.filter((m) => m.role === 'tool').map((m) => m.toolName)).toEqual([
      'mcp__fachuan__get_case',
      'list_lawyers',
    ])
    // 工具行没有被吸进 assistant.tools
    expect(flat.find((m) => m.role === 'assistant')?.tools).toBeUndefined()
  })
})

describe('单 agent 回归（引入多栅前的行为）', () => {
  const rows = rowsOf([
    { role: 'user', content: '查下律师' },
    { role: 'tool', content: '已确认身份', tool_name: 'get_current_user', agent_kind: 'pi' },
    { role: 'tool', content: '律师名单', tool_name: 'list_lawyers', agent_kind: 'pi' },
    { role: 'assistant', content: '查到了', agent_kind: 'pi' },
  ])

  it('刷新后仍只有一栏：工具按时间平铺，不吸进气泡', () => {
    const plan = renderPlan(historyToMessages(rows))

    expect(columnTurns(plan)).toHaveLength(0)
    const flat = plan.flatMap((turn) => (turn.mode === 'flat' ? turn.items : []))
    expect(flat.map((m) => m.role)).toEqual(['user', 'tool', 'tool', 'assistant'])
    expect(flat.filter((m) => m.role === 'tool').map((m) => m.toolName)).toEqual([
      'get_current_user',
      'list_lawyers',
    ])
    expect(flat.find((m) => m.role === 'assistant')?.tools).toBeUndefined()
  })

  it('实时顺序同样是平铺（assistant 气泡 + 工具行，不做栅）', () => {
    const plan = renderPlan(liveMessagesFrom(rows))

    expect(columnTurns(plan)).toHaveLength(0)
    const flat = plan.flatMap((turn) => (turn.mode === 'flat' ? turn.items : []))
    expect(flat.map((m) => m.role)).toEqual(['user', 'assistant', 'tool', 'tool'])
    expect(flat.find((m) => m.role === 'assistant')?.tools).toBeUndefined()
  })
})

describe('多 agent 但整轮没有正文（中断 / 全部失败）', () => {
  const rows = rowsOf([
    { role: 'user', content: '帮我查一下' },
    { role: 'tool', content: '已确认身份', tool_name: 'get_current_user', agent_kind: 'pi' },
    { role: 'tool', content: '找到工具', tool_name: 'tool_search', agent_kind: 'dsh' },
    { role: 'tool', content: '{"cases":1}', tool_name: 'mcp__fachuan__search_cases', agent_kind: 'openai-agents' },
  ])

  it('工具行按原顺序平铺，不因为出现多个 kind 就被合并吞掉', () => {
    const plan = renderPlan(historyToMessages(rows))

    expect(columnTurns(plan)).toHaveLength(0)
    const flat = plan.flatMap((turn) => (turn.mode === 'flat' ? turn.items : []))
    expect(flat.map((m) => m.role)).toEqual(['user', 'tool', 'tool', 'tool'])
    expect(visibleTools(plan).map((m) => m.toolName)).toEqual([
      'get_current_user',
      'tool_search',
      'mcp__fachuan__search_cases',
    ])
  })
})

describe('无工具的相邻多答（原有形状不回归）', () => {
  it('连续两条 assistant 仍合成两栅', () => {
    const rows = rowsOf([
      { role: 'user', content: '问' },
      { role: 'assistant', content: 'Pi 的答', agent_kind: 'pi' },
      { role: 'assistant', content: 'dsh 的答', agent_kind: 'dsh' },
    ])
    const plan = renderPlan(historyToMessages(rows))

    expect(columnTurns(plan)).toHaveLength(1)
    expect(columnTurns(plan)[0]!.columns.map(kindOf)).toEqual(['pi', 'dsh'])
  })
})
