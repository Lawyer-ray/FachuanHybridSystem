// @vitest-environment jsdom
/**
 * 技能抽屉的「信息是否说真话」测试（jsdom）：tab 显隐与切换、双轨徽标、覆盖关系、
 * 配额条、正文字节提示。
 *
 * 这些判据都不能靠肉眼在真机上验：
 * 1. **tab 显隐只由服务端驱动**：有对应条目或 `can_create_firm` 才出现，绝不判 `is_admin`；
 * 2. **双轨徽标**：已生效 / 草稿 / 待审（有未发布改动）/ 已驳回（附理由）/ 已下线；
 * 3. **覆盖关系**：被谁覆盖要写中文名，覆盖了谁要写层级——`/skill:名字` 只展开赢家；
 * 4. **配额按当前作用域**：`used / max` 取 `by_scope`，满了禁用新建并说明原因；
 * 5. **字节提示**：>16KB 说分段、>32KB 说提交会被拒（两个上限都是字节，不是字数）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  fetchAgentSkills: vi.fn(),
  fetchAgentSkill: vi.fn(),
  fetchAgentSkillQuota: vi.fn(),
  createAgentSkill: vi.fn(),
  updateAgentSkill: vi.fn(),
  deleteAgentSkill: vi.fn(),
  setAgentSkillEnabled: vi.fn(),
  validateAgentSkill: vi.fn(),
  duplicateAgentSkill: vi.fn(),
}))
vi.mock('../../skill-api', () => apiMock)

const toastStubs = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastStubs }))

import { toast } from 'sonner'

import { useSkillDrawer } from '../../skill-drawer'
import type { AgentSkill } from '../../types'
import { SkillDrawer } from './SkillDrawer'

function skill(overrides: Partial<AgentSkill> & Pick<AgentSkill, 'key' | 'name' | 'title'>): AgentSkill {
  return {
    description: '一句话说明',
    enabled: true,
    source: 'user',
    scope: 'lawyer',
    scope_weight: 0,
    editable: true,
    version: 1,
    status: 'active',
    review_status: 'none',
    review_note: '',
    published_version: 1,
    has_unpublished_changes: false,
    shadowed: [],
    effective: true,
    shadowed_by: null,
    can_edit: true,
    can_submit: false,
    can_review: false,
    can_archive: false,
    can_restore: false,
    ...overrides,
  }
}

const MINE = skill({ key: 'skill:mine-1', name: 'contract-review', title: '合同审查三段式' })
const BUILTIN = skill({
  key: 'builtin:web-research',
  name: 'web-research',
  title: '联网检索',
  source: 'builtin',
  scope: 'builtin',
  scope_weight: -1,
  editable: false,
  can_edit: false,
})
const FIRM = skill({
  key: 'skill:firm-1',
  name: 'firm-checklist',
  title: '所内核对清单',
  source: 'law_firm',
  scope: 'law_firm',
  scope_weight: 2,
  can_edit: false,
})
const TEAM = skill({
  key: 'skill:team-1',
  name: 'team-checklist',
  title: '团队核对清单',
  source: 'team',
  scope: 'team',
  scope_weight: 1,
  can_edit: false,
})

/** 配额回执（缺省：个人 3/20，共享层给 0 → 不显示共享层配额条） */
function quota(overrides: Record<string, unknown> = {}) {
  return {
    max_skills: 20,
    used: 3,
    by_scope: { lawyer: 3, team: 0, law_firm: 0 },
    max_by_scope: { lawyer: 20, team: 0, law_firm: 0 },
    can_create_firm: false,
    ...overrides,
  }
}

function renderDrawer() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  return render(<SkillDrawer />, { wrapper: wrap })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  useSkillDrawer.setState({ open: true })
  apiMock.fetchAgentSkills.mockResolvedValue({ skills: [MINE, BUILTIN] })
  apiMock.fetchAgentSkillQuota.mockResolvedValue(quota())
  apiMock.setAgentSkillEnabled.mockResolvedValue({ key: MINE.key, enabled: false })
  apiMock.validateAgentSkill.mockResolvedValue({ ok: true, errors: [], preview: '---' })
  apiMock.createAgentSkill.mockResolvedValue(MINE)
})

describe('tab：显隐与切换', () => {
  it('空态给「新建技能」而不是「暂无数据」死路', async () => {
    apiMock.fetchAgentSkills.mockResolvedValue({ skills: [] })
    renderDrawer()
    expect(await screen.findByText(/还没有自己的技能/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '新建技能' }))
    // 进入编辑器：名字已自动生成一份可改的 skill-xxxx
    const nameInput = screen.getByLabelText('技能名（/skill: 后面的命令名）') as HTMLInputElement
    expect(nameInput.value).toMatch(/^skill-[a-z0-9]{4}$/)
  })

  it('有团队 / 所内条目时四个 tab 都在，点谁列谁', async () => {
    apiMock.fetchAgentSkills.mockResolvedValue({ skills: [MINE, FIRM, TEAM, BUILTIN] })
    renderDrawer()
    for (const name of ['我的', '所内', '团队', '系统']) {
      expect(await screen.findByRole('tab', { name })).toBeTruthy()
    }

    fireEvent.click(screen.getByRole('tab', { name: '所内' }))
    expect(await screen.findByText('所内核对清单')).toBeTruthy()
    expect(screen.queryByText('合同审查三段式')).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: '团队' }))
    expect(await screen.findByText('团队核对清单')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: '系统' }))
    expect(await screen.findByText('联网检索')).toBeTruthy()
  })

  it('没有团队条目时「团队」tab 不出现（团队层未上线，前端不空开一格）', async () => {
    apiMock.fetchAgentSkills.mockResolvedValue({ skills: [MINE, FIRM, BUILTIN] })
    renderDrawer()
    expect(await screen.findByRole('tab', { name: '所内' })).toBeTruthy()
    expect(screen.queryByRole('tab', { name: '团队' })).toBeNull()
  })

  it('服务端 can_create_firm=true 时，即使还没有所内条目也出现「所内」tab', async () => {
    apiMock.fetchAgentSkills.mockResolvedValue({ skills: [MINE] })
    apiMock.fetchAgentSkillQuota.mockResolvedValue(
      quota({ can_create_firm: true, max_by_scope: { lawyer: 20, team: 30, law_firm: 60 } }),
    )
    renderDrawer()
    expect(await screen.findByRole('tab', { name: '所内' })).toBeTruthy()
    expect(screen.queryByRole('tab', { name: '团队' })).toBeNull()
  })

  it('待审角标只数「服务端说我能审」的条目', async () => {
    apiMock.fetchAgentSkills.mockResolvedValue({
      skills: [
        MINE,
        skill({ ...FIRM, review_status: 'pending', has_unpublished_changes: true, can_review: true }),
        skill({ ...FIRM, key: 'skill:firm-2', name: 'firm-other', title: '别人的待审', can_review: false, review_status: 'pending' }),
      ],
    })
    renderDrawer()
    const firmTab = await screen.findByRole('tab', { name: '所内' })
    // 角标是对屏幕阅读器隐藏的装饰，数字留在 title 里（否则 tab 的可访问名会变成「所内 1」）
    expect(firmTab.getAttribute('title')).toBe('所内（1 条待你审批）')
  })
})

describe('双轨状态徽标', () => {
  it('已生效 / 草稿 / 待审（有未发布改动）/ 已驳回（带理由）/ 已下线', async () => {
    apiMock.fetchAgentSkills.mockResolvedValue({
      skills: [
        skill({ key: 'skill:a', name: 's-active', title: '生效中的技能' }),
        skill({ key: 'skill:b', name: 's-draft', title: '没发布过的技能', status: 'draft' }),
        skill({
          key: 'skill:c',
          name: 's-pending',
          title: '改动待审的技能',
          review_status: 'pending',
          has_unpublished_changes: true,
          published_version: 1,
          version: 2,
        }),
        skill({
          key: 'skill:d',
          name: 's-rejected',
          title: '被驳回的技能',
          review_status: 'rejected',
          review_note: '第 3 段写了客户全名，请删掉',
        }),
        skill({ key: 'skill:e', name: 's-archived', title: '已下线的技能', status: 'archived' }),
      ],
    })
    renderDrawer()

    expect(await screen.findByText('已生效')).toBeTruthy()
    expect(screen.getByText('草稿')).toBeTruthy()
    expect(screen.getByText('待审（有未发布改动）')).toBeTruthy()
    expect(screen.getByText('已驳回')).toBeTruthy()
    expect(screen.getByText('已下线')).toBeTruthy()
    // 驳回理由必须能读到（律师要知道为什么被驳回）：徽标 title 就是 review_note
    expect(screen.getByText('已驳回').getAttribute('title')).toBe('第 3 段写了客户全名，请删掉')
    // 已下线的条目不在运行时集合里，开关没有意义
    expect(screen.queryByRole('switch', { name: /已下线的技能/ })).toBeNull()
  })
})

describe('覆盖关系', () => {
  it('「我的」列覆盖了所内版；「所内」列被「我的」同名技能覆盖（带中文名）', async () => {
    apiMock.fetchAgentSkills.mockResolvedValue({
      skills: [
        skill({
          ...MINE,
          shadowed: [{ key: FIRM.key, scope: 'law_firm', title: '所内核对清单' }],
        }),
        skill({
          ...FIRM,
          effective: false,
          shadowed_by: { key: MINE.key, scope: 'lawyer', title: '合同审查三段式' },
        }),
      ],
    })
    renderDrawer()

    expect(await screen.findByText('覆盖了所内版')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: '所内' }))
    // 赢家的中文名要写出来：律师认的是「合同审查三段式」，不是 slug
    expect(await screen.findByText('被「我的」同名技能「合同审查三段式」覆盖')).toBeTruthy()
  })
})

describe('共享技能的启停只是偏好', () => {
  it('可访问名与 toast 都写「仅对我」，不让人以为关了全所的那一条', async () => {
    apiMock.fetchAgentSkills.mockResolvedValue({ skills: [FIRM] })
    apiMock.setAgentSkillEnabled.mockResolvedValue({ key: FIRM.key, enabled: false })
    renderDrawer()

    fireEvent.click(await screen.findByRole('tab', { name: '所内' }))
    const toggle = await screen.findByRole('switch', { name: '仅对我停用 所内核对清单' })
    expect(toggle.getAttribute('title')).toBe('只改你自己的使用偏好，不影响其他律师')

    fireEvent.click(toggle)
    await waitFor(() =>
      expect(vi.mocked(toast.success)).toHaveBeenCalledWith('已停用「所内核对清单」', {
        description: '仅对你生效，不影响其他律师；下一轮对话生效',
      }),
    )
  })
})

describe('配额条', () => {
  it('按当前 tab 的作用域显示 used / max', async () => {
    apiMock.fetchAgentSkillQuota.mockResolvedValue(
      quota({ by_scope: { lawyer: 3, team: 0, law_firm: 0 }, max_by_scope: { lawyer: 20, team: 30, law_firm: 60 }, can_create_firm: true }),
    )
    renderDrawer()
    expect(await screen.findByText('已用 3 / 20')).toBeTruthy()
    expect(screen.getByRole('progressbar', { name: '我的配额已用' }).getAttribute('aria-valuemax')).toBe('20')

    fireEvent.click(screen.getByRole('tab', { name: '所内' }))
    expect(await screen.findByText('已用 0 / 60')).toBeTruthy()
  })

  it('满额禁用「新建」并说明原因', async () => {
    apiMock.fetchAgentSkillQuota.mockResolvedValue(
      quota({ used: 20, by_scope: { lawyer: 20, team: 0, law_firm: 0 } }),
    )
    renderDrawer()
    expect(await screen.findByText('已用 20 / 20')).toBeTruthy()
    expect(screen.getByText('我的技能已达上限 20/20，先下线不用的技能再新建')).toBeTruthy()
    const create = screen.getByRole('button', { name: '新建技能' }) as HTMLButtonElement
    expect(create.disabled).toBe(true)
    expect(create.getAttribute('title')).toBe('我的技能已达上限 20/20，先下线不用的技能再新建')
  })
})

describe('正文长度提示', () => {
  async function openCreateAndType(body: string) {
    renderDrawer()
    fireEvent.click(await screen.findByRole('button', { name: '新建技能' }))
    fireEvent.change(screen.getByLabelText('正文（AI 执行的做法）'), { target: { value: body } })
  }

  it('超过 16KB：柔和提示「按需读取会分段」', async () => {
    await openCreateAndType('a'.repeat(16_001))
    expect(await screen.findByText(/16001 字节/)).toBeTruthy()
    expect(screen.getByText(/超过 16KB 后，AI 按需读取会分段/)).toBeTruthy()
  })

  it('超过 32KB：说清提交会被拒绝', async () => {
    await openCreateAndType('a'.repeat(32_769))
    expect(await screen.findByText(/32769 字节/)).toBeTruthy()
    expect(screen.getByText(/超过 32KB，提交会被拒绝/)).toBeTruthy()
  })
})
