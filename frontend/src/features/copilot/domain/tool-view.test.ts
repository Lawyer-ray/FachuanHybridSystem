/**
 * 工具行展示口径：名称归族、标题、耗时、五态文案。
 *
 * 这几条判据错了不会报错，只会「看起来正常但不对劲」：归错族 → 标题说错动作；
 * 标题不截断 → 一行工具条被长路径撑爆；耗时口径错 → 律师以为工具跑了 0 秒。
 */

import { describe, expect, it } from 'vitest'

import { formatElapsed, toolKind, toolStateLabel, toolStateOf, toolSummary } from './tool-view'

describe('toolKind（按名称前缀族归类）', () => {
  it('读 / 查 / 写 / 执行 / 取网络各归各族', () => {
    expect(toolKind('read_folder_file')).toBe('read')
    expect(toolKind('list_contracts')).toBe('read')
    expect(toolKind('get_current_user')).toBe('read')
    expect(toolKind('search_cases')).toBe('search')
    expect(toolKind('web_search')).toBe('search')
    expect(toolKind('rewrite_folder_file')).toBe('write')
    expect(toolKind('delete_case')).toBe('write')
    expect(toolKind('run_python')).toBe('execute')
    expect(toolKind('bash')).toBe('execute')
    expect(toolKind('download_file')).toBe('fetch')
    expect(toolKind('fetch_url')).toBe('fetch')
  })

  it('带 provider 前缀时先归一短名', () => {
    expect(toolKind('mcp__fachuan__read_folder_file')).toBe('read')
  })

  it('未知工具回落 other', () => {
    expect(toolKind('mystery_tool')).toBe('other')
    expect(toolKind('')).toBe('other')
  })
})

describe('toolSummary（「正在做什么」一句短标题）', () => {
  it('按工具族生成「动词 + 对象」', () => {
    expect(toolSummary({ toolName: 'read_folder_file', toolArgs: { path: '合同/2024/合同A.pdf' } })).toBe(
      '读取 合同A.pdf',
    )
    expect(toolSummary({ toolName: 'search_contracts', toolArgs: { query: '违约责任' } })).toBe('检索 违约责任')
    expect(toolSummary({ toolName: 'run_python', toolArgs: { command: 'python -m foo' } })).toBe('执行 python')
  })

  it('取不到参数时只回工具短名（历史回放没有 toolArgs）', () => {
    expect(toolSummary({ toolName: 'mcp__fachuan__list_lawyers' })).toBe('list_lawyers')
    expect(toolSummary({ toolName: 'mystery_tool', toolArgs: { query: 'x' } })).toBe('mystery_tool')
  })

  it('超长参数截到 40 字（标题不能撑爆一行）', () => {
    const text = toolSummary({ toolName: 'search_contracts', toolArgs: { query: '违约责任'.repeat(20) } })
    expect(text.length).toBeLessThanOrEqual(40)
    expect(text.endsWith('…')).toBe(true)
  })
})

describe('formatElapsed（耗时三档）', () => {
  it('亚秒一位小数 / 秒 / 分+秒补零', () => {
    expect(formatElapsed(1_000, 1_400)).toBe('0.4s')
    expect(formatElapsed(1_000, 13_000)).toBe('12s')
    expect(formatElapsed(1_000, 66_000)).toBe('1m05s')
  })

  it('未结束时用注入的 now（每秒刷新可测）', () => {
    expect(formatElapsed(1_000, undefined, 1_400)).toBe('0.4s')
  })

  it('没有开始时刻返回空串，不给假耗时', () => {
    expect(formatElapsed(undefined, 2_000)).toBe('')
    expect(formatElapsed(Number.NaN, 2_000)).toBe('')
  })
})

describe('toolStateOf / toolStateLabel（五态）', () => {
  it('旧数据按结果有无回落（历史回放没有 toolState）', () => {
    expect(toolStateOf({ content: '' })).toBe('running')
    expect(toolStateOf({ content: '结果' })).toBe('ok')
    expect(toolStateOf({ content: '结果', toolState: 'error' })).toBe('error')
  })

  it('五态各有文案与色调', () => {
    expect(toolStateLabel('preparing')).toEqual({ text: '准备中', tone: 'muted' })
    expect(toolStateLabel('running')).toEqual({ text: '调用中', tone: 'muted' })
    expect(toolStateLabel('ok')).toEqual({ text: '已完成', tone: 'ok' })
    expect(toolStateLabel('error')).toEqual({ text: '失败', tone: 'error' })
    expect(toolStateLabel('stopped')).toEqual({ text: '已中止', tone: 'warn' })
  })
})
