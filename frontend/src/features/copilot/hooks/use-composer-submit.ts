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
 * - 流式中 Enter 是「插话」（steer），不是新消息。
 * - 常规发送先清空正文腾出输入位，早失败（建会话/上传附件失败）时回填，
 *   但期间用户又输入了新内容就不打扰（只补空）。
 *
 * 拆出时刻意保留「拿同一份 state + hook 返回」的形态：send/steer/submitTask
 * 是 zustand 稳定引用，speech 与 slash 的交互态（listening / onKeyDown）必须
 * 由 Composer 传给 textarea / toolbar，故以参数注入而不是在本文件重新取。
 */

import type { RefObject } from 'react'

import { defaultOutgoingPrompt } from '../domain'
import type { FolderRefDraft, SelectionQuote } from '../types'

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
    bgMode,
    setBgMode,
    speech,
    slash,
    send,
    steer,
    submitTask,
  } = options

  /** 跟随内容自适应高度（1–5 行） */
  const autoGrow = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
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
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
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

  return { submit, handleKeyDown, autoGrow }
}
