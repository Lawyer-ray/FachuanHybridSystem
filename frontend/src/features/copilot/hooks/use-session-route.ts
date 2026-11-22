/**
 * 会话 ↔ URL 双向同步：`/assistant/:sessionId` 里的 id 就是当前会话。
 *
 * **只在页面宿主（AssistantPage）里调用，抽屉不调用**：抽屉是业务页上的浮层，
 * 没有自己的 URL；两边共用同一个 store，所以页面切到的会话回抽屉还是同一段对话。
 *
 * 为什么要有它：会话原本只活在 store 里（初值读 localStorage），URL 只有光秃秃一条
 * `/assistant` —— 律师没法说「是这个会话要改」，链接也没法贴给别人。现在 URL 是
 * 会话的唯一真相：可复制、可刷新、可贴给别人、可后退前进。
 *
 * 三条硬约束，漏一条就是真故障：
 * 1. **一律 `replace: true`**：切会话不是导航，不该把后退栈塞满（连续点五条会话后
 *    按一次后退，该回到进助手之前那一页，而不是倒着回放刚才点过的会话）。
 * 2. **两侧都先比再写**（循环防护）：写 URL 前比 `pathname`，写 store 前比
 *    `sessionId`。少一边就是 store→URL→store→… 的乒乓。
 * 3. **首帧不能清空 store**：`/assistant` 上 paramId 为空不等于「用户开了新对话」，
 *    见下面 ① 的 seed。
 */

import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLocation, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { assistantSession, ROUTES } from '@/app/paths'

import { sessionsQueryOptions } from '../session-queries'
import { useCopilot } from '../store'

export function useSessionRoute(): void {
  const { sessionId: paramId } = useParams()
  /** URL 里的会话 id；null = 当前落在 `/assistant`（无会话 / 新对话） */
  const urlSessionId = paramId ?? null
  const sessionId = useCopilot((s) => s.sessionId) ?? null
  /** 只看「历史拉取失败」：`lastError` 也会被发消息失败、限流等写入，不能当坏 id 的证据 */
  const historyLoadError = useCopilot((s) => s.historyLoadError) ?? false
  const switchSession = useCopilot((s) => s.switchSession)
  const navigate = useNavigate()
  const { pathname } = useLocation()

  /**
   * 上一轮同步时两侧各自的取值（外加「首帧是否已 seed」）。
   *
   * 只回答一个问题：**这一轮是谁变了**。同值重跑 = 谁都没变 = 什么也不做——于是
   * StrictMode 的双重挂载、以及「写完 URL 后 store 也跟着变一次」的连带 render
   * 都天然幂等，不需要另外去重。
   */
  const syncRef = useRef({ seeded: false, url: urlSessionId, store: sessionId })
  /**
   * 当前会话 id 是不是**页面打开时就有的那个**（URL 带来的，或 localStorage 恢复的）。
   *
   * 只有这类 id 可能是「不存在或已删」的坏 id：用户从侧栏点出来的、或刚发第一条
   * 消息建出来的会话一定存在。判定与重置见 ②。
   */
  const openingIdRef = useRef<string | null>(null)

  // 会话列表：key / 页大小 / 取数跟 SessionSidebar 同源（见 session-queries）——同一个
  // key 在 react-query 里只有一次在飞请求，所以页面同时开着会话栏时这里不会多打一次
  // 接口；判「id 不在列表」的窗口也与用户能翻到的列表是同一个（只装 50 条时 51–100 名
  // 的合法老会话会被误判成坏 id）。
  // 只取「列出来了没」与「列了哪些」两个值：useQuery 返回的 result 对象每轮都是新的，
  // 直接把它放进依赖会让 effect 每轮都跑（幂等但白干）。
  const { isSuccess: sessionsLoaded, data: listedSessions } = useQuery(sessionsQueryOptions('all'))

  useEffect(() => {
    const prev = syncRef.current
    syncRef.current = { seeded: true, url: urlSessionId, store: sessionId }

    // ① 首帧 seed：只在这里定一次「谁说了算」，之后两个方向才算真正的同步。
    //    · URL 有 id（`/assistant/<id>`：别人贴过来的链接 / 刷新）：**信 URL**，把会话
    //      切过去。反过来信 store 会把链接悄悄换成自己上次那个会话。
    //    · URL 没有 id（`/assistant`）：**信 store**（它的 sessionId 是 localStorage
    //      恢复的上次会话）并把 id 写回 URL。这里绝不能反过来把 store 清成新对话——
    //      那正好砍掉「刷新回到上次会话」这条既有行为。
    if (!prev.seeded) {
      openingIdRef.current = urlSessionId ?? sessionId
      if (urlSessionId === null) {
        if (sessionId) void navigate(assistantSession(sessionId), { replace: true })
        return
      }
      if (sessionId !== urlSessionId) void switchSession(urlSessionId)
      return
    }

    // ② 坏 id 兜底：`/assistant/<不存在或已删>`。switchSession 拉历史失败时只设
    //    错误状态、sessionId 仍停在那个坏 id，页面上就是一个永远空着的对话 + 一句
    //    「加载会话历史失败」，而 URL 看着完全正常。三条同时成立才算数：
    //    · 这个 id 是打开页面时就有的（见 openingIdRef，发消息建出来的不算）；
    //    · 历史确实拉失败了（historyLoadError）——**只有**这种情况才需要把用户放回
    //      新对话。不能看 lastError：发消息失败 / 限流也写它，老会话（不在最近 N 条
    //      列表里）发一次消息失败就会被误判成「会话不存在」；
    //    · 列表在 id 就位之后加载完，仍查无此 id。
    //    只凭「不在列表」就重置会误伤两种**合法**的缺席：刚建出来的会话（列表要等
    //    本轮流结束才刷新）、以及不在最新 N 条里的老会话——后者恰恰是「把链接贴给
    //    别人」最想打开的那种。
    //    重置只做一半（URL 改回 /assistant），store 由 ③ 跟着 URL 一起清：一条路径
    //    只写一个真相，少一处能忘的同步。
    if (
      sessionId !== null &&
      sessionId === openingIdRef.current &&
      historyLoadError &&
      sessionsLoaded &&
      !listedSessions?.some((s) => s.session_id === sessionId)
    ) {
      openingIdRef.current = null
      toast.error('这个会话不存在或已被删除，已回到新对话')
      void navigate(ROUTES.assistant, { replace: true })
      return
    }

    // ③ URL 变了（浏览器后退/前进、地址栏直接改）→ 会话跟随 URL
    if (urlSessionId !== prev.url) {
      if (sessionId !== urlSessionId) void switchSession(urlSessionId)
      return
    }

    // ④ store 变了（侧栏点另一条 / 新对话 / 删完邻居接管 / 发消息建出新会话）→ URL 跟随
    if (sessionId !== prev.store) {
      // id 已不是「打开页面时那一个」（用户自己切的、或发消息建出来的）：坏 id 判据
      // 不再适用于它
      if (sessionId !== urlSessionId) openingIdRef.current = null
      const target = sessionId ? assistantSession(sessionId) : ROUTES.assistant
      // 循环防护：路径已经对了就不写——写 URL 会触发 render，那条 render 里
      // sessionId 恒等于新值，少了这个比较就是 ④→render→③→… 的乒乓
      if (pathname !== target) void navigate(target, { replace: true })
    }
  }, [urlSessionId, sessionId, historyLoadError, sessionsLoaded, listedSessions, pathname, navigate, switchSession])
}
