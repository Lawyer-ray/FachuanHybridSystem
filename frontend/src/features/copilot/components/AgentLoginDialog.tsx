/**
 * 后端登录弹窗：「选择 AI」菜单里某一行的 `action=login` 点开的那个框。
 *
 * ## 为什么登录必须进前端
 *
 * qoder 的凭据来自 `qodercli login` 的**浏览器设备授权**（打印一个
 * `https://qoder.com/device/...` 链接，等人确认）。用户全是律师，没有服务器 shell，
 * 「去机器上跑一条命令」对他们是一句废话。所以整条链路搬到界面上：
 *
 * 点「登录 Qoder」→ 后端起 CLI → 这里把授权链接渲染成按钮 → 每 2 秒问一次结果 →
 * 成功即刷新清单（那一行从置灰变可选）。
 *
 * ## 账号是**部署级**的
 *
 * 授权的这一个 Qoder 账号全所共用（Credits 也记在它头上）。文案必须说出来，
 * 否则第二个律师会以为「我是不是没权限」。业务数据权限不受影响：工具调用走的是
 * 律师本人的 MCP 令牌，Qoder 账号只用来跑模型（见后端 `qoder_backend` 的说明）。
 *
 * ## 为什么不用 `window.open`
 *
 * 授权链接是一次性的（带 challenge），被弹窗拦截就等于白点。渲染成 `<a target=_blank>`
 * 由用户自己点，浏览器不会拦，也允许「复制链接到另一台机器打开」（服务器与用户机器
 * 常常不是同一台，这一点在律所内网部署里是常态）。
 *
 * ## 关闭时机
 *
 * 成功 → 自动关（并通知调用方刷新清单）；失败/超时 → 留在原地，用户可点「重新登录」。
 * 关掉弹窗**不会**中断后端那次授权——CLI 还在等，用户随时可以再点开（但这里不保留
 * 上一次的链接，重新点会起一次新的）。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, Copy, ExternalLink, Loader2, X } from 'lucide-react'

import { fetchQoderLoginStatus, startQoderLogin } from '../api'
import type { QoderLoginState } from '../types'

/** 轮询间隔：授权完成到界面更新最多慢 2 秒，比 SSE 便宜得多（一条 HTTP 而已）。 */
const POLL_INTERVAL_MS = 2000

/**
 * `kind → 登录流程`。当前只有 qoder；接第二个需要登录的运行时就在这张表里加一行，
 * 组件本身（文案、轮询、复制）不需要改。
 */
const LOGIN_FLOWS: Record<string, { start: () => Promise<QoderLoginState>; status: (loginId: string) => Promise<QoderLoginState> }> = {
  qoder: { start: () => startQoderLogin(), status: fetchQoderLoginStatus },
}

type Phase = 'starting' | 'waiting' | 'success' | 'failed'

export function AgentLoginDialog({
  kind,
  label,
  onClose,
  onDone,
}: {
  /** 后端 kind（如 `qoder`） */
  kind: string
  /** 给用户看的名字（"Qoder"） */
  label: string
  /** 关掉弹窗（取消 / 成功自动关都走它） */
  onClose: () => void
  /** 登录成功：调用方刷新后端清单（那一行从置灰变可选） */
  onDone: () => void
}) {
  const flow = LOGIN_FLOWS[kind]
  const [phase, setPhase] = useState<Phase>(flow ? 'starting' : 'failed')
  const [url, setUrl] = useState('')
  const [message, setMessage] = useState(flow ? '' : `暂不支持在界面里登录 ${label}，请联系管理员配置。`)
  const [loginId, setLoginId] = useState('')
  const [copied, setCopied] = useState(false)
  const closedRef = useRef(false)

  const start = useCallback(async () => {
    if (!flow) return
    setPhase('starting')
    setUrl('')
    setMessage('')
    setLoginId('')
    setCopied(false)
    try {
      const out = await flow.start()
      if (closedRef.current) return
      setLoginId(out.login_id)
      setUrl(out.url)
      setMessage(out.message)
      setPhase(out.state === 'success' ? 'success' : out.state === 'waiting' ? 'waiting' : 'failed')
    } catch (error) {
      if (closedRef.current) return
      // 后端 503 的文案就是给我们直接显示的（"未找到 qodercli" 之类）；
      // ky 的 HTTPError 把响应体包在 message 里，取不到就退回一句通用话。
      setMessage(error instanceof Error && error.message ? error.message : '无法发起登录，请稍后重试。')
      setPhase('failed')
    }
  }, [flow])

  // 打开即发起一次（不需要用户再点一次「开始」）
  useEffect(() => {
    closedRef.current = false
    void start()
    return () => {
      closedRef.current = true
    }
  }, [start])

  // 轮询：只在 waiting 时挂着，结果一到就摘
  useEffect(() => {
    if (phase !== 'waiting' || !loginId || !flow) return
    let cancelled = false
    const timer = setInterval(() => {
      void flow
        .status(loginId)
        .then((out) => {
          if (cancelled) return
          if (out.state === 'success') {
            setPhase('success')
            setMessage(out.message || '已登录，可以开始提问了。')
            onDone()
            return
          }
          if (out.state === 'failed' || out.state === 'expired') {
            setPhase('failed')
            setMessage(out.message || '授权未完成，请重新登录。')
          }
        })
        .catch(() => {
          // 单次轮询失败不改变结论：网络抖一下就宣布失败会误导用户重开一次授权
        })
    }, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [phase, loginId, flow, onDone])

  // Escape 关闭（与菜单同一套键盘口径）
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const copy = async () => {
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setMessage('')
    } catch {
      // 剪贴板被拒（http 环境 / 权限）时不要静默：提示改用「打开授权页」
      setMessage('复制失败，请直接点「打开授权页」。')
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-login-title"
      data-testid="agent-login-dialog"
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 p-4"
      // 点遮罩关闭（与 Escape 同义）；点内容不关
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div className="w-[420px] max-w-full rounded-[12px] border border-border bg-popover p-4 shadow-lg">
        <div className="flex items-start justify-between gap-2">
          <h2 id="agent-login-title" className="text-[14px] font-medium text-foreground">
            登录 {label}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="rounded-[6px] p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mt-2 text-[11.5px] leading-relaxed text-muted-foreground">
          登录的这一个 {label} 账号<strong className="text-foreground">全所共用</strong>（额度也记在它头上）。
          你的案件与合同权限不受影响——工具调用仍以你本人的身份执行。
        </p>

        <div className="mt-3" aria-live="polite">
          {phase === 'starting' && (
            <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              正在向 {label} 申请授权链接…
            </p>
          )}

          {phase === 'waiting' && (
            <div className="space-y-2">
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="flex w-full items-center justify-center gap-1.5 rounded-[8px] bg-primary px-3 py-2 text-[12.5px] font-medium text-primary-foreground hover:opacity-90"
              >
                <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                打开授权页
              </a>
              <div className="flex items-center gap-1.5">
                <input
                  readOnly
                  value={url}
                  aria-label="授权链接"
                  className="min-w-0 flex-1 truncate rounded-[6px] border border-border bg-secondary/40 px-2 py-1 text-[11px] text-muted-foreground"
                />
                <button
                  type="button"
                  onClick={() => void copy()}
                  className="flex flex-none items-center gap-1 rounded-[6px] border border-border px-2 py-1 text-[11px] hover:bg-secondary"
                >
                  {copied ? <Check className="h-3 w-3" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
                  {copied ? '已复制' : '复制'}
                </button>
              </div>
              <p className="flex items-center gap-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
                {message || '在浏览器里选择账号并确认，完成后这里会自动更新。'}
              </p>
            </div>
          )}

          {phase === 'success' && (
            <p className="flex items-center gap-1.5 text-[12px] text-foreground">
              <Check className="h-3.5 w-3.5 text-emerald-500" aria-hidden />
              已登录 {label}，可以开始提问了。
            </p>
          )}

          {phase === 'failed' && <p className="text-[12px] leading-relaxed text-destructive">{message}</p>}
        </div>

        <div className="mt-3 flex justify-end gap-2">
          {phase === 'success' && flow && (
            <button
              type="button"
              onClick={() => void start()}
              className="rounded-[8px] border border-border px-3 py-1.5 text-[12px] hover:bg-secondary"
              title="额度是账号级的：再加一个账号，长任务跑到限额时可自动换号重跑"
            >
              再添加一个账号
            </button>
          )}
          {phase === 'failed' && flow && (
            <button
              type="button"
              onClick={() => void start()}
              className="rounded-[8px] border border-border px-3 py-1.5 text-[12px] hover:bg-secondary"
            >
              重新登录
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              if (phase === 'success') onDone()
              onClose()
            }}
            className="rounded-[8px] border border-border px-3 py-1.5 text-[12px] hover:bg-secondary"
          >
            {phase === 'success' ? '完成' : '关闭'}
          </button>
        </div>
      </div>
    </div>
  )
}
