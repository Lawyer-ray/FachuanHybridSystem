// @vitest-environment jsdom
/**
 * 提审/发布对话框测试（jsdom）。守的是「作者能不能一次填对」这件事：
 *
 * 1. **字段级错误就地回显**：`/skills/validate` 说技能名撞了，错误必须落在技能名
 *    输入框下方，而且**不发提审请求**（只弹一句 toast 等于让人猜哪个框错了）；
 * 2. **hard 命中阻止提交**：按钮禁用且写明原因，点了也不会打接口；
 * 3. **soft 命中必须勾选**：没勾不让提交，勾了才允许，且提交的载荷不多不少；
 * 4. **目标层只渲染服务端 `promotable_scopes`**：前端不硬编码层级，也不拿 is_admin 猜；
 *    所内层还要勾「已确认在全所范围内成立」——那是服务端会拒的前置条件。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  fetchAgentSkill: vi.fn(),
  validateAgentSkill: vi.fn(),
  submitAgentSkill: vi.fn(),
}))
vi.mock('../../skill-api', () => apiMock)

const toastStubs = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastStubs }))

import type { AgentSkill } from '../../types'
import { SkillPromoteDialog } from './SkillPromoteDialog'

/** 一条个人技能：服务端允许提升时才有 `can_promote` 与 `promotable_scopes` */
function mineSkill(overrides: Partial<AgentSkill> = {}): AgentSkill {
  return {
    key: 'skill:mine-1',
    name: 'contract-review',
    title: '合同审查三段式',
    description: '按四段核对买卖合同',
    enabled: true,
    source: 'user',
    scope: 'lawyer',
    scope_weight: 0,
    editable: true,
    version: 2,
    status: 'active',
    review_status: 'none',
    review_note: '',
    published_version: 2,
    has_unpublished_changes: false,
    shadowed: [],
    effective: true,
    shadowed_by: null,
    can_edit: true,
    can_submit: false,
    can_review: false,
    can_archive: false,
    can_restore: false,
    can_promote: true,
    promotable_scopes: ['team'],
    ...overrides,
  }
}

function finding(overrides: Partial<{ code: string; level: string; field: string; message: string; excerpt: string }> = {}) {
  return {
    code: 'entity_name',
    level: 'soft',
    field: 'body',
    message: '出现完整主体名',
    excerpt: '某某律师事务所',
    ...overrides,
  }
}

function renderDialog(skill: AgentSkill) {
  const onPromoted = vi.fn()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  const view = render(<SkillPromoteDialog skill={skill} onOpenChange={vi.fn()} onPromoted={onPromoted} />, { wrapper: wrap })
  return { ...view, onPromoted }
}

/** 技能名输入框（标签与编辑器同一套说法，律师不用学两遍） */
function slugInput(): HTMLInputElement {
  return screen.getByLabelText('技能名（/skill: 后面的命令名）') as HTMLInputElement
}

function submitButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: '提审' }) as HTMLButtonElement
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.fetchAgentSkill.mockResolvedValue({ ...mineSkill(), body: '1. 主体\n2. 标的' })
  apiMock.validateAgentSkill.mockResolvedValue({ ok: true, errors: [], preview: '', safety: [] })
  apiMock.submitAgentSkill.mockResolvedValue({ ...mineSkill(), review_status: 'pending' })
})

describe('SkillPromoteDialog：字段级错误', () => {
  it('技能名撞名：错误落在输入框下方，且不发提审请求', async () => {
    apiMock.validateAgentSkill.mockResolvedValue({
      ok: false,
      errors: [{ field: 'name', message: '技能名「contract-review」已被所内同名技能占用' }],
      preview: '',
      safety: [],
    })
    renderDialog(mineSkill())

    fireEvent.change(await screen.findByLabelText('技能名（/skill: 后面的命令名）'), {
      target: { value: 'contract-review-2' },
    })
    fireEvent.click(submitButton())

    expect(await screen.findByText('技能名「contract-review」已被所内同名技能占用')).toBeTruthy()
    expect(apiMock.submitAgentSkill).not.toHaveBeenCalled()
    // 名字没改成合规值前，草稿仍在输入框里（不因一次失败把填的东西清掉）
    expect(slugInput().value).toBe('contract-review-2')
  })
})

describe('SkillPromoteDialog：安全闸门', () => {
  it('hard 命中直接阻止提交，并写明原因', async () => {
    apiMock.validateAgentSkill.mockResolvedValue({
      ok: true,
      errors: [],
      preview: '',
      safety: [finding({ code: 'id_card', level: 'hard', message: '疑似身份证号', excerpt: '11******22' })],
    })
    renderDialog(mineSkill())

    expect(await screen.findByText(/正文命中硬性敏感信息/)).toBeTruthy()
    expect(submitButton().disabled).toBe(true)
    fireEvent.click(submitButton())
    expect(apiMock.submitAgentSkill).not.toHaveBeenCalled()
  })

  it('soft 命中必须先勾选确认，勾了才提交成功', async () => {
    apiMock.validateAgentSkill.mockResolvedValue({ ok: true, errors: [], preview: '', safety: [finding()] })
    const { onPromoted } = renderDialog(mineSkill())

    expect(await screen.findByText(/请先逐条核对上面的软告警/)).toBeTruthy()
    expect(submitButton().disabled).toBe(true)

    fireEvent.click(screen.getByRole('checkbox', { name: /我已逐条核对上面的 1 条软告警/ }))
    await waitFor(() => expect(submitButton().disabled).toBe(false))
    fireEvent.click(submitButton())

    await waitFor(() => expect(apiMock.submitAgentSkill).toHaveBeenCalledWith('skill:mine-1', { target_scope: 'team' }))
    expect(onPromoted).toHaveBeenCalledWith('team')
  })
})

describe('SkillPromoteDialog：目标层', () => {
  it('目标层只渲染服务端 promotable_scopes 给的那几层', async () => {
    renderDialog(mineSkill({ promotable_scopes: ['law_firm', 'team'] }))

    const select = (await screen.findByLabelText('发布到哪一层')) as HTMLSelectElement
    expect([...select.options].map((option) => option.value)).toEqual(['law_firm', 'team'])
  })

  it('只有所内一个目标时不给选择器，且必须勾选全所确认才能提交', async () => {
    renderDialog(mineSkill({ promotable_scopes: ['law_firm'] }))

    expect(await screen.findByText(/发布到所内会影响全所律师/)).toBeTruthy()
    expect(screen.queryByLabelText('发布到哪一层')).toBeNull()
    expect(submitButton().disabled).toBe(true)

    fireEvent.click(screen.getByRole('checkbox', { name: /我已确认这条指令在全所范围内成立/ }))
    await waitFor(() => expect(submitButton().disabled).toBe(false))
  })
})
