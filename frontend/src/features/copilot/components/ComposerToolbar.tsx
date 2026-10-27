/**
 * 输入框左侧的工具按钮组：后台运行开关 / 附件（含隐藏 file input）/ 语音输入。
 *
 * 从 Composer 拆出（后者超软红线）。四个按钮共享同一套「禁用条件」——流式、上传中、
 * 发送中都要压住，否则会在「上传完成 → 消息入列」的窗口里被重复触发；条件由
 * Composer 算好传进来，本组件只负责渲染与点击分发。
 */

import { Clock, Mic, Paperclip } from 'lucide-react'

/** 工具按钮的统一外观（三个纯图标按钮共用，避免三份重复长串） */
const iconButtonClass =
  'flex h-7 w-7 flex-none items-center justify-center rounded-[8px] transition-colors disabled:opacity-40'

export function ComposerToolbar({
  bgMode,
  onToggleBgMode,
  bgToggleDisabled,
  attachDisabled,
  onPickFiles,
  fileInputRef,
  onFilesPicked,
  speech,
  speechBase,
}: {
  bgMode: boolean
  onToggleBgMode: () => void
  /** 后台模式开关是否禁用（流式/带附件/发送中等） */
  bgToggleDisabled: boolean
  attachDisabled: boolean
  onPickFiles: () => void
  fileInputRef: React.RefObject<HTMLInputElement | null>
  onFilesPicked: (files: FileList) => void
  /** useSpeechInput 的返回值（supported/listening/start/stop） */
  speech: {
    supported: boolean
    listening: boolean
    start: (base: string) => void
    stop: (quiet?: boolean) => void
  }
  /** 开始听写时的基线文本（点击那一刻输入框里的草稿） */
  speechBase: string
}) {
  return (
    <>
      <button
        type="button"
        className={`${iconButtonClass} ${
          bgMode ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
        }`}
        onClick={onToggleBgMode}
        disabled={bgToggleDisabled}
        aria-label={bgMode ? '关闭后台运行模式' : '切换为后台运行'}
        aria-pressed={bgMode}
        title={
          bgToggleDisabled
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
        className={`${iconButtonClass} text-muted-foreground hover:bg-secondary hover:text-foreground`}
        onClick={onPickFiles}
        disabled={attachDisabled}
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
          if (e.target.files) onFilesPicked(e.target.files)
          e.target.value = ''
        }}
      />
      {/* Firefox 没有 Web Speech：直接不渲染按钮，而不是渲染一个灰的 */}
      {speech.supported && (
        <button
          type="button"
          className={`${iconButtonClass} ${
            speech.listening
              ? 'bg-destructive/10 text-destructive'
              : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
          }`}
          onClick={() => (speech.listening ? speech.stop() : speech.start(speechBase))}
          aria-label={speech.listening ? '停止语音输入' : '语音输入'}
          aria-pressed={speech.listening}
          title={
            speech.listening
              ? '正在听写，点击结束（内容已实时进入输入框，可随口修改后发送）'
              : '语音输入：中文听写，内容实时进入输入框'
          }
        >
          <Mic className={`h-4 w-4 ${speech.listening ? 'animate-pulse' : ''}`} />
        </button>
      )}
    </>
  )
}
