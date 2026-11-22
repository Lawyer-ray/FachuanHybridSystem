// @vitest-environment jsdom
/**
 * 「这次跑哪几个 AI、各用哪个模型」多选菜单（jsdom）。
 *
 * 必须成立的事实：
 * 1. **选择即增删**：点一项回调一次 kind，顺序由 store 决定（菜单不排序）；
 * 2. **上限 {@link MAX_ANSWERS}**：选满后未选项置灰——超出的选择后端会 400，而那
 *    发生在用户已经敲了回车之后；
 * 3. **不可用项置灰并说明原因**：缺 SDK / 没配 LLM 的后端留着（说明真相是
 *    「这里缺东西」），但点不动；
 * 4. 触发按钮：未选（= 单跑会话默认）时只留图标（省输入框宽度），选了才出文字
 *    （名字 / `N 个 AI`）——身份靠 `aria-label` 说清「会话默认（谁）」；
 * 5. **每行带模型下拉**（规格 4.1）：默认预填 `default_model`、未勾选置灰、
 *    清单为空时整枚下拉消失（降级）。
 * 6. **归属规则写在菜单里**：本菜单是新会话 `agent_kind` 的唯一入口（勾 1 个归它、
 *    勾多个归第一个），这条不能只活在代码注释里——用户看不到就会以为「选 2 个
 *    对比」不会把会话绑到第一家。
 * 7. **关闭时机**：勾选**不**关（勾完还要给那一行选模型），只有点菜单外部空白、
 *    `Escape`（焦点还给触发器）、再点触发器这三种会关。
 */

import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { MAX_ANSWERS } from '../domain'
import type { AgentBackendOption } from '../types'
import { AnswerAgentMenu } from './AnswerAgentMenu'

/** 底部「已选 N 个 · 最多 M 个」的期望文案。
 *
 * M **跟着 {@link MAX_ANSWERS} 算**，不写字面值：上限是产品常量（会随可用后端
 * 增减），把 `4` 写进断言就等于给它加了一颗地雷——常量一变，五条无关的用例
 * 一起红，而下一个人还以为是菜单坏了。 */
const quota = (selected: number) => `已选 ${selected} 个 · 最多 ${MAX_ANSWERS} 个`

function option(
  kind: string,
  label = kind,
  available = true,
  models: string[] = [],
  defaultModel = '',
  approval = true,
): AgentBackendOption {
  return {
    kind,
    label,
    description: `${label} 说明`,
    available,
    reason: available ? '' : '未安装 SDK',
    capabilities: { streaming: true, approval },
    models,
    default_model: defaultModel,
  }
}

const MODELS = ['kimi-2.6', 'glm53', 'claude-opus-4-5']
const backends = [
  option('pi', 'Pi', true, MODELS, 'kimi-2.6'),
  // dsh 没有人工审批闸门（fail-closed 直接拒）；openai-agents 默认有闸门
  // （`FACHUAN_OPENAI_APPROVAL` 默认 on，能力位随开关一起变）
  option('dsh', 'DeepSeek Harness', true, MODELS, 'glm53', false),
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

/**
 * 有状态宿主：`selected` 真的随点击变，才能验「勾完那一行当场就能选模型」——
 * 上面那个 vi.fn 版本永远停在传入的 props 上。
 */
function renderStatefulMenu() {
  function Host() {
    const [selected, setSelected] = useState<string[]>([])
    return (
      <AnswerAgentMenu
        backends={backends}
        selected={selected}
        models={{}}
        defaultKind="pi"
        disabled={false}
        hint=""
        // 与 store/answers.ts 的 toggleAnswerAgent 同语义：已选 = 移除，未选 = 追加
        onToggle={(kind) =>
          setSelected((cur) => (cur.includes(kind) ? cur.filter((k) => k !== kind) : [...cur, kind]))
        }
        onSelectModel={() => {}}
      />
    )
  }
  return render(<Host />)
}

/** 打开菜单（触发按钮的 aria-label 随选择变化，按前缀找） */
function openMenu() {
  fireEvent.click(screen.getByRole('button', { name: /本轮参与的 AI/ }))
}

const MULTI_LISTBOX = { name: '可选 AI（多选）' } as const

describe('AnswerAgentMenu', () => {
  it('未选时触发器收成纯图标：不出文字，身份由 aria-label 说清', () => {
    renderMenu()

    const trigger = screen.getByLabelText('本轮参与的 AI：会话默认（Pi）；点击选择')
    expect(trigger.textContent).toBe('')
    // 省下的就是这串文字占的宽度（约 60px 输入框）
    expect(screen.queryByText('1 个 AI')).toBeNull()
    // 兜底信息仍在：tooltip 说清不选时是谁在答
    expect(trigger.getAttribute('title')).toContain('本轮不选 = 单跑会话默认 AI（Pi）')
  })

  it('清单还没到时，未选态说默认 kind 原文（不留空括号）', () => {
    renderMenu({ backends: [], defaultKind: '' })
    expect(screen.getByLabelText('本轮参与的 AI：会话默认（pi）；点击选择')).toBeTruthy()
  })

  it('选中多个时按钮显示数量（不用点开就知道几栏）', () => {
    renderMenu({ selected: ['pi', 'dsh', 'oai'] })
    const trigger = screen.getByLabelText('本轮参与的 AI：3 个 AI')
    expect(trigger.textContent).toContain('3 个 AI')
  })

  it('只选一个时按钮直接显示那家的名字', () => {
    renderMenu({ selected: ['dsh'] })
    const trigger = screen.getByLabelText('本轮参与的 AI：DeepSeek Harness')
    expect(trigger.textContent).toContain('DeepSeek Harness')
  })

  it('清单没拉到时显示 kind 原文，而不是空白', () => {
    renderMenu({ backends: [], selected: ['pi'] })
    expect(screen.getByLabelText('本轮参与的 AI：pi')).toBeTruthy()
  })

  it('点开菜单列出全部后端，默认那家带「默认」徽标且点名到后端', () => {
    renderMenu()
    openMenu()

    const listbox = screen.getByRole('listbox', { name: '可选 AI（多选）' })
    expect(listbox).toBeTruthy()
    expect(screen.getAllByRole('option')).toHaveLength(backends.length)
    // 默认项（清单第一项）标出来：律师要知道「不选时到底是谁在答」。
    // 徽标取「名字 + 默认 chip」（不取「默认 · 名字」：名字就在左边，再抄一遍会挤破行），
    // 所以名字与默认的绑定要同时落在可见文本、悬停提示与无障碍名上。
    expect(screen.getByText('默认')).toBeTruthy()
    expect(screen.getByText('默认').getAttribute('title')).toContain('会话默认 AI：Pi')
    expect(screen.getByRole('checkbox', { name: 'Pi，会话默认' })).toBeTruthy()
    expect(screen.getByRole('option', { name: /Pi/ }).getAttribute('aria-selected')).toBe('false')
    // 非默认项不挂这枚徽标
    expect(screen.getByTestId('agent-row-dsh').textContent).not.toContain('默认')
  })

  /**
   * 合规信息，必须显示在**勾选之前**：`BackendCapabilities.approval=False` 意味着
   * 高危工具不会弹审批卡（dsh 直接拒绝）。等出事再说是没用的；反过来
   * approval=true（pi / 默认配置的 openai-agents）不能误挂这枚标记。
   */
  it('只有 approval=false 的后端在勾选之前挂「无审批」标记（true 的不挂）', () => {
    renderMenu()
    openMenu()

    const piRow = screen.getByTestId('agent-row-pi')
    const dshRow = screen.getByTestId('agent-row-dsh')
    const oaiRow = screen.getByTestId('agent-row-oai')
    expect(piRow.querySelector('[data-no-approval-badge]')).toBeNull()
    expect(dshRow.querySelector('[data-no-approval-badge]')).toBeTruthy()
    expect(oaiRow.querySelector('[data-no-approval-badge]')).toBeNull()
    // 徽标自己带完整语义（tooltip + aria-label），不靠旁边文字
    expect(dshRow.querySelector('[data-no-approval-badge]')!.getAttribute('title')).toContain('没有人工审批闸门')
  })

  it('点一项回调那次 kind，菜单**不**收起（勾选不是「确认」）', () => {
    const { onToggle } = renderMenu()
    openMenu()
    fireEvent.click(screen.getByRole('checkbox', { name: 'DeepSeek Harness' }))

    expect(onToggle).toHaveBeenCalledWith('dsh')
    expect(screen.getByRole('listbox', MULTI_LISTBOX)).toBeTruthy()
  })

  it('已选项带对勾（aria-checked）', () => {
    renderMenu({ selected: ['dsh'] })
    openMenu()
    expect(screen.getByRole('checkbox', { name: 'DeepSeek Harness' }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('checkbox', { name: 'Pi，会话默认' }).getAttribute('aria-checked')).toBe('false')
  })

  it(`选满 ${MAX_ANSWERS} 个后未选项置灰（超上限后端会 400）`, () => {
    // 造 MAX_ANSWERS+1 个后端：前 MAX_ANSWERS 个选中 = 满额，多出来的那个该置灰
    const allBackends = Array.from({ length: MAX_ANSWERS + 1 }, (_, i) => option(`k${i}`, `第${i + 1}个`))
    const picked = allBackends.slice(0, MAX_ANSWERS).map((b) => b.kind)
    renderMenu({ selected: picked, backends: allBackends, defaultKind: 'k0' })
    openMenu()

    expect(screen.getAllByRole('option')).toHaveLength(allBackends.length)
    // 已选的仍可点（取消不需要名额）
    expect((screen.getByRole('checkbox', { name: '第1个，会话默认' }) as HTMLButtonElement).disabled).toBe(false)
    const overflow = screen.getByRole('checkbox', { name: `第${MAX_ANSWERS + 1}个` }) as HTMLButtonElement
    expect(overflow.disabled).toBe(true)
    expect(overflow.title).toContain(`最多同时问 ${MAX_ANSWERS} 个`)
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
    const trigger = screen.getByLabelText('本轮参与的 AI：会话默认（Pi）；点击选择') as HTMLButtonElement
    expect(trigger.disabled).toBe(true)
    expect(trigger.title).toContain('结束前不能改参与方')
  })

  it('传入的禁用原因优先于默认文案', () => {
    renderMenu({ disabled: true, hint: '发送中，请稍候' })
    expect(
      (screen.getByLabelText('本轮参与的 AI：会话默认（Pi）；点击选择') as HTMLButtonElement).title,
    ).toBe('发送中，请稍候')
  })
})

describe('AnswerAgentMenu：关闭时机（勾选不关，点外部空白 / Escape 才关）', () => {
  it('勾一行后菜单仍然打开，底部「已选 N 个」当场更新', () => {
    renderStatefulMenu()
    openMenu()
    expect(screen.getByText(quota(0))).toBeTruthy()

    fireEvent.click(screen.getByRole('checkbox', { name: 'DeepSeek Harness' }))

    // 菜单一关，用户就得重开再找到那一行才能继续配模型
    expect(screen.getByRole('listbox', MULTI_LISTBOX)).toBeTruthy()
    expect(screen.getByText(quota(1))).toBeTruthy()
    expect(screen.getByRole('checkbox', { name: 'DeepSeek Harness' }).getAttribute('aria-checked')).toBe('true')
  })

  it('勾完那一行的模型下拉立刻可点，且展开/选完不连带关掉父菜单', () => {
    renderStatefulMenu()
    openMenu()
    const picker = () => screen.getByLabelText('DeepSeek Harness 使用的模型：glm53') as HTMLButtonElement
    expect(picker().disabled).toBe(true)

    fireEvent.click(screen.getByRole('checkbox', { name: 'DeepSeek Harness' }))
    expect(picker().disabled).toBe(false)

    // 点下拉触发器（pointerdown 先到 document）→ 父菜单不能把自己判成「外部」
    fireEvent.pointerDown(picker())
    fireEvent.click(picker())
    expect(screen.getByRole('listbox', { name: 'DeepSeek Harness 的模型' })).toBeTruthy()
    expect(screen.getByRole('listbox', MULTI_LISTBOX)).toBeTruthy()

    const model = screen.getByRole('option', { name: 'claude-opus-4-5' })
    fireEvent.pointerDown(model)
    fireEvent.click(model)
    // 模型下拉收起自己那一层，父菜单照旧开着（还要接着配别家）
    expect(screen.queryByRole('listbox', { name: 'DeepSeek Harness 的模型' })).toBeNull()
    expect(screen.getByRole('listbox', MULTI_LISTBOX)).toBeTruthy()
  })

  it('点菜单外部（document.body）→ 关闭', () => {
    renderMenu()
    openMenu()
    expect(screen.getByRole('listbox', MULTI_LISTBOX)).toBeTruthy()

    fireEvent.pointerDown(document.body)

    expect(screen.queryByRole('listbox', MULTI_LISTBOX)).toBeNull()
  })

  it('点菜单内部的空白（底部文案区）→ 不关闭', () => {
    renderMenu()
    openMenu()

    fireEvent.pointerDown(screen.getByText(quota(0)))
    fireEvent.pointerDown(screen.getByText(/新会话也归它/))

    expect(screen.getByRole('listbox', MULTI_LISTBOX)).toBeTruthy()
  })

  it('Escape 关闭并把焦点还给触发器', () => {
    renderMenu()
    openMenu()
    const trigger = screen.getByRole('button', { name: /本轮参与的 AI/ })
    // fireEvent.click 不移动焦点，所以焦点本来不在触发器上
    expect(document.activeElement).not.toBe(trigger)

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('listbox', MULTI_LISTBOX)).toBeNull()
    expect(document.activeElement).toBe(trigger)
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
    expect(screen.getByText(quota(2))).toBeTruthy()
  })

  it('底部一句说清归属规则：勾 1 个＝归它，勾多个＝归第一个', () => {
    renderMenu({ selected: ['pi', 'dsh'] })
    openMenu()

    const rule = screen.getByText(/新会话也归它/)
    expect(rule.textContent).toBe('勾 1 个＝本轮只问它，新会话也归它；勾 2 个以上＝并排对比，会话归属第一个')
    // 数量/上限那行照旧，不被这条文案挤掉
    expect(screen.getByText(quota(2))).toBeTruthy()
  })
})
