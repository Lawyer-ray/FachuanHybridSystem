/**
 * `guarded` 动作的前端本地二次确认：把 store 的注册点接到一个**真的会被渲染**的对话框上。
 *
 * ## 为什么这个 hook 自己挂一个 React root（而不是返回 JSX 让调用方渲染）
 *
 * 唯一的挂载点是 `useUiToolHost()`——它在 Router 内、且被面板与助手页共用，但它**是纯
 * hook、不渲染树**（返回 void，调用方 `UiToolHostInner` 返回 null）。hook 没法把 JSX
 * 塞进别人的树里，所以这里用与 sonner 同思路的命令式挂载：`createRoot` 一个挂在 `body`
 * 下的容器，把对话框渲染进去。对话框本身用 `@/components/ui/dialog`（Radix），它的
 * Content 仍会 portal 到 `body`，所以 `z-[130]`、焦点陷阱、Esc/遮罩关闭都与既有弹窗同一套。
 *
 * 另一个被否掉的做法是把 root 的创建推迟到「第一条请求到来时」：那样每次确认都要新建
 * 一个 root（React 的卸载/挂载语义、测试里的 act 边界都更绕），而这里一次挂载的开销只是
 * 一个空容器 + `render(null)`。
 *
 * ## 为什么写 `createElement` 而不是 JSX
 *
 * 本文件是 `.ts`（与 store 同目录的 hook，不引入编译期 JSX 约定），而仓库的
 * `react-refresh` 只对组件文件生效——这里不导出任何组件。用 `createElement` 让
 * 「谁是组件、谁只是工厂函数」始终一眼可见：`GuardedConfirmDialog` 是唯一渲染的东西。
 *
 * ## 为什么卸载时把在等的请求按「取消」结账
 *
 * 面板收起 / 路由切走时宿主会卸载。如果这时有一条第 guarded 动作正等着点击，
 * 直接丢掉那个 Promise 会让 store 的写锁永远等下去（后续写动作全部排队超限），
 * 而律师什么都没看见。按 `false` 结账是唯一诚实的选择：**没人同意，就不执行**。
 */

import { createElement, useEffect } from 'react'
import type { ReactElement } from 'react'
import { createRoot } from 'react-dom/client'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import {
  releaseGuardedConfirmHandler,
  setGuardedConfirmHandler,
} from '../store/ui-guarded-confirm'
import type { GuardedConfirmHandler, GuardedConfirmRequest } from '../store/ui-guarded-confirm'

/** 参数预览的截断长度（字符）：弹框只用来**认对象**，完整参数在审计里 */
const ARGS_PREVIEW_LIMIT = 400

/** `args` → 可读的多行预览（超长截断；截断处留个「…」说明不是全部） */
function previewArgs(args: Record<string, unknown>): string {
  const text = JSON.stringify(args, null, 2) ?? '{}'
  return text.length > ARGS_PREVIEW_LIMIT ? `${text.slice(0, ARGS_PREVIEW_LIMIT)}…` : text
}

/** 对话框本体（纯展示 + 两个回调，不持有状态：状态在下面的宿主闭包里） */
function GuardedConfirmDialog({
  request,
  onCancel,
  onConfirm,
}: {
  request: GuardedConfirmRequest
  onCancel: () => void
  onConfirm: () => void
}): ReactElement {
  return createElement(
    Dialog,
    {
      open: true,
      // Esc / 点速罩 / 右上角 X 都走 Radix 的「请求关闭」：一律当成取消（没确认就不执行）
      onOpenChange: (open: boolean) => {
        if (!open) onCancel()
      },
    },
    createElement(
      DialogContent,
      null,
      createElement(
        DialogHeader,
        null,
        createElement(DialogTitle, null, `需要你确认：${request.title}`),
        // Radix 缺 Description 会打 a11y 告警；顺便把「这次点击算什么」说清楚——
        // 它不是批准凭据（批准在服务端审批闸门那边，已经过了）。
        createElement(
          DialogDescription,
          null,
          '这是页面上的一次防误点确认，不是审批凭据。确认后动作立即执行。',
        ),
      ),
      createElement(
        'pre',
        {
          // 等宽 + 可滚动：参数是给律师核对「是哪一个包」的，不是给人读的段落
          className: 'max-h-40 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap',
          'data-testid': 'ui-guarded-confirm-args',
        },
        previewArgs(request.args),
      ),
      createElement(
        DialogFooter,
        null,
        createElement(Button, { type: 'button', variant: 'outline', onClick: onCancel }, '取消'),
        createElement(Button, { type: 'button', variant: 'destructive', onClick: onConfirm }, '确认执行'),
      ),
    ),
  )
}

/** 宿主控制器：`ask` 注册给 store，`dispose` 负责卸载 root 并把在等的请求按取消结账 */
interface GuardedConfirmHost {
  ask: GuardedConfirmHandler
  dispose: () => void
}

/** 建一个挂在 `body` 下的命令式 React root，并返回「问一次」的入口（理由见文件头） */
function createGuardedConfirmHost(): GuardedConfirmHost {
  const container = document.createElement('div')
  container.setAttribute('data-ui-guarded-confirm-host', '')
  document.body.appendChild(container)
  const root = createRoot(container)
  /** 当前这一条请求的结账函数；null = 没有请求在等 */
  let settle: ((approved: boolean) => void) | null = null

  /** 结账一次：先撤掉弹框再回话，避免回调里同步抛错时留下一个点不掉的框 */
  const finish = (approved: boolean): void => {
    const resolve = settle
    settle = null
    root.render(null)
    resolve?.(approved)
  }

  const ask: GuardedConfirmHandler = (request) => {
    // 上一条还挂着（正常情况下不会：写锁保证同一时刻只有一条写动作在飞）也先按取消结账——
    // 两个框叠在一起时，律师点哪个都说不清自己批准了哪一条。
    finish(false)
    return new Promise<boolean>((resolve) => {
      settle = resolve
      root.render(
        createElement(GuardedConfirmDialog, {
          request,
          onCancel: () => finish(false),
          onConfirm: () => finish(true),
        }),
      )
    })
  }

  const dispose = (): void => {
    finish(false)
    root.unmount()
    container.remove()
  }

  root.render(null)
  return { ask, dispose }
}

/**
 * 挂载二次确认宿主（`useUiToolHost` 里一行接入）。重复挂载时**后挂的那个**是当前宿主，
 * 先卸载的那个只按归属撤销、不会把另一个的槽位清掉。
 */
export function useUiGuardedConfirm(): void {
  useEffect(() => {
    const host = createGuardedConfirmHost()
    setGuardedConfirmHandler(host.ask)
    return () => {
      releaseGuardedConfirmHandler(host.ask)
      host.dispose()
    }
  }, [])
}
