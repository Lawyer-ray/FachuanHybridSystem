/**
 * 输入区：Enter 发送、Shift+Enter 换行；流式期间变为「停止」+ 可插话（steer）。
 *
 * 三种提交路径：
 * - 常规：Enter / 发送钮 → store.send（SSE 流式）
 * - 流式中：输入框保持可用，Enter → store.steer（运行中插话，不改写当前输出）；
 *   已插话的文本以「已插话 N 条」提示，可整体撤回（DELETE /queue）
 * - 后台模式（时钟开关）：提交后立即返回，任务在后台跑完写入会话通知
 *
 * `/` 打头时弹命令菜单（技能补全 `/skill:名字 ` + 内置命令），交互态在
 * use-slash-menu；底栏显示会话上下文水位（done 事件 / stats 接口回填）。
 *
 * 主题：中性灰阶，无 emoji；发送成功静默，失败由 MessageList 的错误行兜底。
 *
 * 拆分记录（本文件已收敛到 ≤200 行）：ComposerFooter / ComposerQuote / PendingChips /
 * ComposerToolbar（左侧三个工具按钮 + 隐藏 file input）、use-composer-submit
 * （submit + handleKeyDown + autoGrow）、use-composer-intake（框选引用 / 选区预填
 * 两条事件通道）。submit 牵动 speech / slash / send 三个 hook 的协调顺序，
 * 改它之前先读 use-composer-submit.ts 的文件头。
 */

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, Square, Undo2 } from 'lucide-react'
import { toast } from 'sonner'

import { fetchAgentSkills } from '../api'
import { useComposerIntake } from '../hooks/use-composer-intake'
import { useComposerSubmit } from '../hooks/use-composer-submit'
import { useSlashMenu } from '../hooks/use-slash-menu'
import { useSpeechInput } from '../hooks/use-speech-input'
import { useCopilot } from '../store'
import { ComposerFooter } from './ComposerFooter'
import { ComposerQuote } from './ComposerQuote'
import { ComposerToolbar } from './ComposerToolbar'
import { PendingChips } from './PendingChips'
import { SlashMenu } from './SlashMenu'

/** 流式中的「已插话 N 条」提示条（撤回按钮在前一排，两者共用一行） */
const STEER_BAR_CLASS = 'mb-1.5 flex items-center gap-1.5 px-1 text-[11.5px] text-muted-foreground'
const REVOKE_BUTTON_CLASS = 'flex h-6 flex-none items-center gap-1 rounded-[6px] px-1.5 transition-colors hover:bg-secondary hover:text-foreground'
const STOP_BUTTON_CLASS = 'flex h-7 w-7 flex-none items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-85'
const SEND_BUTTON_CLASS = 'copilot-send flex h-7 w-7 flex-none items-center justify-center rounded-full disabled:opacity-30 disabled:shadow-none'

export function Composer() {
  const [text, setText] = useState('')
  const [bgMode, setBgMode] = useState(false)
  const streaming = useCopilot((s) => s.streaming)
  const queuedSteers = useCopilot((s) => s.queuedSteers)
  const pendingFiles = useCopilot((s) => s.pendingFiles)
  const pendingRefs = useCopilot((s) => s.pendingRefs)
  const pendingQuote = useCopilot((s) => s.pendingQuote)
  const setPendingQuote = useCopilot((s) => s.setPendingQuote)
  const uploading = useCopilot((s) => s.uploadingAttachments)
  // 发送全过程在途（建会话/上传附件期间）：与 uploading 一起置忙，堵住
  // 「上传完成 → 消息入列」这段两者都为 false 的窗口里的二次提交
  const sending = useCopilot((s) => s.sending)
  const compactContext = useCopilot((s) => s.compactContext)
  const sessionId = useCopilot((s) => s.sessionId)
  const messageCount = useCopilot((s) => s.messages.length)
  const addAttachmentFiles = useCopilot((s) => s.addAttachmentFiles)
  const send = useCopilot((s) => s.send)
  const stop = useCopilot((s) => s.stop)
  const steer = useCopilot((s) => s.steer)
  const revokeQueuedSteers = useCopilot((s) => s.revokeQueuedSteers)
  const submitTask = useCopilot((s) => s.submitTask)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  /** 语音听写（Chrome/Edge 原生，zh-CN）：内容实时进草稿；onText 带 autoGrow
   *  ——语音进来也要长个儿，不能等用户敲键才撑高 */
  const speech = useSpeechInput({
    onText: (t) => {
      setText(t)
      requestAnimationFrame(autoGrow)
    },
  })

  // 权限拒绝这类用户必须知道原因的失败，弹一次 toast（悬停 title 太隐蔽）
  useEffect(() => {
    if (speech.error) toast.error('语音输入失败', { description: speech.error })
  }, [speech.error])

  // 技能清单（`/` 菜单数据源）：菜单打开才被消费，失败静默降级为「只有内置命令」
  const skillsQuery = useQuery({ queryKey: ['agent-skills'], queryFn: () => fetchAgentSkills(), staleTime: 5 * 60_000, retry: false })
  const skills = skillsQuery.data?.skills ?? []

  const slash = useSlashMenu({
    text,
    skills,
    hasSession: Boolean(sessionId && messageCount > 0),
    onSkill: (name) => {
      setText(`/skill:${name} `)
      textareaRef.current?.focus()
    },
    onCommand: (id) => {
      if (id !== 'compact') return
      setText('')
      void compactContext()
    },
  })

  const { submit, handleKeyDown, autoGrow } = useComposerSubmit({
    text, setText, textareaRef, pendingFiles, pendingRefs, pendingQuote, uploading, sending,
    streaming, bgMode, setBgMode, speech, slash, send, steer, submitTask,
  })

  // 两条外部写入通道：框选引用（挂引用卡）与选区预填（追加文字），见 hook 文件头
  useComposerIntake({ setText, setPendingQuote, textareaRef, autoGrow })

  /** 点快捷 pill：直接替换草稿（是明确动作，别把两条指令拼在一起），光标落末尾 */
  const applyPrompt = (prompt: string) => {
    setText(prompt)
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (!el) return
      el.focus()
      el.setSelectionRange(el.value.length, el.value.length)
      autoGrow()
    })
  }

  const placeholder = speech.listening
    ? '正在听写…说完点麦克风结束，可手动修改后发送'
    : streaming
      ? '插话补充指令，Enter 送达当前对话…'
      : bgMode
        ? '后台运行：提交后可关闭页面，跑完会在会话里通知你…'
        : '问点什么…'
  /** 已挂附件/文件夹引用：有它们时后台任务不适用，发送钮也不算空 */
  const hasPendingAttachments = pendingFiles.length > 0 || pendingRefs.length > 0
  /** 输入框是否有内容（正文 / 附件 / 文件夹引用 / 框选引用任一） */
  const hasPayload = Boolean(text.trim()) || hasPendingAttachments || Boolean(pendingQuote)

  return (
    <div className="flex-none border-t border-border p-2.5">
      {/* 内容限宽居中：与消息栏同宽对齐（两边都走 max-w-6xl，宽度一致不错位） */}
      <div className="mx-auto w-full max-w-6xl">
        {/* 框选引用（豆包式）：选区挂成引用条、输入框保持空白；快捷 pills 一键补指令，随消息出站 */}
        {pendingQuote && (
          <ComposerQuote quote={pendingQuote} onRemove={() => setPendingQuote(null)} onPickPrompt={applyPrompt} />
        )}
        <PendingChips />
        {streaming && queuedSteers.length > 0 && (
          <div className={STEER_BAR_CLASS}>
            <span className="min-w-0 flex-1 truncate">已插话 {queuedSteers.length} 条，将在本轮生效</span>
            <button type="button" className={REVOKE_BUTTON_CLASS} onClick={() => void revokeQueuedSteers()} aria-label="撤回插话" title="撤回已排队、尚未生效的插话">
              <Undo2 className="h-3 w-3" />
              撤回
            </button>
          </div>
        )}
        <div className="relative flex items-end gap-2 rounded-[14px] border border-border bg-background px-2.5 py-1.5 shadow-sm transition-[border-color,box-shadow] duration-150 focus-within:border-foreground/30 focus-within:ring-4 focus-within:ring-foreground/10">
          {slash.open && (
            <SlashMenu items={slash.items} selectedIndex={slash.index} onHover={slash.setIndex} onSelect={slash.apply} />
          )}
          <ComposerToolbar
            bgMode={bgMode}
            onToggleBgMode={() => setBgMode((v) => !v)}
            bgToggleDisabled={streaming || hasPendingAttachments || sending}
            attachDisabled={streaming || uploading || sending}
            onPickFiles={() => fileInputRef.current?.click()}
            fileInputRef={fileInputRef}
            onFilesPicked={addAttachmentFiles}
            speech={speech}
            speechBase={text}
          />
          <textarea
            ref={textareaRef}
            value={text}
            rows={1}
            placeholder={placeholder}
            className="max-h-30 min-h-6 flex-1 resize-none bg-transparent text-[13px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground"
            onChange={(e) => {
              // 听写中手动改字：以编辑后的全文为新基线，后续听写在其后追加
              if (speech.listening) speech.rebase(e.target.value)
              setText(e.target.value)
              autoGrow()
            }}
            onKeyDown={handleKeyDown}
          />
          {streaming ? (
            <button type="button" className={STOP_BUTTON_CLASS} onClick={stop} aria-label="停止生成" title="停止生成（已生成部分会保留）">
              <Square className="h-3 w-3 fill-current" />
            </button>
          ) : (
            <button type="button" className={SEND_BUTTON_CLASS} onClick={submit} disabled={uploading || sending || !hasPayload} aria-label={bgMode ? '提交后台任务' : '发送'} title={uploading ? '附件上传中…' : undefined}>
              <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.5} />
            </button>
          )}
        </div>
        <ComposerFooter bgMode={bgMode} />
      </div>
    </div>
  )
}
