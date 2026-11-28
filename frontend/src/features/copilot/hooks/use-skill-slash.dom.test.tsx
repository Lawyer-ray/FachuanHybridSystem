// @vitest-environment jsdom
/**
 * `/` 菜单的技能送达降级提示（jsdom）。
 *
 * 锁的是「三态聚合真的接到了菜单接线点」：`classifySkillDelivery` 是纯函数（三态
 * 单测在 store/backends.test.ts），但纯函数算对了不等于用户看得见——本文件按
 * 「本轮在跑哪些后端」构造 store，断言打开 `/` 菜单时只有降级两档弹提示、
 * 全支持档一声不响。这也顺带锁住「不勾任何后端时按偏好后端算」这条回退。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { toast } from 'sonner'
import { describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  sessionId: null as string | null,
  messages: [] as unknown[],
  compactContext: vi.fn(),
  backends: [] as unknown[],
  answerAgents: [] as string[],
  selectedAgentKind: '',
}))

vi.mock('../store', () => ({
  useCopilot: (selector: (s: typeof storeMock) => unknown) => selector(storeMock),
}))
vi.mock('../api', () => ({ fetchAgentSkills: vi.fn(async () => ({ skills: [] })) }))
vi.mock('../skill-drawer', () => ({
  useSkillDrawer: (selector: (s: { openDrawer: () => void }) => unknown) => selector({ openDrawer: vi.fn() }),
}))
vi.mock('sonner', () => ({ toast: vi.fn() }))

import { SKILL_DELIVERY_HINTS } from '../store/backends'
import { useSkillSlash } from './use-skill-slash'

function option(kind: string, skillDelivery: 'tool_only' | 'prompt') {
  return {
    kind,
    label: kind,
    description: '',
    available: true,
    reason: '',
    capabilities: { streaming: true, skill_delivery: skillDelivery },
  }
}

const pi = option('pi', 'prompt')
const codex = option('codex', 'tool_only')

function renderSlash() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderHook(() => useSkillSlash({ text: '/', setText: vi.fn(), textareaRef: { current: null }, setCaret: vi.fn() }), {
    wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  })
}

describe('useSkillSlash：技能送达三态提示', () => {
  it('全支持：不弹任何降级提示', () => {
    storeMock.backends = [pi]
    storeMock.answerAgents = ['pi']
    renderSlash()
    expect(toast).not.toHaveBeenCalled()
  })

  it('混合降级：弹「自主命中可能不一致」', () => {
    storeMock.backends = [pi, codex]
    storeMock.answerAgents = ['pi', 'codex']
    renderSlash()
    expect(toast).toHaveBeenCalledWith(SKILL_DELIVERY_HINTS.mixed)
  })

  it('仅工具：没勾后端时按偏好后端算，弹点名 /skill:名字 的绕法', () => {
    storeMock.backends = [pi, codex]
    storeMock.answerAgents = []
    storeMock.selectedAgentKind = 'codex'
    renderSlash()
    expect(toast).toHaveBeenCalledWith(SKILL_DELIVERY_HINTS.tool_only)
  })
})
