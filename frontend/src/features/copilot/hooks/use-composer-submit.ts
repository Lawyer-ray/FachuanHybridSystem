/**
 * 输入区的提交逻辑：submit / handleKeyDown / autoGrow（跟随内容撑高 1–5 行）。
 *
 * 从 Composer 拆出（后者超软红线）。**这里的顺序是踩过坑的，不要重排**：
 *
 * - 听写中发送先 `speech.stop(true)` 静默停止（草稿里已含说到的最后一个字，
 *   interim 每次 onresult 都实时 emit 进了输入框；停止后再 emit 会把发掉的
 *   内容「复活」回已清空的输入框）。
 * - `uploading || sending` 两个标志都要挡：「上传完成 → 消息入列」之间两者
 *   都为 false 的窗口里二次提交会重复发。
 * - 流式中 Enter 是「插话」（steer），不是新消息；当前后端不声明 `steer` 能力
 *   时改为提示「等本轮结束」，绝不静默丢弃用户的输入。
 * - 常规发送先清空正文腾出输入位，早失败（建会话/上传附件失败）时回填，
 *   但期间用户又输入了新内容就不打扰（只补空）。
 *
 * 拆出时刻意保留「拿同一份 state + hook 返回」的形态：send/steer/submitTask
 * 是 zustand 稳定引用，speech 与 slash 的交互态（listening / onKeyDown）必须
 * 由 Composer 传给 textarea / toolbar，故以参数注入而不是在本文件重新取。
 *
 * IME 守卫（useImeEnterGuard）在本文件内挂载并把 composition 处理器一并返回，
 * 由 Composer 绑到 textarea：合成态的生命周期与 Enter 判定必须在同一处，
 * 拆给两处会漂移。
 */

import type { RefObject } from 'react'

import { defaultOutgoingPrompt } from '../domain'
import { useCopilot } from '../store'
import type { FolderRefDraft, SelectionQuote } from '../types'
import { useImeEnterGuard } from './use-ime-enter-guard'

/** 输入框自适应高度的像素上限（约 5 行）：全 feature 只此一份，改它即改两处调用 */
export const MAX_COMPOSER_HEIGHT = 120

/**
 * 跟随内容撑高：先归零再按 scrollHeight 夹到 {@link MAX_COMPOSER_HEIGHT}。
 *
 * 具名导出而不是在两处各写一遍：Composer 的 `@` 选中路径（选完后要立即长个儿）
 * 早于 useComposerSubmit 返回，所以它在 Composer 里直接调；本 hook 的 autoGrow
 * 也走同一个函数，两处口径不可能再漂。
 */
export function growTextarea(el: HTMLTextAreaElement): void {
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, MAX_COMPOSER_HEIGHT)}px`
}

export interface ComposerSubmitOptions {
  text: string
  setText: React.Dispatch<React.SetStateAction<string>>
  textareaRef: RefObject<HTMLTextAreaElement | null>
  pendingFiles: File[]
  pendingRefs: FolderRefDraft[]
  pendingQuote: SelectionQuote | null
  uploading: boolean
  sending: boolean
  streaming: boolean
  /** 当前后端是否支持运行中插话（`BackendCapabilities.steer`） */
  steerEnabled: boolean
  bgMode: boolean
  setBgMode: (on: boolean) => void
  speech: { listening: boolean; stop: (quiet?: boolean) => void }
  slash: { onKeyDown: (e: React.KeyboardEvent) => boolean }
  send: (outgoing: string, onQueued?: (sent: boolean) => void) => Promise<void>
  steer: (text: string) => Promise<void>
  submitTask: (text: string) => Promise<void>
}

export function useComposerSubmit(options: ComposerSubmitOptions) {
  const {
    text,
    setText,
    textareaRef,
    pendingFiles,
    pendingRefs,
    pendingQuote,
    uploading,
    sending,
    streaming,
    steerEnabled,
    bgMode,
    setBgMode,
    speech,
    slash,
    send,
    steer,
    submitTask,
  } = options

  /** 输入法 Enter 守卫：选词确认的 Enter 不能当发送（PIT-006） */
  const ime = useImeEnterGuard()

  /** 跟随内容自适应高度（1–5 行）：夹高口径见 growTextarea */
  const autoGrow = () => {
    const el = textareaRef.current
    if (!el) return
    growTextarea(el)
  }

  const submit = () => {
    // 听写中直接发送：静默停止（草稿里已含说到的最后一个字，interim 每次
    // onresult 都实时 emit 进了输入框），停止后再 emit 会把发掉的内容
    // 「复活」回已清空的输入框
    if (speech.listening) speech.stop(true)
    const value = text.trim()
    if (!value && pendingFiles.length === 0 && pendingRefs.length === 0 && !pendingQuote) return
    if (uploading || sending) return
    if (streaming) {
      // 后端不支持插话（如声明 steer=false）：说清楚为什么没反应，而不是把
      // 用户敲的这段字默默扔掉——后者看起来就是「按了没反应」
      if (!steerEnabled) {
        useCopilot.setState({ lastError: '当前后端不支持运行中插话，请等本轮结束后再发送' })
        return
      }
      // 运行中插话：不改写当前输出，在工具调用后、下次模型调用前生效
      void steer(value)
      setText('')
      return
    }
    if (bgMode) {
      setBgMode(false)
      setText('')
      void submitTask(value)
      return
    }
    // 先清空正文腾出输入位；早失败（建会话/附件上传失败）时回填，别让
    // 用户重打一遍。期间用户又输入了新内容则不打扰（只补空）。
    setText('')
    const outgoing = value || defaultOutgoingPrompt(pendingRefs, pendingFiles.length, pendingQuote)
    void send(outgoing, (sent) => {
      if (!sent) setText((prev) => (prev.trim() ? prev : outgoing))
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // 合成中 / compositionend 后尾随窗口的 Enter 一律吞掉，且必须在 slash 之前：
    // 菜单开着时 Enter 本来是「选中菜单项」，但选词那次 Enter 绝不能顺带选中它。
    if (ime.shouldIgnoreEnter(e)) {
      ime.guardEnter(e)
      return
    }
    // Shift+Enter 是换行，永远不是发送，也**不该被 slash 菜单当成「选中项」**：
    // slash.onKeyDown 的 case 'Enter' 不看 shiftKey，菜单开着时 Shift+Enter 会
    // 直接 apply 选中项。所以在问菜单之前就短路——换行是输入法/浏览器的事。
    if (e.key === 'Enter' && e.shiftKey) return
    if (e.key === 'Enter') {
      // 菜单开着时 Enter 是「选中菜单项」不是「发送」；其余菜单键同理短路
      if (slash.onKeyDown(e)) {
        e.preventDefault()
        return
      }
      e.preventDefault()
      submit()
      return
    }
    if (slash.onKeyDown(e)) {
      e.preventDefault()
    }
  }

  return {
    submit,
    handleKeyDown,
    autoGrow,
    ime,
    onCompositionStart: ime.onCompositionStart,
    onCompositionEnd: ime.onCompositionEnd,
  }
}
