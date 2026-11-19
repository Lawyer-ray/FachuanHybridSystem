// @vitest-environment jsdom
/**
 * 回归（真实渲染）：多 agent 会话刷新后「栅数变少 / 工具条混在一起」。
 *
 * 与 `domain/multiagent-refresh.test.ts` 的分工：那边验 domain 变换，这里验
 * `MessageList → AnswerGroupView → MultiAnswers` 真把结果画成了三栏，而且
 * 工具只在所属那栏出现、不再作为全宽 ToolRow 堆在转录流底部。
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
    // 全宽工具行的文案是「已完成 · 工具名」；多栏归位后不该再出现
    expect(document.body.textContent).not.toContain('已完成 · ')
  })
})

describe('多 agent 但整轮没有正文（中断 / 全部失败）', () => {
  it('新问题：只有工具行时仍要画出来，不能因多 kind 被合并吞掉', () => {
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
    expect(document.body.textContent).toContain('已完成 · get_current_user')
    expect(document.body.textContent).toContain('已完成 · tool_search')
    expect(document.body.textContent).toContain('已完成 · search_cases')
  })
})

describe('旧数据 / 单 agent：工具仍按时间平铺', () => {
  it('空 agentKind 的工具行照样画出（律师要看到查了什么）', () => {
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
    expect(document.body.textContent).toContain('已完成 · get_case')
    expect(document.body.textContent).toContain('旧工具结果：案件 393')
    expect(document.body.textContent).toContain('旧的 Pi 回答')
  })

  it('单 agent 轮次不分栅，工具行在气泡外平铺', () => {
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
    expect(document.body.textContent).toContain('已完成 · get_current_user')
    expect(document.body.textContent).toContain('已完成 · list_lawyers')
    expect(document.body.textContent).toContain('查到了')
  })
})
