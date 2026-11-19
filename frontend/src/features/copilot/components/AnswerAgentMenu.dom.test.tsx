// @vitest-environment jsdom
/**
 * 「这次跑哪几个 AI、各用哪个模型」多选菜单（jsdom）。
 *
 * 必须成立的事实：
 * 1. **选择即增删**：点一项回调一次 kind，顺序由 store 决定（菜单不排序）；
 * 2. **上限 4**：选满后未选项置灰——超出的选择后端会 400，而那发生在用户已经
 *    敲了回车之后；
 * 3. **不可用项置灰并说明原因**：缺 SDK / 没配 LLM 的后端留着（说明真相是
 *    「这里缺东西」），但点不动；
 * 4. 触发按钮上要能看出「本轮问几个」，否则律师得点开才知道；
 * 5. **每行带模型下拉**（规格 4.1）：默认预填 `default_model`、未勾选置灰、
 *    清单为空时整枚下拉消失（降级）。
 */

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AgentBackendOption } from '../types'
import { AnswerAgentMenu } from './AnswerAgentMenu'

function option(kind: string, label = kind, available = true, models: string[] = [], defaultModel = ''): AgentBackendOption {
  return {
    kind,
    label,
    description: `${label} 说明`,
    available,
    reason: available ? '' : '未安装 SDK',
    capabilities: { streaming: true },
    models,
    default_model: defaultModel,
  }
}

const MODELS = ['kimi-2.6', 'glm53', 'claude-opus-4-5']
const backends = [
  option('pi', 'Pi', true, MODELS, 'kimi-2.6'),
  option('dsh', 'DeepSeek Harness', true, MODELS, 'glm53'),
  option('oai', 'OpenAI Agents', true, MODELS, 'kimi-2.6'),
  option('gpt', 'GPT'),
]

function renderMenu(props: Partial<React.ComponentProps<typeof AnswerAgentMenu>> = {}) {
  const onToggle = vi.fn()
  const onSelectModel = vi.fn()
  const rendered = render(
    <AnswerAgentMenu
      backends={backends}
      selected={[]}
      models={{}}
      defaultKind="pi"
      disabled={false}
      hint=""
      onToggle={onToggle}
      onSelectModel={onSelectModel}
      {...props}
    />,
  )
  return { onToggle, onSelectModel, ...rendered }
}

/** 打开菜单（触发按钮的 aria-label 随选择变化，按前缀找） */
function openMenu() {
  fireEvent.click(screen.getByRole('button', { name: /本轮参与的 AI/ }))
}

describe('AnswerAgentMenu', () => {
  it('未选时触发按钮说明本轮只跑 1 个 AI', () => {
    renderMenu()
    expect(screen.getByLabelText('本轮参与的 AI：1 个 AI')).toBeTruthy()
  })

  it('选中多个时按钮显示数量（不用点开就知道几栏）', () => {
    renderMenu({ selected: ['pi', 'dsh', 'oai'] })
    expect(screen.getByLabelText('本轮参与的 AI：3 个 AI')).toBeTruthy()
  })

  it('只选一个时按钮直接显示那家的名字', () => {
    renderMenu({ selected: ['dsh'] })
    expect(screen.getByLabelText('本轮参与的 AI：DeepSeek Harness')).toBeTruthy()
  })

  it('清单没拉到时显示 kind 原文，而不是空白', () => {
    renderMenu({ backends: [], selected: ['pi'] })
    expect(screen.getByLabelText('本轮参与的 AI：pi')).toBeTruthy()
  })

  it('点开菜单列出全部后端，默认那家带「默认」徽标', () => {
    renderMenu()
    openMenu()

    const listbox = screen.getByRole('listbox', { name: '可选 AI（多选）' })
    expect(listbox).toBeTruthy()
    expect(screen.getAllByRole('option')).toHaveLength(backends.length)
    // 默认项（清单第一项）标出来：律师要知道「不选时到底是谁在答」
    expect(screen.getByText('默认')).toBeTruthy()
    expect(screen.getByRole('option', { name: /Pi/ }).getAttribute('aria-selected')).toBe('false')
  })

  it('点一项回调那次 kind，并收起菜单', () => {
    const { onToggle } = renderMenu()
    openMenu()
    fireEvent.click(screen.getByRole('checkbox', { name: 'DeepSeek Harness' }))

    expect(onToggle).toHaveBeenCalledWith('dsh')
    expect(screen.queryByRole('listbox', { name: '可选 AI（多选）' })).toBeNull()
  })

  it('已选项带对勾（aria-checked）', () => {
    renderMenu({ selected: ['dsh'] })
    openMenu()
    expect(screen.getByRole('checkbox', { name: 'DeepSeek Harness' }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('checkbox', { name: 'Pi' }).getAttribute('aria-checked')).toBe('false')
  })

  it('选满 4 个后未选项置灰（超上限后端会 400）', () => {
    // 已选 4 个 = 满额；清单里再来第五个后端
    const allBackends = [...backends, option('x', '第五个')]
    renderMenu({ selected: ['pi', 'dsh', 'oai', 'gpt'], backends: allBackends })
    openMenu()

    expect(screen.getAllByRole('option')).toHaveLength(allBackends.length)
    // 已选的仍可点（取消不需要名额）
    expect((screen.getByRole('checkbox', { name: 'Pi' }) as HTMLButtonElement).disabled).toBe(false)
    const fifth = screen.getByRole('checkbox', { name: '第五个' }) as HTMLButtonElement
    expect(fifth.disabled).toBe(true)
    expect(fifth.title).toContain('最多同时问 4 个')
  })

  it('不可用的后端置灰并显示原因（点不动，但留在列表里说明真相）', () => {
    renderMenu({ backends: [option('pi', 'Pi'), option('dsh', 'DeepSeek Harness', false, MODELS, 'glm53')] })
    openMenu()

    const dsh = screen.getByRole('checkbox', { name: 'DeepSeek Harness' }) as HTMLButtonElement
    expect(dsh.disabled).toBe(true)
    expect(dsh.closest('[data-testid="agent-row-dsh"]')!.textContent).toContain('未安装 SDK')
  })

  it('清单为空时菜单仍可打开并说明「本轮使用默认 AI」', () => {
    renderMenu({ backends: [] })
    openMenu()
    expect(screen.getByText('后端清单暂不可用，本轮使用默认 AI。')).toBeTruthy()
  })

  it('流式中禁用：按钮点不动，提示说清原因', () => {
    renderMenu({ disabled: true })
    const trigger = screen.getByLabelText('本轮参与的 AI：1 个 AI') as HTMLButtonElement
    expect(trigger.disabled).toBe(true)
    expect(trigger.title).toContain('结束前不能改参与方')
  })

  it('传入的禁用原因优先于默认文案', () => {
    renderMenu({ disabled: true, hint: '发送中，请稍候' })
    expect((screen.getByLabelText('本轮参与的 AI：1 个 AI') as HTMLButtonElement).title).toBe('发送中，请稍候')
  })
})

describe('AnswerAgentMenu：每行的模型下拉（规格 4.1）', () => {
  it('模型下拉预填后端给的 default_model（用户不用先点一下才知道去哪改）', () => {
    renderMenu()
    openMenu()
    expect(screen.getByLabelText('Pi 使用的模型：kimi-2.6')).toBeTruthy()
    expect(screen.getByLabelText('DeepSeek Harness 使用的模型：glm53')).toBeTruthy()
  })

  it('律师指定过的模型覆盖默认预填', () => {
    renderMenu({ models: { pi: 'claude-opus-4-5' } })
    openMenu()
    expect(screen.getByLabelText('Pi 使用的模型：claude-opus-4-5')).toBeTruthy()
  })

  it('没勾选的行模型下拉置灰（选了也不跑）', () => {
    renderMenu()
    openMenu()
    const picker = screen.getByLabelText('Pi 使用的模型：kimi-2.6') as HTMLButtonElement
    expect(picker.disabled).toBe(true)
    expect(picker.title).toContain('先勾选这一行')
  })

  it('勾选后模型下拉可点，选中回调 (kind, 模型)', () => {
    const { onSelectModel } = renderMenu({ selected: ['pi'] })
    openMenu()
    fireEvent.click(screen.getByLabelText('Pi 使用的模型：kimi-2.6'))
    fireEvent.click(screen.getByRole('option', { name: 'claude-opus-4-5' }))

    expect(onSelectModel).toHaveBeenCalledWith('pi', 'claude-opus-4-5')
    // 选完收起自己的列表，但整张多选菜单不收起（还要接着配别家）
    expect(screen.queryByRole('listbox', { name: 'Pi 的模型' })).toBeNull()
    expect(screen.getByRole('listbox', { name: '可选 AI（多选）' })).toBeTruthy()
  })

  it('改模型不会把那一行勾选掉（两个控件互相独立）', () => {
    const { onToggle, onSelectModel } = renderMenu({ selected: ['pi'] })
    openMenu()
    fireEvent.click(screen.getByLabelText('Pi 使用的模型：kimi-2.6'))
    fireEvent.click(screen.getByRole('option', { name: 'glm53' }))

    expect(onSelectModel).toHaveBeenCalledWith('pi', 'glm53')
    expect(onToggle).not.toHaveBeenCalled()
  })

  it('模型清单为空时整枚下拉不渲染（后端未上线该字段的部署照常用多选）', () => {
    // GPT 那条没有 models：行还在、勾选框还能点，只是没有模型下拉
    renderMenu({ backends: [option('gpt', 'GPT')], selected: ['gpt'] })
    openMenu()
    expect(screen.getByRole('checkbox', { name: 'GPT' })).toBeTruthy()
    expect(screen.queryByLabelText(/使用的模型/)).toBeNull()
  })

  it('点击下拉以外的地方收起模型列表（无遮罩，靠监听点击）', () => {
    renderMenu({ selected: ['pi'] })
    openMenu()
    fireEvent.click(screen.getByLabelText('Pi 使用的模型：kimi-2.6'))
    expect(screen.getByRole('listbox', { name: 'Pi 的模型' })).toBeTruthy()

    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole('listbox', { name: 'Pi 的模型' })).toBeNull()
  })

  it('既没指定也没 default_model 时显示「默认模型」（不是一片空白）', () => {
    renderMenu({ backends: [option('pi', 'Pi', true, MODELS)], selected: ['pi'] })
    openMenu()
    expect(screen.getByLabelText('Pi 使用的模型：默认模型')).toBeTruthy()
  })

  it('底部显示已选数量与上限', () => {
    renderMenu({ selected: ['pi', 'dsh'] })
    openMenu()
    expect(screen.getByText('已选 2 个 · 最多 4 个')).toBeTruthy()
  })
})
