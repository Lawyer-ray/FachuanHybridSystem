/**
 * 流式「还在干活」的口径：当前在调哪个工具、动作词翻译。
 *
 * 这几条判据错了都不会报错，只会「看起来正常但不对劲」：取错工具 → 卡片
 * 显示的是已经查完的那个（律师看到「正在查 XX」永远不停）；动作词翻译错
 * （把 `get_current_user` 直出）→ 界面上冒出一串程序内部标识。
 */

import { describe, expect, it } from 'vitest'

import { activityText, pendingToolCall, toolActionLabel } from './progress'
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
