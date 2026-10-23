/**
 * 输入区：Enter 发送、Shift+Enter 换行；流式期间变为「停止」+ 可插话（steer）。
 *
 * 三种提交路径：
 * - 常规：Enter / 发送钮 → store.send（SSE 流式）
 * - 流式中：输入框保持可用，Enter → store.steer（运行中插话，不改写当前输出）；
 *   已插话的文本以「已插话 N 条」提示，可整体撤回（DELETE /queue）
 * - 后台模式（时钟开关）：提交后立即返回，任务在后台跑完写入会话通知
 *
 * 主题：中性灰阶，无 emoji；发送成功静默，失败由 MessageList 的错误行兜底。
 */

import { useRef, useState } from 'react'
import { ArrowUp, Clock, FolderOpen, Paperclip, Square, Undo2, X } from 'lucide-react'

import { formatFileSize } from '../domain'
import { useCopilot } from '../store'
import { TurnStatsView } from './TurnStatsView'

export function Composer() {
  const [text, setText] = useState('')
  const [bgMode, setBgMode] = useState(false)
  const streaming = useCopilot((s) => s.streaming)
  const queuedSteers = useCopilot((s) => s.queuedSteers)
  const pendingFiles = useCopilot((s) => s.pendingFiles)
  const pendingRefs = useCopilot((s) => s.pendingRefs)
  const uploading = useCopilot((s) => s.uploadingAttachments)
  const addAttachmentFiles = useCopilot((s) => s.addAttachmentFiles)
  const removeAttachmentFile = useCopilot((s) => s.removeAttachmentFile)
  const removeFolderRef = useCopilot((s) => s.removeFolderRef)
  const send = useCopilot((s) => s.send)
  const stop = useCopilot((s) => s.stop)
  const steer = useCopilot((s) => s.steer)
  const revokeQueuedSteers = useCopilot((s) => s.revokeQueuedSteers)
  const submitTask = useCopilot((s) => s.submitTask)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const submit = () => {
    const value = text.trim()
    if (!value && pendingFiles.length === 0 && pendingRefs.length === 0) return
    if (uploading) return
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
    const outgoing =
      value || (pendingRefs.length > 0 ? '请分析我引用的文件。' : '请分析我上传的附件。')
    void send(outgoing, (sent) => {
      if (!sent) setText((prev) => (prev.trim() ? prev : outgoing))
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  /** 跟随内容自适应高度（1–5 行） */
  const autoGrow = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }

  const placeholder = streaming
    ? '插话补充指令，Enter 送达当前对话…'
    : bgMode
      ? '后台运行：提交后可关闭页面，跑完会在会话里通知你…'
      : '问点什么…'

  return (
    <div className="flex-none border-t border-border p-2.5">
      {(pendingRefs.length > 0 || pendingFiles.length > 0) && (
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {pendingRefs.map((ref, i) => (
            <span
              key={`${ref.contractId}-${ref.subpath}`}
              className="flex max-w-full items-center gap-1 rounded-[6px] border border-border bg-primary/10 px-1.5 py-0.5 text-[11.5px] text-foreground"
              title={`合同 ${ref.contractId} · ${ref.subpath}（引用原文件，发送时由 AI 直接读取）`}
            >
              <FolderOpen className="h-3 w-3 flex-none text-primary" />
              <span className="max-w-52 truncate">{ref.subpath}</span>
              <button
                type="button"
                className="flex h-4 w-4 flex-none items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:bg-card hover:text-destructive"
                aria-label={`移除引用 ${ref.name}`}
                onClick={() => removeFolderRef(i)}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {pendingFiles.map((file, i) => (
            <span
              key={`${file.name}-${i}`}
              className="flex max-w-full items-center gap-1 rounded-[6px] border border-border bg-secondary/60 px-1.5 py-0.5 text-[11.5px] text-secondary-foreground"
              title={`${file.name} · ${formatFileSize(file.size)}`}
            >
              <Paperclip className="h-3 w-3 flex-none text-muted-foreground" />
              <span className="max-w-44 truncate">{file.name}</span>
              <span className="flex-none text-muted-foreground">{formatFileSize(file.size)}</span>
              <button
                type="button"
                className="flex h-4 w-4 flex-none items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:bg-card hover:text-destructive"
                aria-label={`移除附件 ${file.name}`}
                onClick={() => removeAttachmentFile(i)}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      {streaming && queuedSteers.length > 0 && (
        <div className="mb-1.5 flex items-center gap-1.5 px-1 text-[11.5px] text-muted-foreground">
          <span className="min-w-0 flex-1 truncate">已插话 {queuedSteers.length} 条，将在本轮生效</span>
          <button
            type="button"
            className="flex h-6 flex-none items-center gap-1 rounded-[6px] px-1.5 transition-colors hover:bg-secondary hover:text-foreground"
            onClick={() => void revokeQueuedSteers()}
            aria-label="撤回插话"
            title="撤回已排队、尚未生效的插话"
          >
            <Undo2 className="h-3 w-3" />
            撤回
          </button>
        </div>
      )}
      <div className="flex items-end gap-2 rounded-[12px] border border-input bg-background px-2.5 py-1.5 focus-within:border-foreground/40">
        <button
          type="button"
          className={`flex h-7 w-7 flex-none items-center justify-center rounded-[8px] transition-colors disabled:opacity-40 ${
            bgMode ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
          }`}
          onClick={() => setBgMode((v) => !v)}
          disabled={streaming || pendingFiles.length > 0 || pendingRefs.length > 0}
          aria-label={bgMode ? '关闭后台运行模式' : '切换为后台运行'}
          aria-pressed={bgMode}
          title={
            pendingFiles.length > 0
              ? '带附件/引用的消息只能即时对话（后台任务暂不支持）'
              : bgMode
                ? '后台运行已开启：提交的任务在后台执行'
                : '切换为后台运行：适合要跑几分钟的长任务'
          }
        >
          <Clock className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-40"
          onClick={() => fileInputRef.current?.click()}
          disabled={streaming || uploading}
          aria-label="添加附件"
          title="添加附件（PDF / Word / 图片 / 文本，≤20MB；也可直接拖入面板）"
        >
          <Paperclip className="h-4 w-4" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.png,.jpg,.jpeg,.tif,.tiff,.txt"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addAttachmentFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <textarea
          ref={textareaRef}
          value={text}
          rows={1}
          placeholder={placeholder}
          className="max-h-30 min-h-6 flex-1 resize-none bg-transparent text-[13px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground"
          onChange={(e) => {
            setText(e.target.value)
            autoGrow()
          }}
          onKeyDown={handleKeyDown}
        />
        {streaming ? (
          <button
            type="button"
            className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-85"
            onClick={stop}
            aria-label="停止生成"
            title="停止生成（已生成部分会保留）"
          >
            <Square className="h-3 w-3 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-85 disabled:opacity-30"
            onClick={submit}
            disabled={uploading || (!text.trim() && pendingFiles.length === 0 && pendingRefs.length === 0)}
            aria-label={bgMode ? '提交后台任务' : '发送'}
            title={uploading ? '附件上传中…' : undefined}
          >
            <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.5} />
          </button>
        )}
      </div>
      <p className="mt-1.5 flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
        <span className="min-w-0 flex-1 truncate">
          {bgMode ? '后台任务跑完会写入会话通知；高危操作会等你回来审批。' : 'AI 回答仅供参考，法律判断需由律师复核。'}
        </span>
        <TurnStatsView />
      </p>
    </div>
  )
}
