// @vitest-environment jsdom
/**
 * 技能抽屉测试（jsdom）。
 *
 * 只覆盖真正会出事的几条：
 * 1. **两个 tab** 各列各的来源，空态有「新建技能」而不是死路；
 * 2. **权限在界面上**：内置行只能「复制为我的」+ 启停，个人行才有编辑/删除；
 * 3. **开关乐观更新**：点了立即变色，失败回滚到请求前的值；
 * 4. **保存前先校验**：服务端字段错误落到对应字段下方，草稿不丢；
 * 5. **首次保存前的一次性告知**：确认后才真的发创建请求，localStorage 记一次；
 * 6. **未保存离开要二次确认**；
 * 7. **`dirty` 不能说谎**：新建态的初始名只生成一次，空表单/改回原样都不算未保存
 *    （render 期间生成名字会让任意重渲染都换名，`dirty` 被永久锁死为真）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  fetchAgentSkills: vi.fn(),
  fetchAgentSkill: vi.fn(),
  createAgentSkill: vi.fn(),
  updateAgentSkill: vi.fn(),
  deleteAgentSkill: vi.fn(),
  setAgentSkillEnabled: vi.fn(),
  validateAgentSkill: vi.fn(),
  duplicateAgentSkill: vi.fn(),
}))
vi.mock('../../skill-api', () => apiMock)

import { useSkillDrawer } from '../../skill-drawer'
import type { AgentSkill } from '../../types'
import { SkillDrawer } from './SkillDrawer'
import { SkillEditor } from './SkillEditor'

function builtin(overrides: Partial<AgentSkill> = {}): AgentSkill {
  return {
    key: 'builtin:web-research',
    name: 'web-research',
    title: 'web-research',
    description: '联网搜索与网页原文抓取',
    enabled: true,
    source: 'builtin',
    scope: '',
    editable: false,
    version: 0,
    ...overrides,
  }
}

function mine(overrides: Partial<AgentSkill> = {}): AgentSkill {
  return {
    key: 'skill:mine-1',
    name: 'contract-review',
    title: '合同审查三段式',
    description: '按四段核对买卖合同',
    enabled: true,
    source: 'user',
    scope: 'lawyer',
    editable: true,
    version: 2,
    ...overrides,
  }
}

function renderDrawer() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  return render(<SkillDrawer />, { wrapper: wrap })
}

/** 打开新建视图并填满必填项（草稿值由调用方给） */
function fillDraft(values: { title: string; name: string; description: string; body: string }) {
  fireEvent.change(screen.getByLabelText('显示名'), { target: { value: values.title } })
  fireEvent.change(screen.getByLabelText('技能名（/skill: 后面的命令名）'), { target: { value: values.name } })
  fireEvent.change(screen.getByLabelText('描述（一句话说清它管什么）'), { target: { value: values.description } })
  fireEvent.change(screen.getByLabelText('正文（AI 执行的做法）'), { target: { value: values.body } })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  useSkillDrawer.setState({ open: true })
  apiMock.fetchAgentSkills.mockResolvedValue({ skills: [builtin(), mine()] })
  apiMock.fetchAgentSkill.mockResolvedValue({ ...mine(), body: '1. 主体\n2. 标的' })
  apiMock.setAgentSkillEnabled.mockResolvedValue({ key: 'skill:mine-1', enabled: false })
  apiMock.validateAgentSkill.mockResolvedValue({ ok: true, errors: [], preview: '---\nname: contract-review' })
  apiMock.createAgentSkill.mockResolvedValue(mine())
  apiMock.deleteAgentSkill.mockResolvedValue(undefined)
  apiMock.duplicateAgentSkill.mockResolvedValue(builtin({ key: 'skill:copy-1', source: 'user', editable: true }))
})

describe('SkillDrawer：两个 tab 与空态', () => {
  it('「我的」列个人技能，「系统」列内置技能', async () => {
    renderDrawer()
    expect(await screen.findByText('合同审查三段式')).toBeTruthy()
    expect(screen.queryByText('web-research')).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: '系统' }))
    // 标题与 slug 都是 web-research（一行两个字位），用 AllBy 避开展开歧义
    expect((await screen.findAllByText('web-research')).length).toBeGreaterThan(0)
    expect(screen.queryByText('合同审查三段式')).toBeNull()
  })

  it('空态给「新建技能」而不是「暂无数据」死路', async () => {
    apiMock.fetchAgentSkills.mockResolvedValue({ skills: [] })
    renderDrawer()
    expect(await screen.findByText(/还没有自己的技能/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '新建技能' }))
    // 进入编辑器：名字已自动生成一份可改的 skill-xxxx
    const nameInput = screen.getByLabelText('技能名（/skill: 后面的命令名）') as HTMLInputElement
    expect(nameInput.value).toMatch(/^skill-[a-z0-9]{4}$/)
  })
})

describe('SkillDrawer：行内动作按来源区分', () => {
  it('个人行有编辑/删除；内置行只有「复制为我的」', async () => {
    renderDrawer()
    await screen.findByText('合同审查三段式')
    expect(screen.getByRole('button', { name: '编辑 合同审查三段式' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '删除 合同审查三段式' })).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: '系统' }))
    expect(await screen.findByRole('button', { name: '复制 web-research 为我的' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /^编辑/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /^删除/ })).toBeNull()
  })

  it('删除个人技能：确认后调用接口', async () => {
    renderDrawer()
    fireEvent.click(await screen.findByRole('button', { name: '删除 合同审查三段式' }))
    expect(await screen.findByText('删除「合同审查三段式」？')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    await waitFor(() => expect(apiMock.deleteAgentSkill).toHaveBeenCalledWith('skill:mine-1'))
  })
})

describe('SkillDrawer：启停', () => {
  it('乐观更新：点击立即变，失败回滚', async () => {
    let rejectToggle: (reason: unknown) => void = () => {}
    apiMock.setAgentSkillEnabled.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectToggle = reject
      }),
    )
    renderDrawer()

    const toggle = await screen.findByRole('switch', { name: '停用 合同审查三段式' })
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    fireEvent.click(toggle)

    // 请求还没回来，开关已经翻面（等往返再变色会被当成没点到）
    await waitFor(() => expect(screen.getByRole('switch', { name: '启用 合同审查三段式' }).getAttribute('aria-checked')).toBe('false'))

    await act(async () => {
      rejectToggle(new Error('boom'))
    })
    await waitFor(() => expect(screen.getByRole('switch', { name: '停用 合同审查三段式' }).getAttribute('aria-checked')).toBe('true'))
  })
})

describe('SkillDrawer：编辑器', () => {
  it('保存前先校验：字段错误落到对应字段，草稿不丢、不发创建请求', async () => {
    apiMock.validateAgentSkill.mockResolvedValue({
      ok: false,
      errors: [{ field: 'name', message: '技能名已被内置技能占用' }],
      preview: '',
    })
    renderDrawer()
    fireEvent.click(await screen.findByRole('button', { name: '新建技能' }))
    fillDraft({ title: '合同审查', name: 'web-research', description: '审买卖合同', body: '1. 主体' })

    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByText('技能名已被内置技能占用')).toBeTruthy()
    // TanStack v5 的 mutationFn 会多给一个 context 参数（client/meta/mutationKey）
    expect(apiMock.validateAgentSkill).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'web-research', title: '合同审查', body: '1. 主体' }),
      expect.anything(),
    )
    // 校验不通过就不该发创建请求，且草稿仍在（关掉等于让人重写）
    expect(apiMock.createAgentSkill).not.toHaveBeenCalled()
    expect((screen.getByLabelText('显示名') as HTMLInputElement).value).toBe('合同审查')
  })

  it('首次保存前弹一次告知，确认后才创建；localStorage 记一次', async () => {
    renderDrawer()
    fireEvent.click(await screen.findByRole('button', { name: '新建技能' }))
    fillDraft({ title: '合同审查', name: 'contract-check', description: '审买卖合同', body: '1. 主体' })

    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByText('写技能前须知')).toBeTruthy()
    expect(apiMock.createAgentSkill).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '我知道了，继续保存' }))
    await waitFor(() => expect(apiMock.createAgentSkill).toHaveBeenCalled())
    expect(localStorage.getItem('fachuan:skill-notice:v1')).toBe('1')
  })

  it('有未保存改动时点「取消」要二次确认，确认后回到列表', async () => {
    renderDrawer()
    fireEvent.click(await screen.findByRole('button', { name: '新建技能' }))
    fireEvent.change(screen.getByLabelText('显示名'), { target: { value: '写了一半' } })

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(await screen.findByText('放弃未保存的修改？')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }))
    await waitFor(() => expect(screen.getByRole('tab', { name: '我的' })).toBeTruthy())
  })

  it('空表单点抽屉关闭（X）不弹放弃确认：dirty 不因重渲染变真', async () => {
    renderDrawer()
    fireEvent.click(await screen.findByRole('button', { name: '新建技能' }))
    // 改一个字再删回去：草稿回到初值，dirty 必须跟着回落
    const title = screen.getByLabelText('显示名')
    fireEvent.change(title, { target: { value: 'x' } })
    fireEvent.change(title, { target: { value: '' } })

    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    await waitFor(() => expect(useSkillDrawer.getState().open).toBe(false))
    expect(screen.queryByText('放弃未保存的修改？')).toBeNull()
  })

  it('有未保存改动时点抽屉关闭（X）同样要二次确认', async () => {
    renderDrawer()
    fireEvent.click(await screen.findByRole('button', { name: '新建技能' }))
    fireEvent.change(screen.getByLabelText('显示名'), { target: { value: '写了一半' } })

    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(await screen.findByText('放弃未保存的修改？')).toBeTruthy()
    // 还没确认：抽屉不能已经关掉
    expect(useSkillDrawer.getState().open).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }))
    await waitFor(() => expect(useSkillDrawer.getState().open).toBe(false))
  })
})

describe('SkillEditor：dirty 只说真话', () => {
  /** 直接渲染编辑器：`dirty` 是它上报给抽屉的唯一出口，在这一层断言最直接 */
  function renderEditor(onDirtyChange: (dirty: boolean) => void) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    const wrap = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    return render(<SkillEditor target={{ mode: 'create' }} onClose={() => {}} onDirtyChange={onDirtyChange} />, { wrapper: wrap })
  }

  it('新建态重渲染不换初始名（初始名只生成一次）', () => {
    const onDirtyChange = vi.fn()
    const { rerender } = renderEditor(onDirtyChange)
    const nameInput = () => screen.getByLabelText('技能名（/skill: 后面的命令名）') as HTMLInputElement
    const first = nameInput().value
    expect(first).toMatch(/^skill-[a-z0-9]{4}$/)

    // 外部重渲染（抽屉切 tab、清单刷新都会触发）：名字不能被换掉，dirty 不能变真
    rerender(<SkillEditor target={{ mode: 'create' }} onClose={() => {}} onDirtyChange={onDirtyChange} />)
    expect(nameInput().value).toBe(first)
    expect(onDirtyChange).toHaveBeenLastCalledWith(false)
  })

  it('改了又改回原样：dirty 回落到 false', () => {
    const onDirtyChange = vi.fn()
    renderEditor(onDirtyChange)
    const title = screen.getByLabelText('显示名')

    fireEvent.change(title, { target: { value: '写了一半' } })
    expect(onDirtyChange).toHaveBeenLastCalledWith(true)

    fireEvent.change(title, { target: { value: '' } })
    expect(onDirtyChange).toHaveBeenLastCalledWith(false)
  })
})
