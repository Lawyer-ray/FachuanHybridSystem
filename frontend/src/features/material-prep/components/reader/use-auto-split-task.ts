import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'

import { findInflightPdfSplitJob } from '../../api'
import type { BundleMat } from '../../types'
import { usePollSession } from '@/hooks/use-poll-session'
import { jobSnapshotOf, pollJob, type JobProgressSnapshot } from './auto-split-helpers'

// 本模块对外暴露的 TaskState 里带着 JobProgressSnapshot，转导出一次让消费方
// （含测试）只从一处取类型，不必知道它最初定义在 auto-split-helpers。
export type { JobProgressSnapshot }

/**
 * 「现在有没有一份云端拆分任务在跑、跑到哪了」的会话态 + 打开阅读器时的自动接管。
 *
 * ## 为什么从 `useAutoSplit` 里拆出来
 *
 * 两件事原先挤在同一个 hook 里：**编排**（提交任务 → 轮询 → 回写草稿）与
 * **会话态**（现在跑到哪）。接管是第三种入口——任务不是本页面发起的（刷新、
 * 换设备、同事先点了一次），本页面只需要轮询与展示，**绝不能**回写草稿。拆开后
 * `useAutoSplit` 继续只管编排，这里管「谁在跑、跑到哪」，两个文件都不会超规模红线。
 *
 * ## 为什么用模块级 store 而不是 zustand 的 ReaderState
 *
 * 进度面板读的那份快照与列表/草稿无关，却要在工具条按钮和底部浮条两处同时可见。
 * 放进 `ReaderState` 也不算错，但它会被卷进阅读器 store 的复位语义（换包一律清空），
 * 而这里要表达的是「一个独立的异步任务正在进行」——它有自己的生命周期
 * （begin → 轮询 → 终态），和阅读器的 openId 不同步。一个 20 行的
 * `useSyncExternalStore` 就够了，不必为一份临时状态扩 store 的接口面。
 */

interface TaskState {
  /** 进行中的任务；null = 没有 */
  jobId: string | null
  /** 最近一次轮询拿到的快照；自己刚提交、还没轮询到时为 null（面板显示「正在提交」） */
  snapshot: JobProgressSnapshot | null
  /** 本页面**亲自**发起的任务：只有它允许把结果回写草稿 */
  owned: boolean
  /** 用户点过「不再显示」：任务还在后台跑，只是不再占着屏幕 */
  hidden: boolean
}

const IDLE: TaskState = { jobId: null, snapshot: null, owned: false, hidden: false }

let state: TaskState = IDLE
const listeners = new Set<() => void>()

function setState(patch: Partial<TaskState>) {
  state = { ...state, ...patch }
  for (const notify of listeners) notify()
}

/** `getSnapshot` 必须引用恒定，否则 useSyncExternalStore 每次渲染都会重订阅 */
function readState(): TaskState {
  return state
}

/** 直读模块级会话态：供「卸载后不要再写」这类只能看副作用、看不到渲染的快照断言使用 */
export function readAutoSplitTask(): TaskState {
  return state
}

function subscribe(notify: () => void) {
  listeners.add(notify)
  return () => {
    listeners.delete(notify)
  }
}

/** 轮询进度回报到面板（`useAutoSplit` 中途回报也走这条通道） */
export function reportAutoSplitProgress(snapshot: JobProgressSnapshot) {
  setState({ snapshot })
}

/**
 * 开始一次**本页面发起**的任务（`owned=true`，终态允许回写草稿）。
 *
 * `jobId=null` + `snapshot=null` 表示「已经在提交了，但还不知道任务号」：
 * 提交 164 页 PDF 本身要几十秒，这段时间也得有个面板，不能空着。
 */
export function beginOwnedAutoSplit(snapshot: JobProgressSnapshot | null = null) {
  setState({ jobId: snapshot?.jobId ?? null, snapshot, owned: true, hidden: false })
}

/**
 * 任务收尾：清空会话态（进度面板随之消失），并让平台空闲下来。
 *
 * 置空与 notify **两步都要做，且不能在空态提前 return**：`useSyncExternalStore`
 * 的订阅在任何变更后都会重读快照，靠的是「notify 之后 React 才重渲染」；
 * 而 `state === IDLE` 这种「已经空了」的短路判断在测试环境里会先命中——IDLE 是
 * 共用常量，初次 `setState` 之后拿到的对象未必等于它，短路与否就成了运气问题。
 * 统一走一次赋值 + 一次 notify，行为与调用顺序无关。
 */
export function clearAutoSplitTask() {
  // 换一个新对象：`readState` 靠引用比较，原地改字段不会触发重渲染
  state = IDLE
  for (const notify of listeners) notify()
}

/**
 * 打开阅读器时接管进行中的任务。
 *
 * 为什么要在**打开时**主动查：`running` 以前只活在本页面某个组件的 useState 里，
 * 组件一重挂载就丢，界面回到「什么都不知道」，而云端那个任务还在烧钱（幽灵任务）。
 * 现在任务的存在性与进度都来自后端，页面只负责展示。
 *
 * 几处刻意的取舍：
 * - 只在**没有**在手任务时查（`state.jobId == null`）：别把用户刚点出来的任务抢成
 *   「接管」，否则那次轮询结束时会因为 `owned=false` 而不回写草稿。
 * - 每个阅读器会话只探一次（`probedRef`）：草稿每改一次（改名、拖页）都会换
 *   `mats` 引用，不该因此把后端再问一遍。
 * - 页数未知（`pagesUnknown` / 兜底的 1 页）的 PDF **不查**：拿猜出来的页数去匹配
 *   后端只会查出空集，等于永远接管不到，还白白多打一次请求。
 * - `mounted` 闸门挡 StrictMode 的假卸载：开发态 effect 跑成 setup→cleanup→setup，
 *   若在 cleanup 里做任何不可逆的置位，第二次 setup 就再也不会查了
 *   （`usePollSession` 头注释记过同类事故）。
 */
export function useInflightAutoSplit(mats: BundleMat[], enabled: boolean) {
  const task = useSyncExternalStore(subscribe, readState)
  const pollSession = usePollSession()
  const probedRef = useRef(false)

  useEffect(() => {
    if (!enabled) {
      // 换包 / 关闭阅读器：复位探针，下一个材料包要重新查
      probedRef.current = false
      return
    }
    // 已有任务在手（用户刚点了按钮 / 上一个材料包接管来的）：不探测，也不抢成「接管」。
    // 每次渲染读模块级 state 而不是闭包里的 task：effect 的重跑依赖里没有 task，
    // 读闭包值会拿到挂载那一刻的旧快照，判断就永远是「还没有任务」。
    if (probedRef.current || readState().jobId != null) return
    const pdfs = mats.filter((m) => m.k === 'pdf' && !m.pagesUnknown && (m.pages ?? 0) > 1)
    if (pdfs.length === 0) return

    let mounted = true
    void (async () => {
      for (const mat of pdfs) {
        // 探测失败必须就地吞掉：它只是「看看有没有人在跑」的附加信息，
        // 一个网络抖动不该在阅读器里留下一条未捕获拒绝（CI 会因此整批红）。
        // findInflightPdfSplitJob 内部已有 try/catch，但那是「HTTP 层」的兜底；
        // 这里再包一层是防止任何上层被替身/换实现后漏出 reject。
        const job = await findInflightPdfSplitJob(mat.n, mat.pages).catch(() => null)
        // 探完一轮才置位：否则 StrictMode 的第二次 setup 会在第一次的请求还没回来时
        // 又发一遍（两次请求本身无害，但两次 `begin()` 会让先到的轮询立刻过期）
        if (!mounted || state.jobId != null) return
        if (!job) continue
        probedRef.current = true
        setState({
          jobId: job.job_id,
          owned: false,
          hidden: false,
          snapshot: jobSnapshotOf({ ...job, source_name: mat.n }),
        })
        const lease = pollSession.begin()
        try {
          // tolerateStale：心跳停了只提示、不抛错。接管的是**别人的**任务，
          // 替人按下「放弃」不是本页面该做的决定，交给面板上的律师自己判断。
          await pollJob(
            job.job_id,
            lease,
            (_text, snapshot) => {
              if (lease.isStale()) return
              setState({ snapshot: { ...snapshot, sourceName: mat.n } })
            },
            true,
          )
        } catch {
          // 接管失败（任务已取消 / 已失败 / 真的超时）不做任何事：律师再点一次按钮，
          // 那时走的是「复用已完成结果 / 新建任务」的正常路径。这里既不回写草稿
          // 也不弹错——那不是本次操作的失败。
        } finally {
          if (!lease.isStale() && state.jobId === job.job_id) clearAutoSplitTask()
        }
        return
      }
      if (mounted) probedRef.current = true
    })()

    return () => {
      mounted = false
    }
  }, [enabled, mats, pollSession])

  /**
   * 「不再显示」：只收起界面，**不**取消任务。
   *
   * 一份 164 页卷宗要跑十几分钟、几十块钱，浮条挡着页面时律师点一下的意图是
   * 「别挡我」，不是「把这次识别作废」。真要取消是另一件事，需要二次确认，
   * 而这里的浮条不承担那个动作。
   */
  const hide = useCallback(() => setState({ hidden: true }), [])

  return { task, hide }
}
