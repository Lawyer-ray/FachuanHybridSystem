import { useCallback, useEffect, useMemo, useRef } from 'react'

/**
 * 可中断轮询会话 lease：由 usePollSession().begin() 签发，随轮询循环传递。
 */
export interface PollLease {
  /** 本会话是否已失效（新会话开启 / 手动失效 / 组件卸载）。循环应在每个 await 前后自检 */
  isStale(): boolean
  /**
   * 每循环可中断的 sleep：会话失效时立即 resolve（而非挂满剩余时长），
   * 调用方醒来后经 isStale() 自检退出。
   */
  sleep(ms: number): Promise<void>
}

export interface UsePollSessionResult {
  /** 开启新会话并使旧会话即刻失效（旧循环正在 await 的部分会在下一个自检点退出） */
  begin(): PollLease
  /** 不开新会话、只让当前会话失效（reset 场景：旧循环退出，但不打新任务） */
  invalidate(): void
}

/**
 * 轮询会话 hook：会话号失效 + 每循环可中断 sleep + 卸载自动失效的最小原语。
 *
 * 为什么需要它（三处轮询实现曾共有的缺陷）：
 * 1. 旧实现用 cancelled ref 只在卸载置位——submit() 重入时停不掉「正在 await
 *    网络请求」的旧循环，旧循环继续轮询旧任务 id，把终态写进 state 覆盖新提交。
 *    这里改为会话号守卫：每次 begin()/invalidate() 自增会话号，旧循环在任何
 *    自检点发现自己过期即刻退出。
 * 2. 旧实现共享单个 timer ref，重入时 clearTimeout 停掉的是 sleep promise 背后的
 *    定时器——promise 永不 resolve，await 它的 async 帧永久悬挂（内存泄漏）。
 *    这里每个 sleep 自带定时器并登记到唤醒表；失效时主动 resolve 全部挂着的
 *    sleep，让旧循环「醒过来 → 发现已过期 → 正常 return」干净收尾。
 *
 * 卸载失效为什么是「setup 可复位的标志」而不是「cleanup 里会话号自增」
 * （2026-10-20 记一笔永停「正在上传文书…」事故）：开发态 StrictMode 对新挂载组件
 * 把 effect 跑成 setup→cleanup→setup。cleanup 里直接 session++ 不可逆，挂载 effect
 * 中签发的 lease 会被这次假卸载永久打成 stale；而消费方若用 ref 防重（RecognizeDialog
 * 同一文件不二次提交），第二次 setup 不会再签发新 lease，在飞的上传返回后被 isStale
 * 静默吞掉。unmounted 标志 setup 复位 / cleanup 置位，假卸载可逆、真卸载仍让全部
 * lease 失效。
 *
 * 与 features/home/.../court-sms/use-court-sms.ts 内的 pollSession 是同一范式的
 * 两种实现：那边先修好、绑定了法院短信的具体编排（阶段步进/收件箱失效），
 * 不值得为收敛去改动已验证的代码；本 hook 把同一套「会话号 + 可中断 sleep」
 * 原语抽成与任务 API 无关的通用形态，供 doc-parse / recognize / converter 等
 * 更多消费方复用。
 */
export function usePollSession(): UsePollSessionResult {
  // 会话号单调自增；lease 持有签发时的快照，与最新值不等即视为过期
  const session = useRef(0)
  // 卸载标志：setup 复位、cleanup 置位（见头注释，StrictMode 的假卸载因此可逆）
  const unmounted = useRef(false)
  // 挂着的 sleep 唤醒表（Set：旧会话与新会话的 sleep 可能短暂并存，要全部唤醒）
  const sleepers = useRef(new Set<() => void>())

  const wakeAll = useCallback(() => {
    const pending = sleepers.current
    sleepers.current = new Set()
    for (const wake of pending) wake()
  }, [])

  // 卸载自动失效：置位后所有存活 lease 过期，并唤醒挂着的 sleep。否则被 clearTimeout
  // 语义遗漏的旧循环会带着闭包里的 setState 永久悬挂
  useEffect(() => {
    unmounted.current = false
    return () => {
      unmounted.current = true
      wakeAll()
    }
  }, [wakeAll])

  const begin = useCallback((): PollLease => {
    const mine = ++session.current
    // 唤醒旧会话挂着的 sleep，让它们尽快走完「醒来 → 自检 → 退出」的收尾
    wakeAll()
    const isStale = () => mine !== session.current || unmounted.current
    return {
      isStale,
      sleep: (ms: number) =>
        new Promise<void>((resolve) => {
          // 签发后才失效的会话：别再等了，立即放行（自检会退出）
          if (isStale()) {
            resolve()
            return
          }
          let done = false
          const finish = () => {
            if (done) return
            done = true
            sleepers.current.delete(finish)
            window.clearTimeout(timer)
            resolve()
          }
          const timer = window.setTimeout(finish, ms)
          sleepers.current.add(finish)
        }),
    }
  }, [wakeAll])

  const invalidate = useCallback(() => {
    session.current++
    wakeAll()
  }, [wakeAll])

  // 引用稳定：消费方把它放进 useCallback 依赖（submit 等），对象每渲染重建会让
  // 依赖它的回调跟着漂移，进而让以回调为依赖的 effect 每次渲染重跑
  return useMemo(() => ({ begin, invalidate }), [begin, invalidate])
}
