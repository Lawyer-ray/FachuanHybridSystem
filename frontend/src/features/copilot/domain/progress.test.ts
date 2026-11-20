/**
 * 流式「还在干活」的口径：当前在调哪个工具、动作词翻译。
 *
 * 这几条判据错了都不会报错，只会「看起来正常但不对劲」：取错工具 → 卡片
 * 显示的是已经查完的那个（律师看到「正在查 XX」永远不停）；动作词翻译错
 * （把 `get_current_user` 直出）→ 界面上冒出一串程序内部标识。
 */

import { describe, expect, it } from 'vitest'

import { activityText, applyToolCall, applyToolResult, currentTool, pendingToolCall, toolActionLabel } from './progress'
import type { ChatMessage } from '../types'

const tool = (id: string, name: string, content = ''): ChatMessage => ({
  id,
  role: 'tool',
  content,
  toolName: name,
})

describe('pendingToolCall（这一栏此刻在等哪个工具）', () => {
  it('没有工具时返回 null（不能编造一个焦点）', () => {
    expect(pendingToolCall(undefined)).toBeNull()
    expect(pendingToolCall([])).toBeNull()
  })

  it('只有一条未完成工具时就是它', () => {
    expect(pendingToolCall([tool('t1', 'list_lawyers')])?.id).toBe('t1')
  })

  it('并行调用取**最后发起**的那条（界面只留一个焦点）', () => {
    const tools = [tool('t1', 'get_current_user'), tool('t2', 'list_lawyers')]
    expect(pendingToolCall(tools)?.id).toBe('t2')
  })

  it('已完成的工具不算：跳过它找后面没回来的那条', () => {
    const tools = [tool('t1', 'get_current_user', '{"id":1}'), tool('t2', 'list_cases')]
    expect(pendingToolCall(tools)?.id).toBe('t2')
  })

  it('全部已完成时返回 null（此刻不在等任何工具）', () => {
    const tools = [tool('t1', 'get_current_user', '{}'), tool('t2', 'list_cases', '[]')]
    expect(pendingToolCall(tools)).toBeNull()
  })
})

/**
 * 单栏真实形态：气泡上没有 `tools`（那是多栏的渲染槽），只有 `pendingTool`。
 *
 * 这一组以前是空的——`activityText` 只看 `message.tools`，而单栏永远是 undefined，
 * 于是 dsh / openai-agents 调工具的十几秒里界面什么都没有（律师以为卡死）。
 */
describe('activityText（单栏：靠 pendingTool 说话）', () => {
  const assistant = (pendingTool?: ChatMessage): ChatMessage => ({
    id: 'a1',
    role: 'assistant',
    content: '',
    streaming: true,
    ...(pendingTool ? { pendingTool } : {}),
  })

  it('工具还在跑：说清在查什么（不依赖 tools）', () => {
    expect(activityText(assistant(tool('call-1', 'mcp__fachuan__list_lawyers')))).toBe('正在查律师名单…')
  })

  it('工具都回来了、正文还没到：转「正在整理资料…」（不是继续「正在查」）', () => {
    // turn-handlers 的 onToolResult 把 pendingTool 置为**已完成**而不是清空，
    // 就是为了这一档能判出来：置空的话这里会直接白回去，而正文还要再等好几秒
    expect(activityText(assistant(tool('call-1', 'get_client', '{"name":"张三"}')))).toBe('正在整理资料…')
  })

  it('正文到了就不再说动作（正文自己会说话）', () => {
    expect(activityText({ ...assistant(tool('call-1', 'get_client')), content: '结论' })).toBeNull()
  })

  it('多栏时 tools 优先：并行调用里还差最早那个没回来', () => {
    // 多栏的 tools 是本轮全部工具的历史，pendingTool 只是最后一枚；顺序反了会把
    // 「还在等 get_current_user」说成「正在查律师名单」（后一个已经回来了）
    const message: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: '',
      streaming: true,
      tools: [tool('t1', 'get_current_user'), tool('t2', 'list_lawyers', '[]')],
      pendingTool: tool('t2', 'list_lawyers', '[]'),
    }
    expect(activityText(message)).toBe('正在确认身份…')
  })
})

describe('currentTool（这条气泡的焦点工具）', () => {
  it('两个来源都空时返回 null（不能编造焦点）', () => {
    expect(currentTool({ id: 'a1', role: 'assistant', content: '' })).toBeNull()
  })

  it('只有 pendingTool 时就是它（单栏）', () => {
    const tool1 = tool('call-1', 'list_cases')
    expect(currentTool({ id: 'a1', role: 'assistant', content: '', pendingTool: tool1 })?.id).toBe('call-1')
  })

  it('tools 里有未完成的优先于 pendingTool（多栏）', () => {
    const message: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: '',
      tools: [tool('t1', 'get_current_user')],
      pendingTool: tool('t2', 'list_lawyers', '已回'),
    }
    expect(currentTool(message)?.id).toBe('t1')
  })
})

describe('toolActionLabel（工具名 → 律师看得懂的动作词）', () => {
  it('高频工具翻译成中文动作', () => {
    expect(toolActionLabel('get_current_user')).toBe('确认身份')
    expect(toolActionLabel('list_lawyers')).toBe('查律师名单')
    expect(toolActionLabel('read_folder_file')).toBe('读材料文件')
    expect(toolActionLabel('tool_search')).toBe('检索可用工具')
  })

  it('带 mcp 前缀的名字先归一，再查表', () => {
    // 事件与历史里的 toolName 存的是原名，前缀不能让它查不到表
    expect(toolActionLabel('mcp__fachuan__list_cases')).toBe('查案件列表')
  })

  it('没收录的工具回落为短名（比什么都不显示更接近「在干什么」）', () => {
    expect(toolActionLabel('mcp__fachuan__some_new_tool')).toBe('some_new_tool')
    expect(toolActionLabel('custom_tool')).toBe('custom_tool')
  })

  it('缺名时回落为「工具」（与 shortToolName 同一兜底）', () => {
    expect(toolActionLabel(undefined)).toBe('工具')
    expect(toolActionLabel('')).toBe('工具')
  })
})

describe('activityText（这一栏此刻在干什么）', () => {
  it('有工具未返回：说清在查什么', () => {
    const message: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: '',
      streaming: true,
      tools: [tool('t1', 'mcp__fachuan__list_lawyers')],
    }
    expect(activityText(message)).toBe('正在查律师名单…')
  })

  it('工具全回来了、正文还没来：在读结果', () => {
    const message: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: '',
      streaming: true,
      tools: [tool('t1', 'list_cases', '[]')],
    }
    expect(activityText(message)).toBe('正在整理资料…')
  })

  it('正文到达后不再报动作（不能与正文并存）', () => {
    const message: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: '答案',
      streaming: true,
      tools: [tool('t1', 'list_cases')],
    }
    expect(activityText(message)).toBeNull()
  })

  it('思考中不叠加活动行（思考块自带「深度思考中…」流光）', () => {
    const message: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: '',
      streaming: true,
      thinking: '推理中',
      tools: [tool('t1', 'list_cases')],
    }
    expect(activityText(message)).toBeNull()
  })

  it('失败栏轮不到活动行（有自己的「本轮未做」）', () => {
    const message: ChatMessage = { id: 'a1', role: 'assistant', content: '', streaming: true, failed: true }
    expect(activityText(message)).toBeNull()
  })

  it('流已结束不显示活动行', () => {
    const message: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: '',
      streaming: false,
      tools: [tool('t1', 'list_cases')],
    }
    expect(activityText(message)).toBeNull()
  })

  it('空栏（没有工具、没有思考、正文未到）留空，不凭空说「正在思考」', () => {
    // 思考模式关闭时「正在思考…」是不成立的叙述；这一段只有几百毫秒
    expect(activityText({ id: 'a1', role: 'assistant', content: '', streaming: true })).toBeNull()
  })
})

describe('applyToolCall / applyToolResult（一次调用落在两个位置）', () => {
  const assistant = (id: string, agentKind?: string): ChatMessage => ({
    id,
    role: 'assistant',
    content: '',
    streaming: true,
    ...(agentKind ? { agentKind } : {}),
  })
  const lanes = () => [assistant('a1'), assistant('a2', 'dsh')]
  const owner = (messages: ChatMessage[], id = 'a1') => messages.find((m) => m.id === id)!

  it('tool_call：转录里新增工具行，且只在所属气泡挂 pendingTool', () => {
    const next = applyToolCall(lanes(), 'a1', { toolCallId: 'c1', toolName: 'list_lawyers', agentKind: 'pi' })

    expect(next.filter((m) => m.role === 'tool')).toHaveLength(1)
    expect(next.find((m) => m.role === 'tool')!.agentKind).toBe('pi')
    expect(owner(next).pendingTool?.toolName).toBe('list_lawyers')
    // 另一栏绝不能被挂上：多答串栏会让 dsh 那一栏显示 pi 的工具
    expect(owner(next, 'a2').pendingTool).toBeUndefined()
  })

  it('同一次调用重复到达：不新增行，且返回**原引用**（store 据此跳过写状态）', () => {
    const first = applyToolCall(lanes(), 'a1', { toolCallId: 'c1', toolName: 'list_lawyers' })
    const again = applyToolCall(first, 'a1', { toolCallId: 'c1', toolName: 'list_lawyers' })

    expect(again).toBe(first)
    expect(again.filter((m) => m.role === 'tool')).toHaveLength(1)
  })

  it('参数渐进完整：后到的修订块覆盖前一条，仍只有一行', () => {
    const first = applyToolCall(lanes(), 'a1', {
      toolCallId: 'c1',
      toolName: 'rewrite_folder_file',
      rewrite: { original: '一半', replacement: '' },
    })
    const second = applyToolCall(first, 'a1', {
      toolCallId: 'c1',
      toolName: 'rewrite_folder_file',
      rewrite: { original: '完整原文', replacement: '完整改写' },
    })

    const rows = second.filter((m) => m.role === 'tool')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.rewrite?.replacement).toBe('完整改写')
  })

  it('tool_result：工具行填结果，pendingTool 置**已完成**（不是清空）', () => {
    let messages = applyToolCall(lanes(), 'a1', { toolCallId: 'c1', toolName: 'get_client' })
    messages = applyToolResult(messages, 'a1', { toolCallId: 'c1', result: '{"name":"张三"}' })

    expect(messages.find((m) => m.role === 'tool')!.content).toBe('{"name":"张三"}')
    expect(owner(messages).pendingTool).toBeTruthy()
    expect(owner(messages).pendingTool!.content).toBe('{"name":"张三"}')
    // 「查完了、正文还没来」这一档必须能判出来（置空的话界面会白回去）
    expect(activityText(owner(messages))).toBe('正在整理资料…')
  })

  it('结果为空也算完成（否则界面永远停在「正在查…」，而哨兵不漏到文案里）', () => {
    let messages = applyToolCall(lanes(), 'a1', { toolCallId: 'c1', toolName: 'list_cases' })
    messages = applyToolResult(messages, 'a1', { toolCallId: 'c1', result: '' })

    const text = activityText(owner(messages))
    expect(text).toBe('正在整理资料…')
    expect(text).not.toContain('无返回内容')
  })

  it('别的栏的工具结果不影响本栏的「正在查」', () => {
    let messages = applyToolCall(lanes(), 'a1', { toolCallId: 'p1', toolName: 'get_client' })
    messages = applyToolCall(messages, 'a2', { toolCallId: 'd1', toolName: 'list_cases' })
    messages = applyToolResult(messages, 'a2', { toolCallId: 'd1', result: '[]' })

    expect(activityText(owner(messages, 'a1'))).toBe('正在查客户信息…')
    expect(activityText(owner(messages, 'a2'))).toBe('正在整理资料…')
  })
})
