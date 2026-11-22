// @vitest-environment jsdom
/**
 * 回归（真实渲染）：多 agent 会话刷新后「栅数变少 / 工具条混在一起」。
 *
 * 与 `domain/multiagent-refresh.test.ts` 的分工：那边验 domain 变换，这里验
 * `MessageList → AnswerGroupView → MultiAnswers` 真把结果画成了三栏，而且
 * 工具只在所属那栏出现、不再作为整行工具条堆在转录流底部。
 *
 * 单栏（含只有工具、没有正文的轮次）的连续工具现在是**换行 chip 流**（见 ToolChips
 * 的 `ToolChipList`）：`<details>` 收起是一枚 chip、展开才占整行。整行形态的 `ToolRow`
 * 只剩多栏里「没归位到任何一栏」的工具在用。所以这里断言的是「工具仍在时间流里、
 * 在气泡之外、结果仍可读」，**不再锁具体文案**（`ok` 态已不出「已完成」字）。
 */

import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { historyToMessages } from '../domain'
import { useCopilot } from '../store'
import type { AgentHistoryMessage, ChatMessage } from '../types'
import { MessageList } from './MessageList'

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

/** 真实会话 268 的简化落库顺序（工具插在 pi 的回答前后） */
const SESSION_268_ROWS = rowsOf([
  { role: 'user', content: '这份合同有效吗？' },
  {
    role: 'tool',
    content: '{"cases":3}',
    tool_name: 'mcp__fachuan__search_cases',
    agent_kind: 'openai-agents',
  },
  {
    role: 'tool',
    content: '{"case_id":393}',
    tool_name: 'mcp__fachuan__get_case',
    agent_kind: 'openai-agents',
  },
  { role: 'assistant', content: 'Pi 的回答', agent_kind: 'pi' },
  {
    role: 'tool',
    content: '{"contracts":2}',
    tool_name: 'mcp__fachuan__list_contracts',
    agent_kind: 'openai-agents',
  },
  {
    role: 'tool',
    content: '合同正文…',
    tool_name: 'mcp__fachuan__read_folder_file',
    agent_kind: 'openai-agents',
  },
  { role: 'assistant', content: 'dsh 的回答', agent_kind: 'dsh' },
  { role: 'assistant', content: 'openai-agents 的回答', agent_kind: 'openai-agents' },
])

/**
 * 时间流里承载某工具的那枚 chip。
 *
 * 用结构断言而不是纯子串：工具名必须落在一枚 `<details>`（可展开看返回值）里，
 * 且**不在任何气泡内**（气泡带 `data-msg-id`，栏内的 `OwnToolList` 就在气泡里）——
 * 否则「在气泡外」这件事一旦漂移，纯子串断言还会因为别处的同名文字而永远为真。
 */
function chipOf(toolName: string): HTMLElement {
  const chip = screen.getByText(toolName).closest('details')
  expect(chip).not.toBeNull()
  expect(chip!.closest('[data-msg-id]')).toBeNull()
  return chip as HTMLElement
}

function renderMessages(messages: ChatMessage[]) {
  useCopilot.setState({
    messages,
    streaming: false,
    loadingHistory: false,
    approvals: [],
    lastError: null,
    queuePosition: null,
  })
  return render(<MessageList />)
}

afterEach(() => {
  act(() => {
    useCopilot.setState({
      messages: [],
      streaming: false,
      loadingHistory: false,
      approvals: [],
      lastError: null,
      queuePosition: null,
    })
  })
})

describe('刷新：同一轮的三个 agent 并排', () => {
  it('渲染出 3 栅，三份回答各在自己的栏里', () => {
    renderMessages(historyToMessages(SESSION_268_ROWS))

    const grid = screen.getByTestId('multi-answers')
    expect(grid.getAttribute('data-columns')).toBe('3')
    expect(screen.getByTestId('multi-column-pi').textContent).toContain('Pi 的回答')
    expect(screen.getByTestId('multi-column-dsh').textContent).toContain('dsh 的回答')
    expect(screen.getByTestId('multi-column-openai-agents').textContent).toContain(
      'openai-agents 的回答',
    )
  })

  it('新问题：刷新后三栏的左右顺序与实时一致（pi → dsh → openai-agents）', () => {
    // 实时（store 开流）先按栏清单入列 assistant 气泡；刷新后 openai-agents
    // 的工具排在最前，栏若在工具首次出现的位置吐出，整排会换位。
    renderMessages(historyToMessages(SESSION_268_ROWS))

    const kinds = [...screen.getByTestId('multi-answers').querySelectorAll('[data-testid^="multi-column-"]')]
      .map((node) => node.getAttribute('data-testid'))
    expect(kinds).toEqual([
      'multi-column-pi',
      'multi-column-dsh',
      'multi-column-openai-agents',
    ])
  })

  it('四条工具只在 openai-agents 那栏，且不再当全宽 ToolRow 渲染', () => {
    renderMessages(historyToMessages(SESSION_268_ROWS))

    const openai = screen.getByTestId('multi-column-openai-agents')
    for (const name of ['search_cases', 'get_case', 'list_contracts', 'read_folder_file']) {
      expect(openai.textContent).toContain(name)
    }
    expect(screen.getByTestId('multi-column-pi').textContent).not.toContain('search_cases')
    expect(screen.getByTestId('multi-column-dsh').textContent).not.toContain('search_cases')
    // 守卫本轮需求：`ok` 态**不再出可见文字**「已完成」（用户要的是只有图标的 chip，
    // 见 ToolChips 文件头）。整行 ToolRow 的文案正是「已完成 · 工具名」，而这里也
    // 根本不该有多栏归位后的整行工具条——两件事一起防，别把它改回来。
    expect(document.body.textContent).not.toContain('已完成 · ')
  })
})

describe('多 agent 但整轮没有正文（中断 / 全部失败）', () => {
  it('新问题：只有工具时仍要画出来（chip 流），不能因多 kind 被合并吞掉', () => {
    renderMessages(
      historyToMessages(
        rowsOf([
          { role: 'user', content: '帮我查一下' },
          { role: 'tool', content: '已确认身份', tool_name: 'get_current_user', agent_kind: 'pi' },
          { role: 'tool', content: '找到工具', tool_name: 'tool_search', agent_kind: 'dsh' },
          {
            role: 'tool',
            content: '{"cases":1}',
            tool_name: 'mcp__fachuan__search_cases',
            agent_kind: 'openai-agents',
          },
        ]),
      ),
    )

    expect(screen.queryByTestId('multi-answers')).toBeNull()
    // 三条工具各一枚 chip，且结果跟着 chip（展开/可读）
    expect(chipOf('get_current_user').textContent).toContain('已确认身份')
    expect(chipOf('tool_search').textContent).toContain('找到工具')
    // 工具原文先过 `domain/tool-content` 的 `formatToolContent`（见 ToolRow/ToolChips）：
    // 键值可见、已展开成多行、**不再**把原文的紧凑形状原样吐出来。
    // 这里刻意不写「反证式 `not.toContain('{\n')`」：本样本是紧凑 JSON `{"cases":1}`
    //（不是 MCP 信封），它美化后本来就以 `{\n` 开头，那条守卫在这里恒假；
    // 等价的反证是「紧凑原文不见了」——美化一旦被关掉，最后一条会立刻变红。
    const cases = chipOf('search_cases').textContent ?? ''
    expect(cases).toContain('"cases": 1')
    expect(cases).toContain('\n')
    expect(cases).not.toContain('{"cases":1}')
  })
})

describe('旧数据 / 单 agent：工具仍在时间流里（换成换行 chip 流）', () => {
  it('空 agentKind 的工具 chip 照样画出（律师要看到查了什么）', () => {
    renderMessages(
      historyToMessages(
        rowsOf([
          { role: 'user', content: '以前问过的问题' },
          { role: 'tool', content: '旧工具结果：案件 393', tool_name: 'mcp__fachuan__get_case' },
          { role: 'assistant', content: '旧的 Pi 回答' },
        ]),
      ),
    )

    expect(screen.queryByTestId('multi-answers')).toBeNull()
    expect(chipOf('get_case').textContent).toContain('旧工具结果：案件 393')
    expect(document.body.textContent).toContain('旧的 Pi 回答')
  })

  it('单 agent 轮次不分栅，工具 chip 在气泡外组成换行流', () => {
    renderMessages(
      historyToMessages(
        rowsOf([
          { role: 'user', content: '查下律师' },
          { role: 'tool', content: '已确认身份', tool_name: 'get_current_user', agent_kind: 'pi' },
          { role: 'tool', content: '律师名单', tool_name: 'list_lawyers', agent_kind: 'pi' },
          { role: 'assistant', content: '查到了', agent_kind: 'pi' },
        ]),
      ),
    )

    expect(screen.queryByTestId('multi-answers')).toBeNull()
    expect(chipOf('get_current_user').textContent).toContain('已确认身份')
    expect(chipOf('list_lawyers').textContent).toContain('律师名单')
    expect(document.body.textContent).toContain('查到了')
  })
})
