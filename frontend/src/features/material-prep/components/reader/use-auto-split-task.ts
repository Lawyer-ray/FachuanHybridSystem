import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import { toast } from 'sonner'

import { cancelPdfSplitJob, findInflightPdfSplitJob } from '../../api'
import { useReader } from '../../store'
import type { BundleMat } from '../../types'
import { errMessage } from '@/lib/errors'
import { usePollSession } from '@/hooks/use-poll-session'
import { jobSnapshotOf, pollJob, type JobProgressSnapshot } from './auto-split-helpers'

// 本模块对外暴露的 TaskState 里带着 JobProgressSnapshot，转导出一次让消费方
// （含测试）只从一处取类型，不必知道它最初定义在 auto-split-helpers。
export type { JobProgressSnapshot }

/**
 * 「现在有没有一份云端拆分任务在跑、跑到哪了」的会话态 + 打开阅读器时的自动接管
 * + **彻底停止**。
 *
 * ## 为什么从 `useAutoSplit` 里拆出来
 *
 * 两件事原先挤在同一个 hook 里：**编排**（提交任务 → 轮询 → 回写草稿）与
 * **会话态**（现在跑到哪）。接管是第三种入口——任务不是本页面发起的（刷新、
 * 换设备、同事先点了一次），本页面只需要轮询与展示，**绝不能**回写草稿。拆开后
 * `useAutoSplit` 继续只管编排，这里管「谁在跑、跑到哪」。
 *
 * ## 为什么用模块级 store 而不是 zustand 的 ReaderState
 *
 * 进度面板读的那份快照与列表/草稿无关，却要在工具条按钮和底部浮条两处同时可见。
 * 它有自己的生命周期（begin → 轮询 → 终态），与阅读器的 openId 不同步，
 * 所以不放 `ReaderState`（那会被卷进「换包一律清空」的复位语义）。
 *
 * ## ⚠️ 但**必须按材料包归属**（2026-11-26 实测缺陷）
 *
 * 上面那句「与 openId 不同步」被写成了「完全不管 openId」，于是：律师在材料包 A
 * 上发起识别，再打开材料包 B → B 的底部浮条上显示着 A 那份任务的
 * 「正在识别文字（0/37 页）」。两条路都会漏：
 *
 *  · 会话态是模块级的，换包时既没清空、也不看包号；
 *  · `useInflightAutoSplit` 的「已有在手任务就不探测」把**别的包**的任务当成了在手任务。
 *
 * 现在每个任务都记着 `packId`（材料包主键），三处一起收敛：回报时对不上包就丢弃、
 * 钩子只把本包的任务交给界面、换包时先把上一个包的状态清掉。
 * 教训写进坑库了：`docs/harness/pitfalls.md` PIT-028（异步任务的界面状态必须带归属容器）。
 */

interface TaskState {
  /**
   * 这份任务属于哪个材料包（`InboxMessage` 主键）。
   *
   * 它是「这份进度该不该显示在眼前这个包上」的唯一判据。`null` = 没有任务。
   */
  packId: number | null
  /** 进行中的任务；null = 没有 */
  jobId: string | null
  /** 最近一次轮询拿到的快照；自己刚提交、还没轮询到时为 null（面板显示「正在提交」） */
  snapshot: JobProgressSnapshot | null
  /** 本页面**亲自**发起的任务：只有它允许把结果回写草稿 */
  owned: boolean
  /** 用户点过「不再显示」：任务还在后台跑，只是不再占着屏幕 */
  hidden: boolean
}

const IDLE: TaskState = { packId: null, jobId: null, snapshot: null, owned: false, hidden: false }

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

/**
 * 轮询进度回报到面板（`useAutoSplit` 中途回报也走这条通道）。
 *
 * **包号对不上就整条丢弃**：这是「切包之后迟到的快照不许再亮起来」的最后一道闸。
 * 轮询循环自己也会在 lease 失效时停手，但那个检查发生在调用方，而这里是所有
 * 快照的唯一入口——放这里一条，任何漏掉的调用方都不会把进度写到错包上。
 */
export function reportAutoSplitProgress(packId: number, snapshot: JobProgressSnapshot) {
  if (state.packId !== packId) return
  setState({ snapshot })
}

/**
 * 开始一次**本页面发起**的任务（`owned=true`，终态允许回写草稿）。
 *
 * `jobId=null` + `snapshot=null` 表示「已经在提交了，但还不知道任务号」：
 * 提交 164 页 PDF 本身要几十秒，这段时间也得有个面板，不能空着。
 */
export function beginOwnedAutoSplit(packId: number, snapshot: JobProgressSnapshot | null = null) {
  setState({ packId, jobId: snapshot?.jobId ?? null, snapshot, owned: true, hidden: false })
}

/**
 * 任务收尾：清空会话态（进度面板随之消失），并让平台空闲下来。
 *
 * 传 `packId` 时**只清自己那一份**：A 包的轮询收尾时若把 B 包刚发起的任务一起清掉，
 * B 的面板会凭空消失、B 的回写也跟着断了。
 *
 * 置空与 notify **两步都要做，且不能在空态提前 return**：`useSyncExternalStore`
 * 的订阅在任何变更后都会重读快照，靠的是「notify 之后 React 才重渲染」；
 * 而 `state === IDLE` 这种「已经空了」的短路判断在测试环境里会先命中——IDLE 是
 * 共用常量，初次 `setState` 之后拿到的对象未必等于它，短路与否就成了运气问题。
 * 统一走一次赋值 + 一次 notify，行为与调用顺序无关。
 */
export function clearAutoSplitTask(packId?: number) {
  if (packId != null && state.packId !== packId) return
  // 换一个新对象：`readState` 靠引用比较，原地改字段不会触发重渲染
  state = IDLE
  for (const notify of listeners) notify()
}

/**
 * 本地轮询循环的「就地停机」回调。
 *
 * 为什么需要注册而不是让面板直接闭包持有：停机要动的两样东西（`usePollSession`
 * 签发的 lease、`useAutoSplit` 的 `running` 状态）都活在**发起轮询的那个 hook**里，
 * 而按钮渲染在另一个组件（底部浮条）。注册表是两边唯一的共同点。
 *
 * 用 token 而非 packId 作身份：同一个包上重入两次时，先结束的那次不能把后开始的
 * 那次注册的停机回调删掉（否则第二次就再也停不下来）。
 */
let stopper: { token: symbol; packId: number; stop: () => void } | null = null

/** 注册停机回调，返回用于注销的 token（调用方在 `finally` 里带着它注销） */
export function registerAutoSplitStopper(packId: number, stop: () => void): symbol {
  const token = Symbol('auto-split-stopper')
  stopper = { token, packId, stop }
  return token
}

/** 注销停机回调；token 对不上（已被后来者覆盖）时什么都不做 */
export function releaseAutoSplitStopper(token: symbol) {
  if (stopper?.token === token) stopper = null
}

/**
 * 律师已经按下「停止识别」的包。
 *
 * 只解决一个体验问题：取消有往返时延，轮询循环会先看到 `status=cancelled` 并抛错，
 * 而那明明是**用户自己要的**结果——弹一条红色「识别失败」等于把一次正确的操作
 * 报成故障。编排层（`useAutoSplit`）的 catch 靠它区分「取消」与「真失败」。
 */
let stoppingPack: number | null = null

/** 这个包是否正在被用户主动停止（→ 轮询抛出的「已取消」不该当失败报） */
export function isAutoSplitStopping(packId: number): boolean {
  return stoppingPack === packId
}

/**
 * **彻底停止**这次识别：停掉本页面的轮询 + 让服务端取消任务。
 *
 * 顺序是**先打后端、成功后才动本地**，理由：
 *  · 后端取消失败时任务还在烧钱，这时把浮条藏掉等于向用户谎报「停了」——
 *    浮条留着、进度继续走，用户看得见、还能再按一次；
 *  · 取消失败也不停本地轮询：正因为任务还在跑，进度才必须继续是活的。
 *
 * 幂等：包已经换了、或本来就没有任务，直接当成功（没什么可停的）。
 */
export async function stopAutoSplitTask(packId: number): Promise<{ ok: boolean; message: string }> {
  const current = state
  if (current.packId !== packId || !current.jobId) {
    // 还没有任务号 = 还在提交那几十秒里：停本地即可，服务端没有可取消的对象
    localStop(packId)
    clearAutoSplitTask(packId)
    return { ok: true, message: '已停止本次识别' }
  }

  stoppingPack = packId
  try {
    await cancelPdfSplitJob(current.jobId)
  } catch (error) {
    // 没停成：一切都保持原样（循环还在跑、浮条还在），用户可以再按一次
    stoppingPack = null
    return { ok: false, message: errMessage(error, '取消云端任务失败') }
  }
  localStop(packId)
  clearAutoSplitTask(packId)
  stoppingPack = null
  return { ok: true, message: '已停止本次识别，云端任务已取消' }
}

/**
 * 底部浮条「停止识别」的入口：**自己**从会话态读包号，停完把结果说出来。
 *
 * 为什么不层层传 prop：浮条要的只是「停掉这个包的任务」，而包号本来就
 * 记在会话态里；传 prop 要穿过 ReaderBody → ReaderOverlays → AutoSplitProgress 三层，
 * 每层都多一个只用于转发的参数。组件答不上来的事实（哪个包、怎么停）不该变成 prop。
 */
export async function stopCurrentAutoSplitTask(): Promise<void> {
  const packId = state.packId
  if (packId == null) return
  const result = await stopAutoSplitTask(packId)
  if (result.ok) toast.success(result.message)
  else toast.error(`停止识别失败：${result.message}（任务仍在云端运行，可再试一次）`)
}

/** 让本页面正在跑的轮询循环在下一个自检点退出（没有注册过就什么都不做） */
function localStop(packId: number) {
  if (stopper?.packId !== packId) return
  const { stop } = stopper
  stopper = null
  stop()
}

/**
 * 打开阅读器时接管进行中的任务。
 *
 * 为什么要在**打开时**主动查：`running` 以前只活在本页面某个组件的 useState 里，
 * 组件一重挂载就丢，界面回到「什么都不知道」，而云端那个任务还在烧钱（幽灵任务）。
 * 现在任务的存在性与进度都来自后端，页面只负责展示。
 *
 * 包号（`openId`）从阅读器 store 直接读，而不是让调用方再传一遍：它和「现在打开的是
 * 哪个材料包」是同一个事实，多一层传参就多一种传错的姿势（传错就是又一个
 * 「别人的进度条」）。
 *
 * 几处刻意的取舍：
 * - 只接管**当前这个材料包**的任务（`packId` 一起发给后端）：同名同页数不唯一，
 *   靠它们匹配会把别的包的任务认成这个包的。
 * - 只在本包**没有**在手任务时查（`packId` 与状态一致且已有任务）：别把用户刚点
 *   出来的任务抢成「接管」，否则那次轮询结束时会因为 `owned=false` 而不回写草稿。
 * - 每个材料包只探一次（`probedPackRef` 记包号而不是布尔）：草稿每改一次（改名、
 *   拖页）都会换 `mats` 引用，不该因此把后端再问一遍；换包则必须重探。
 * - 页数未知（`pagesUnknown` / 兜底的 1 页）的 PDF **不查**：拿猜出来的页数去匹配
 *   后端只会查出空集，等于永远接管不到，还白白多打一次请求。
 * - `mounted` 闸门挡 StrictMode 的假卸载：开发态 effect 跑成 setup→cleanup→setup，
 *   若在 cleanup 里做任何不可逆的置位，第二次 setup 就再也不会查了
 *   （`usePollSession` 头注释记过同类事故）。
 */
export function useInflightAutoSplit(mats: BundleMat[], enabled: boolean) {
  const task = useSyncExternalStore(subscribe, readState)
  const packId = useReader((s) => s.openId)
  const pollSession = usePollSession()
  const probedPackRef = useRef<number | null>(null)

  useEffect(() => {
    if (!enabled || packId == null) {
      // 关闭阅读器：复位探针，下一个材料包要重新查
      probedPackRef.current = null
      return
    }
    // 换包：上一个包的任务不属于眼前这个包，立刻撤掉（浮条随之消失），并允许重探。
    // 不清掉的话，下面「本包已有任务就不探测」会把别的包的任务当成在手任务，
    // 结果是这个包永远探测不到自己的任务、却一直显示别人的进度。
    if (readState().packId !== packId && readState().packId != null) clearAutoSplitTask()
    if (probedPackRef.current === packId) return
    const mine = readState()
    if (mine.packId === packId && (mine.jobId != null || mine.owned)) return

    const pdfs = mats.filter((m) => m.k === 'pdf' && !m.pagesUnknown && (m.pages ?? 0) > 1)
    if (pdfs.length === 0) return

    let mounted = true
    void (async () => {
      for (const mat of pdfs) {
        // 探测失败必须就地吞掉：它只是「看看有没有人在跑」的附加信息，
        // 一个网络抖动不该在阅读器里留下一条未捕获拒绝（CI 会因此整批红）。
        // findInflightPdfSplitJob 内部已有 try/catch，但那是「HTTP 层」的兜底；
        // 这里再包一层是防止任何上层被替身/换实现后漏出 reject。
        const job = await findInflightPdfSplitJob({
          packMessageId: packId,
          sourceName: mat.n,
          totalPages: mat.pages,
        }).catch(() => null)
        // 探完一轮才置位：否则 StrictMode 的第二次 setup 会在第一次的请求还没回来时
        // 又发一遍（两次请求本身无害，但两次 `begin()` 会让先到的轮询立刻过期）。
        // 中途本包已经有人接手（用户点了按钮 / 另一个探测先到）就不夺：「本包」这个前提
        // 不能省——别的包的会话态（待清理）不得把本包的接管拦掉。
        const current = readState()
        if (!mounted || (current.packId === packId && current.jobId != null)) return
        if (!job) continue
        probedPackRef.current = packId
        setState({
          packId,
          jobId: job.job_id,
          owned: false,
          hidden: false,
          snapshot: jobSnapshotOf({ ...job, source_name: mat.n }),
        })
        const lease = pollSession.begin()
        const token = registerAutoSplitStopper(packId, () => pollSession.invalidate())
        try {
          // tolerateStale：心跳停了只提示、不抛错。接管的是**别人的**任务，
          // 替人按下「放弃」不是本页面该做的决定，交给面板上的律师自己判断。
          await pollJob(
            job.job_id,
            lease,
            (_text, snapshot) => {
              // 包号与任务号都要对得上：律师可能在本页面又点了一次「自动识别」，
              // 那一刻在手任务已经换成新任务，这个接管循环的旧快照不能再往上写
              // （否则面板一会儿显示旧任务、一会儿显示新任务）
              const latest = readState()
              if (lease.isStale() || latest.packId !== packId || latest.jobId !== job.job_id) return
              setState({ snapshot: { ...snapshot, sourceName: mat.n } })
            },
            true,
          )
        } catch {
          // 接管失败（任务已取消 / 已失败 / 真的超时）不做任何事：律师再点一次按钮，
          // 那时走的是「复用已完成结果 / 新建任务」的正常路径。这里既不回写草稿
          // 也不弹错——那不是本次操作的失败。
        } finally {
          releaseAutoSplitStopper(token)
          if (!lease.isStale() && state.packId === packId && state.jobId === job.job_id) clearAutoSplitTask(packId)
        }
        return
      }
      if (mounted) probedPackRef.current = packId
    })()

    return () => {
      mounted = false
    }
  }, [enabled, mats, packId, pollSession])

  /**
   * 「不再显示」：只收起界面，**不**取消任务。
   *
   * 一份 164 页卷宗要跑十几分钟、几十块钱，浮条挡着页面时律师点一下的意图是
   * 「别挡我」，不是「把这次识别作废」。真要取消是「停止识别」那个按钮的事
   * （`stopCurrentAutoSplitTask`），它打后端取消接口并二次确认。
   */
  const hide = useCallback(() => setState({ hidden: true }), [])

  // 只把**本包**的任务交出去：别的包的进度条绝不能出现在这个页面上。
  // 这一层判定在渲染期完成（不依赖 effect 的执行时机），所以换包的第一帧也不会闪。
  const scoped = task.packId === packId && packId != null ? task : IDLE

  return { task: scoped, hide }
}
