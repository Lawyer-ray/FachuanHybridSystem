// @vitest-environment jsdom
/**
 * 命令名漂移提示测试（jsdom）。
 *
 * 守的是「提示既不漏也不烦」：
 * 1. **首次观察不提示**：挂载时还不知道「之前是谁」，把它当漂移会在每次打开抽屉时都弹；
 * 2. **同一次挂载只弹一次**：清单刷新（启停、保存、切 tab 都会重拉）会反复触发赢家比对，
 *    没有内存去重会连着弹好几遍；
 * 3. **换 user 或换 name 会再弹**：存储键是 `user + name`——同一台机器换个人登录时，
 *    那个名字的层级归属是另一件事，用裸 name 记会让第二个人永远收不到提示；
 * 4. 判定只读服务端 `effective`：这里刻意让「个人版被停用、所内版顶上来」这一组数据
 *    说话，不给前端任何推算级联的余地。
 */
import { render } from '@testing-library/react'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const toastStubs = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastStubs }))

import { useAuth } from '@/features/auth'

import type { AgentSkill } from '../../types'
import { contendedSkillNames, skillDriftToastKey, useSkillDrift } from './use-skill-drift'

/** 一条技能的完整形状（本组判据只看 name / effective / scope，其余给最小合法值） */
function skill(overrides: Partial<AgentSkill> & Pick<AgentSkill, 'key' | 'name'>): AgentSkill {
  return {
    title: '同名技能',
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
    effective: false,
    shadowed_by: null,
    can_edit: true,
    can_submit: false,
    can_review: false,
    can_archive: false,
    can_restore: false,
    ...overrides,
  }
}

/** 「个人版赢」的一轮清单：个人生效、所内被遮蔽 */
const PERSONAL_WINS: AgentSkill[] = [
  skill({ key: 'skill:p1', name: 'contract-review', scope: 'lawyer', title: '我的合同审查', effective: true }),
  skill({
    key: 'skill:f1',
    name: 'contract-review',
    scope: 'law_firm',
    scope_weight: 2,
    title: '所内合同审查',
    shadowed_by: { key: 'skill:p1', scope: 'lawyer', title: '我的合同审查' },
  }),
]

/** 「所内版顶上来」：个人版被停用（不再是可交付），所内版胜出 */
const FIRM_WINS: AgentSkill[] = [
  skill({ key: 'skill:p1', name: 'contract-review', scope: 'lawyer', title: '我的合同审查', enabled: false }),
  skill({ key: 'skill:f1', name: 'contract-review', scope: 'law_firm', scope_weight: 2, title: '所内合同审查', effective: true }),
]

/** 只跑 hook、不渲染任何东西：本组判据全在「什么时候弹」上 */
function DriftProbe({ skills }: { skills: AgentSkill[] }) {
  useSkillDrift(skills)
  return null
}

function signInAs(id: number): void {
  act(() => {
    useAuth.setState({ user: { id, username: `lawyer-${id}`, avatar_url: null } })
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  signInAs(7)
})

describe('useSkillDrift：提示时机', () => {
  it('首次观察不提示；赢家换层只提示一次，存储键按 user+name 记', () => {
    const { rerender } = render(<DriftProbe skills={PERSONAL_WINS} />)
    // 挂载时没有基线：不该弹
    expect(toastStubs.info).not.toHaveBeenCalled()

    rerender(<DriftProbe skills={FIRM_WINS} />)
    expect(toastStubs.info).toHaveBeenCalledTimes(1)
    expect(String(toastStubs.info.mock.calls[0]?.[0])).toContain('/skill:contract-review')
    expect(localStorage.getItem(skillDriftToastKey('u7', 'contract-review'))).toBe('1')

    // 再换回来、再换过去：同一次挂载里对同一个名字不再重复打扰
    rerender(<DriftProbe skills={PERSONAL_WINS} />)
    rerender(<DriftProbe skills={FIRM_WINS} />)
    expect(toastStubs.info).toHaveBeenCalledTimes(1)
  })

  it('换 user 会再弹一次（同一台机器换人登录是另一件事）', () => {
    const { rerender } = render(<DriftProbe skills={PERSONAL_WINS} />)
    rerender(<DriftProbe skills={FIRM_WINS} />)
    expect(toastStubs.info).toHaveBeenCalledTimes(1)

    signInAs(8)
    // u8 视角下赢家又变了一次：存储键换了，所以必须重新提示
    rerender(<DriftProbe skills={PERSONAL_WINS} />)
    expect(toastStubs.info).toHaveBeenCalledTimes(2)
    expect(localStorage.getItem(skillDriftToastKey('u8', 'contract-review'))).toBe('1')
  })

  it('换 name 会再弹一次（两个名字各自计数）', () => {
    const before = [
      skill({ key: 'skill:p1', name: 'contract-review', effective: true }),
      skill({ key: 'skill:f1', name: 'contract-review', scope: 'law_firm', scope_weight: 2 }),
      skill({ key: 'skill:p2', name: 'firm-checklist', effective: true }),
      skill({ key: 'skill:f2', name: 'firm-checklist', scope: 'law_firm', scope_weight: 2 }),
    ]
    const after = [
      skill({ key: 'skill:p1', name: 'contract-review' }),
      skill({ key: 'skill:f1', name: 'contract-review', scope: 'law_firm', scope_weight: 2, effective: true }),
      skill({ key: 'skill:p2', name: 'firm-checklist' }),
      skill({ key: 'skill:f2', name: 'firm-checklist', scope: 'law_firm', scope_weight: 2, effective: true }),
    ]

    const { rerender } = render(<DriftProbe skills={before} />)
    rerender(<DriftProbe skills={after} />)

    expect(toastStubs.info).toHaveBeenCalledTimes(2)
    const messages = toastStubs.info.mock.calls.map((call) => String(call[0]))
    expect(messages.some((text) => text.includes('/skill:contract-review'))).toBe(true)
    expect(messages.some((text) => text.includes('/skill:firm-checklist'))).toBe(true)
  })
})

describe('contendedSkillNames', () => {
  it('只把「有同名竞争」的名字算进来：独一条的名字不需要行内标注', () => {
    const skills = [...PERSONAL_WINS, skill({ key: 'skill:solo', name: 'web-research', effective: true })]
    const contended = contendedSkillNames(skills)
    expect([...contended]).toEqual(['contract-review'])
  })
})
