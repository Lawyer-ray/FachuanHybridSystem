/**
 * 界面动作（`ui_action`）执行层的**开发专用**探针页：`/_dev/ui-action`。
 *
 * ## 为什么必须有这一页
 *
 * 执行层的关键结论只在真浏览器里成立：`ui_navigate` 到底有没有改地址栏、
 * `ui_copilot_open` 到底有没有派发启动事件、被白名单拒掉的动作是不是**真的**没动地址。
 * jsdom 能证明 store 里写了 ok / error，却证明不了浏览器照做了——而这段差异正好是
 * Safari / Firefox 手测要找的东西。真机手测又不该先跑一遍登录：本页只调用执行器、
 * 不发任何 API 请求，所以挂在一个**免登录**的独立路径上，任何浏览器打开即用。
 *
 * ## 怎么用
 *
 * 点按钮 → 对照下方三行实测输出：
 * - `probe-loc`：`location.pathname + search`（地址有没有真的变）
 * - `probe-run`：最近一次运行记录的 state / code（执行层判成 ok 还是哪一类失败）
 * - `probe-launch`：最近一次 `copilot:launch` 事件的 payload（`ui_copilot_open` 的真实效果）
 *
 * 每次点击都走**真实链路** `useCopilot.getState().runUiAction({ callId, action, args, route })`
 * ——与 SSE 帧到达时 `handlers/ui-action-handler.ts` 做的事完全一致；**不**直接调
 * `navigate`，否则测的是 router 而不是执行层。
 *
 * 注意：允许类动作跳的 `/projects`、`/material-prep` 在未登录时会被 `RequireAuth`
 * 前转到 `/login`（本页自己免登录，目标页不免）。这不是失败——判定看 `probe-run`
 * 是不是 `ok`、地址是不是离开了 `/_dev/ui-action`；跳走后再回到本路径，运行记录仍在
 * store 里（不随页面卸载丢失）。
 *
 * ## 为什么不会进 prod 包
 *
 * 挂载点 `src/app/router.tsx` 用 `import.meta.env.DEV ? lazy(() => import(...)) : null`
 * 引用本文件：Vite 在构建期把 `import.meta.env.DEV` 替换为 `false`，整个分支连同这里的
 * 动态 import 一起被摇掉。验证：`pnpm build && grep -rl "probe-loc" dist/` 必须无输出。
 */

import { useEffect, useState } from 'react'
import { useLocation } from 'react-router'

import { UiActionBanner } from '../components/UiActionBanner'
import { UiToolHost } from '../components/UiToolHost'
import { COPILOT_LAUNCH_EVENT } from '../launch'
import type { CopilotLaunchContext } from '../launch'
import type { UiToolRun } from '../state-types'
import { useCopilot } from '../store'

interface ProbeCase {
  /** 稳定 id：按钮 key 与 `data-testid`（手测/自动化都靠它定位） */
  id: string
  /** 按钮文案 */
  label: string
  /** 期望结果：手测时逐字对照 probe-run / probe-loc 的实测值 */
  expected: string
  action: string
  args: Record<string, unknown>
  /** 后端清单声明的期望路由前缀（`ui-tools/generated.ts` 的 `spec.route`）；忠实照抄真实帧 */
  route: string | null
}

const PROBE_CASES: readonly ProbeCase[] = [
  {
    id: 'navigate-projects',
    label: '① 跳转 /projects',
    expected: 'probe-run = ok，probe-loc 变成 /projects',
    action: 'ui_navigate',
    args: { path: '/projects' },
    route: null,
  },
  {
    id: 'material-prep-todo',
    label: '② 材料预处理切「待处理」',
    expected: 'probe-run = ok，probe-loc 变成 /material-prep?stage=todo',
    action: 'ui_material_prep_set_stage',
    args: { stage: 'todo' },
    route: '/material-prep',
  },
  {
    id: 'copilot-open-context',
    label: '③ 打开助手（带案件上下文）',
    expected: 'probe-run = ok，probe-launch 出现 case / 42 / 探针案件',
    action: 'ui_copilot_open',
    args: { origin: 'case', refId: 42, title: '探针案件' },
    route: null,
  },
  {
    id: 'reject-javascript-url',
    label: '④ 必须被拒：javascript: 伪协议',
    expected: 'probe-run = error / route_unreachable，probe-loc 不变',
    action: 'ui_navigate',
    args: { path: 'javascript:alert(1)' },
    route: null,
  },
  {
    id: 'reject-client-upload',
    label: '⑤ 必须被拒：客户上传链接 /u/abc',
    expected: 'probe-run = error / route_unreachable（链接即凭证，白名单排除），probe-loc 不变',
    action: 'ui_navigate',
    args: { path: '/u/abc' },
    route: null,
  },
]

/**
 * 每次点击都要一个新的 callId：store 的幂等表按 callId 去重（`seenCallIds`），
 * 复用同一个 id 时第二次点会被静默丢掉，探针就永远测不出第二条。
 *
 * `crypto.randomUUID` 虽在基线内（Safari 15.4+），却是 **secure context 限定**：
 * 真机 Safari 用局域网 `http://192.168.x.x:5090` 打开本页时它不存在，故留一条手拼回退。
 */
function newCallId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `probe-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** 最近一条运行记录（与 `UiActionBanner` 同口径：按 startedAt 取最大） */
function latestRun(runs: Record<string, UiToolRun>): UiToolRun | null {
  let latest: UiToolRun | null = null
  for (const run of Object.values(runs)) {
    if (latest === null || run.startedAt >= latest.startedAt) latest = run
  }
  return latest
}

/**
 * 三行实测输出的**跨导航持久化**。
 *
 * 为什么需要：允许类动作会把地址带离本页（未登录时被 `RequireAuth` 前转到 `/login`），
 * 而 `probe-run` 存在 copilot store 里——SPA 内前进后退还在，**整页刷新就没了**。
 * 手测的人若用地址栏回到本页（最自然的动作），会看到「尚未执行」，误以为动作没跑。
 *
 * 存 `sessionStorage` 而不是 `localStorage`：只活在这个标签页，关掉即清，
 * 不会把上次手测的结论带到下一次会话里骗人。
 */
const PROBE_STORE_KEY = 'fachuan:ui-action-probe'

interface ProbePersisted {
  run: string
  launch: string
  errors: string
}

const NO_ERRORS = '（无）'

function readPersisted(): ProbePersisted {
  const empty: ProbePersisted = { run: '（尚未执行）', launch: '（尚未收到 copilot:launch）', errors: NO_ERRORS }
  try {
    const raw = sessionStorage.getItem(PROBE_STORE_KEY)
    if (!raw) return empty
    const parsed = JSON.parse(raw) as Partial<ProbePersisted>
    return {
      run: parsed.run || empty.run,
      launch: parsed.launch || empty.launch,
      errors: parsed.errors || empty.errors,
    }
  } catch {
    return empty
  }
}

/** 一次运行记录的可读形态（state 必显，code 只在失败时有） */
function describeRun(run: UiToolRun | null): string {
  if (run === null) return '（尚未执行）'
  return `${run.name} → ${run.state}${run.code ? ` / ${run.code}` : ''}`
}

export default function UiActionProbe() {
  const location = useLocation()
  const runs = useCopilot((s) => s.uiToolRuns)
  // 首帧从 sessionStorage 恢复：地址栏回到本页时仍能看到上一次的结论（理由见 PROBE_STORE_KEY）。
  // 用 useState 的惰性初始化而不是 useRef：渲染期读 ref 会被 react-hooks/refs 拦
  // （而它拦得对——ref 变化不会触发重渲染，恢复值只该算一次）。
  const [restored] = useState<ProbePersisted>(() => readPersisted())
  const [lastLaunch, setLastLaunch] = useState(restored.launch)
  /**
   * 未捕获异常/拒绝的自捕获：手测第 8 步要求「控制台无红色报错」，但 Web Inspector
   * 的 AX 树在自动化里读不到（它是独立 webview）。把错误顺手抄到页面上，
   * 第 8 步就变成**可机读**的一行，而不是靠人肉看控制台。
   * 只捕获本页生命周期内冒到 window 的错误——够用，且不改变产品代码行为。
   */
  const [caughtErrors, setCaughtErrors] = useState(restored.errors)

  // `ui_copilot_open` 的真实效果是派发启动事件（`launch.ts` 的既定模式）。本页不在
  // AppShell 里、没有面板订阅它，所以自己接一下把 payload 显示出来——否则「打开了助手」
  // 在探针上完全不可见，等于这一条动作没被验过。
  useEffect(() => {
    const onLaunch = (event: Event): void => {
      const detail = (event as CustomEvent<CopilotLaunchContext | null>).detail
      setLastLaunch(detail ? `${detail.origin} / ${detail.refId} / ${detail.title}` : '（普通打开，无上下文）')
    }
    window.addEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
    return () => window.removeEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
  }, [])

  const runText = describeRun(latestRun(runs))
  // 展示值 = 本次内存里的结论优先；没有（整页刷新后还没点）才退回持久化的那次
  const shownRun = latestRun(runs) === null ? restored.run : runText
  const shownLaunch = lastLaunch === '（尚未收到 copilot:launch）' ? restored.launch : lastLaunch

  // 每次结论变化都落一次 sessionStorage：页面被导航带走的瞬间也已经是新值
  useEffect(() => {
    try {
      sessionStorage.setItem(PROBE_STORE_KEY, JSON.stringify({ run: shownRun, launch: shownLaunch, errors: caughtErrors }))
    } catch {
      // 隐私窗口 / 禁用存储：持久化只是便利，失败不影响本次手测
    }
  }, [shownRun, shownLaunch, caughtErrors])

  useEffect(() => {
    const onError = (event: ErrorEvent): void => {
      setCaughtErrors(`window.onerror: ${event.message}`)
    }
    const onRejection = (event: PromiseRejectionEvent): void => {
      const reason = event.reason as { message?: string } | undefined
      setCaughtErrors(`unhandledrejection: ${reason?.message ?? String(event.reason)}`)
    }
    window.addEventListener('error', onError)
    window.addEventListener('unhandledrejection', onRejection)
    return () => {
      window.removeEventListener('error', onError)
      window.removeEventListener('unhandledrejection', onRejection)
    }
  }, [])

  const fire = (item: ProbeCase): void => {
    const store = useCopilot.getState()
    // 「停下」标记只在新一轮开流时清（`handlers/ui-action-handler.ts`）。探针没有流，
    // 点过一次横幅上的「停下」之后所有动作都会被静默跳过；按同一语义在这里清一次，
    // 否则手测的人会以为执行层坏了。
    if (store.abortedAt !== null) useCopilot.setState({ abortedAt: null })
    void store.runUiAction({ callId: newCallId(), action: item.action, args: item.args, route: item.route })
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-6 text-foreground">
      <header className="flex flex-col gap-1">
        <h1 className="text-[15px] font-semibold">界面动作探针（仅 dev 构建存在）</h1>
        <p className="text-[12px] leading-5 text-muted-foreground">
          点按钮看下面三行实测输出。允许类动作在未登录时会被 RequireAuth 前转到 /login，这不算失败：
          判定看 probe-run 是不是 ok、地址有没有离开本页。
        </p>
      </header>

      {/* 真实的两个宿主组件：UiToolHost 注入 navigate / toast / openCopilot 端口（本页在 Router
          下，useNavigate 可用），UiActionBanner 把执行态显示出来。换成假的就测不到这两层。 */}
      <UiToolHost />
      <UiActionBanner />

      <section className="flex flex-col gap-2">
        {PROBE_CASES.map((item) => (
          <div key={item.id} className="flex flex-col gap-1 rounded-[9px] border border-border p-2.5">
            <button
              type="button"
              data-testid={`probe-case-${item.id}`}
              onClick={() => fire(item)}
              className="self-start rounded-[6px] border border-border bg-card px-2.5 py-1 text-[12.5px] transition-colors hover:bg-secondary hover:text-foreground"
            >
              {item.label}
            </button>
            <span className="text-[11.5px] text-muted-foreground">期望：{item.expected}</span>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-1 rounded-[9px] border border-border bg-card p-2.5 font-mono text-[12px]">
        <div data-testid="probe-loc">probe-loc：{location.pathname + location.search}</div>
        <div data-testid="probe-run">probe-run：{shownRun}</div>
        <div data-testid="probe-launch">probe-launch：{shownLaunch}</div>
        <div data-testid="probe-errors" className={caughtErrors === NO_ERRORS ? '' : 'text-red-600 dark:text-red-400'}>
          probe-errors：{caughtErrors}
        </div>
      </section>
    </div>
  )
}
