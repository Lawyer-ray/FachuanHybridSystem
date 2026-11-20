/**
 * `noMoreHistory` 判据的边界与同步（node 环境，纯 store 状态机）。
 *
 * 为什么单独一个文件：它锁的是**一个数**（还有没有更早的历史），而错判的两个方向
 * 代价不对称但都很难复现——
 * - 漏判（实际有更早却判「到头」）：律师永远翻不到三个月前的那段分析，**没有任何
 *   报错**，只会以为「记录丢了」；
 * - 错判（实际到头却还显示按钮）：每次滑到顶都白打一次必然空的请求，看着像卡住。
 *
 * 被测契约（对应 `store/session.ts` 的 `isLastHistoryPage`）：
 * 1. 判据只有一条：「本批返回条数 < 一页」。首屏（最新一页）、游标页（更早一页）、
 *    轮询刷新（重取最新一页）三处**都必须**用它，任何一处漏掉就会出现本节 2 的
 *    那个 bug；
 * 2. `refreshHistory` 替换转录时必须**重算**：原实现在这里不更新，于是
 *    「翻到底（true）→ 任务跑完轮询刷新把转录换回最新一页 → 按钮永久消失」；
 * 3. 会话边界上清零：翻页状态是**上一个会话的事实**，不能跟着切到下一个会话。
 *
 * 与 `store/session-history.test.ts`（游标/守卫/失败静默）不重叠，这一份只打边界。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { HISTORY_PAGE_SIZE } from './domain'
import { useCopilot } from './store'
import type { AgentHistoryMessage } from './types'

vi.mock('./api', () => ({
  createSession: vi.fn(),
  fetchHistory: vi.fn(),
  openMessageStream: vi.fn(),
  decideApproval: vi.fn(),
  listSessions: vi.fn(),
  deleteSession: vi.fn(),
  steerSession: vi.fn(),
  clearSessionQueue: vi.fn(),
  submitAgentTask: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  uploadAttachment: vi.fn(),
}))

const fetchHistory = vi.mocked(copilotApi.fetchHistory)

/** 造一行后端历史（`message_id` 决定 `db-` 前缀 id，翻页靠它当游标） */
function row(messageId: number): AgentHistoryMessage {
  return { message_id: messageId, role: 'user', content: `消息 ${messageId}` } as AgentHistoryMessage
}

/** 造 n 行历史（id 从 from 开始递增） */
function rows(n: number, from = 1): AgentHistoryMessage[] {
  return Array.from({ length: n }, (_, i) => row(from + i))
}

beforeEach(() => {
  vi.clearAllMocks()
  // 用 reset 而不是手写 setState：新增状态字段时这里不会漏（漏了就会出现
  // 「上个用例的 noMoreHistory 留在 true，后面整组用例全在守卫处静默返回」）
  useCopilot.getState().reset()
})

/** 打开一个会话（首屏历史由调用方先 mock 好） */
async function open(sessionId: string): Promise<void> {
  await useCopilot.getState().switchSession(sessionId)
}

describe('首屏分页边界：100 / 199 / 200 / 201 条', () => {
  // 后端 `list_messages` 不传 before_id 时返**最新一页**（`created_at desc` 取 limit
  // 条再反转），所以「首批不足一页」就等于「总共不足一页」——这正是判据成立的前提。
  it('100 条（不足一页）→ 判定到头，且翻页按钮点不动', async () => {
    fetchHistory.mockResolvedValue(rows(100))
    await open('s-100')

    expect(useCopilot.getState().messages).toHaveLength(100)
    expect(useCopilot.getState().noMoreHistory).toBe(true)

    // 再来一次「加载更早」必须是**零请求**：100 条已经全在了，再问就是白问
    await useCopilot.getState().loadOlderHistory()
    expect(fetchHistory).toHaveBeenCalledTimes(1)
  })

  it('199 条（差一条满页）→ 同样判定到头', async () => {
    fetchHistory.mockResolvedValue(rows(199))
    await open('s-199')

    expect(useCopilot.getState().messages).toHaveLength(199)
    expect(useCopilot.getState().noMoreHistory).toBe(true)

    await useCopilot.getState().loadOlderHistory()
    expect(fetchHistory).toHaveBeenCalledTimes(1)
  })

  it('正好 200 条 → 不判定到头；下一次翻页拿到 0 条才收敛', async () => {
    fetchHistory.mockResolvedValueOnce(rows(200)).mockResolvedValueOnce([])
    await open('s-200')

    // 一整页说明可能被 limit 切断了（也可能刚好 200 条），前端只能先假设还有
    expect(useCopilot.getState().noMoreHistory).toBe(false)

    await useCopilot.getState().loadOlderHistory()
    // 一次白请求换来确定性：0 条 ⟹ 到头，按钮消失
    expect(fetchHistory).toHaveBeenLastCalledWith('s-200', HISTORY_PAGE_SIZE, 1)
    expect(useCopilot.getState().noMoreHistory).toBe(true)
  })

  it('201 条 → 首屏 200 条不判到头，翻到第 201 条后判定到头', async () => {
    fetchHistory.mockResolvedValueOnce(rows(200, 2)).mockResolvedValueOnce([row(1)])
    await open('s-201')

    expect(useCopilot.getState().noMoreHistory).toBe(false)

    await useCopilot.getState().loadOlderHistory()

    expect(useCopilot.getState().messages.map((m) => m.id)).toHaveLength(201)
    expect(useCopilot.getState().messages[0]?.id).toBe('db-1')
    expect(useCopilot.getState().noMoreHistory).toBe(true)
  })

  it('游标页正好满页 → 不判到头（用户还能继续往上翻）', async () => {
    fetchHistory.mockResolvedValueOnce(rows(200, 201)).mockResolvedValueOnce(rows(200, 1))
    await open('s-400')

    await useCopilot.getState().loadOlderHistory()

    expect(useCopilot.getState().messages).toHaveLength(400)
    expect(useCopilot.getState().noMoreHistory).toBe(false)
  })
})

describe('refreshHistory 必须同步维护 noMoreHistory', () => {
  it('翻到底之后轮询刷新：转录换回最新一页，按钮必须回来（否则更早的消息永久不可达）', async () => {
    // 真实场景：250 条的会话，律师翻到最老那 50 条（判到头），
    // 后台任务跑完触发 refreshHistory → 转录被换成最新 200 条。
    fetchHistory.mockResolvedValueOnce(rows(200, 51)).mockResolvedValueOnce(rows(50, 1))
    await open('s-250')

    await useCopilot.getState().loadOlderHistory()
    expect(useCopilot.getState().messages).toHaveLength(250)
    expect(useCopilot.getState().noMoreHistory).toBe(true)

    // 轮询刷新（任务式会话每轮结束都会走这里）
    fetchHistory.mockResolvedValueOnce(rows(200, 51))
    await useCopilot.getState().refreshHistory()

    expect(useCopilot.getState().messages).toHaveLength(200)
    // 原实现只换 messages 不碰 noMoreHistory ⟹ 这里还是 true，那 50 条再也翻不回来
    expect(useCopilot.getState().noMoreHistory).toBe(false)
  })

  it('刷新后不足一页 → 判定到头', async () => {
    fetchHistory.mockResolvedValueOnce(rows(30))
    await open('s-30')
    useCopilot.setState({ noMoreHistory: false }) // 制造「状态错了」的现场

    fetchHistory.mockResolvedValueOnce(rows(30))
    await useCopilot.getState().refreshHistory()

    expect(useCopilot.getState().noMoreHistory).toBe(true)
  })

  it('刷新返回 0 条 → 判定到头（会话消息被清空/删除）', async () => {
    fetchHistory.mockResolvedValueOnce(rows(5))
    await open('s-5')
    useCopilot.setState({ noMoreHistory: false })

    fetchHistory.mockResolvedValueOnce([])
    await useCopilot.getState().refreshHistory()

    expect(useCopilot.getState().noMoreHistory).toBe(true)
  })

  it('刷新失败 → 保持原判定（不知道就别改，否则按钮会随网络抖动闪）', async () => {
    fetchHistory.mockResolvedValueOnce(rows(200))
    await open('s-fail')
    expect(useCopilot.getState().noMoreHistory).toBe(false)

    fetchHistory.mockRejectedValueOnce(new Error('轮询超时'))
    await useCopilot.getState().refreshHistory()

    expect(useCopilot.getState().noMoreHistory).toBe(false)
    expect(useCopilot.getState().lastError).toBeNull()
  })
})

describe('会话边界：翻页状态不跨会话', () => {
  it('A 会话翻到底 → 切到 B 会话，B 不得继承「到头」', async () => {
    fetchHistory.mockResolvedValueOnce(rows(3))
    await open('s-a')
    expect(useCopilot.getState().noMoreHistory).toBe(true)

    // B 自己有 250 条（首屏切出 200 条整页 ⟹ 还有更早的没进来）
    fetchHistory.mockResolvedValueOnce(rows(200, 51))
    await open('s-b')

    // A 的「到底」是 A 的事实。继承过来 B 会直接没有「加载更早」按钮
    expect(useCopilot.getState().noMoreHistory).toBe(false)
    expect(useCopilot.getState().messages).toHaveLength(200)
  })

  it('切会话后历史拉取失败：也不能留着上一个会话的「到头」', async () => {
    fetchHistory.mockResolvedValueOnce(rows(3))
    await open('s-a')
    expect(useCopilot.getState().noMoreHistory).toBe(true)

    fetchHistory.mockRejectedValueOnce(new Error('网络抖动'))
    await open('s-b')

    expect(useCopilot.getState().lastError).toBe('加载会话历史失败')
    expect(useCopilot.getState().noMoreHistory).toBe(false)
  })

  it('切会话的 await 窗口内 noMoreHistory 已经是 false（避免空态闪一下按钮又被收回）', async () => {
    fetchHistory.mockResolvedValueOnce(rows(3))
    await open('s-a')

    let resolveB!: (v: AgentHistoryMessage[]) => void
    fetchHistory.mockReturnValueOnce(
      new Promise<AgentHistoryMessage[]>((r) => {
        resolveB = r
      }),
    )
    const pending = open('s-b')

    // B 的首次历史还在飞：此时没有任何「到头」的依据
    expect(useCopilot.getState().noMoreHistory).toBe(false)

    resolveB(rows(200))
    await pending
    expect(useCopilot.getState().noMoreHistory).toBe(false)
  })
})
