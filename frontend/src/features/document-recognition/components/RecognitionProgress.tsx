import { Check, FileText } from 'lucide-react'

import { cn } from '@/lib/utils'

import '../document-recognition.css'

interface Props {
  /** submitting=上传中；polling=识别中（文本提取 + LLM 分析） */
  phase: 'submitting' | 'polling'
  fileName: string
  hint: string
}

const STEPS = ['上传文件', '识别中', '人工确认'] as const

/** 识别进行中的等待态：文件卡扫描线动画 + 三步进度指示。 */
export function RecognitionProgress({ phase, fileName, hint }: Props) {
  const activeStep = phase === 'submitting' ? 0 : 1
  return (
    <div className="flex animate-in fade-in duration-300 flex-col items-center gap-5 py-8">
      {/* 文件卡 + 扫描线 */}
      <div className="relative h-[104px] w-[84px] overflow-hidden rounded-[10px] border border-border bg-card shadow-sm">
        <div className="flex h-full flex-col items-center justify-center gap-2 px-1.5">
          <FileText className="dr-glow h-7 w-7 text-status-blue" />
          <span className="line-clamp-2 w-full text-center text-[9px] leading-[1.35] text-muted-foreground">
            {fileName}
          </span>
        </div>
        <div className="dr-scanline absolute inset-x-2 top-1/2 h-px -translate-y-1/2" />
      </div>

      {/* 三步进度 */}
      <div className="flex items-center gap-1.5">
        {STEPS.map((label, i) => {
          const done = i < activeStep
          const active = i === activeStep
          return (
            <div key={label} className="flex items-center gap-1.5">
              <span
                className={cn(
                  'flex h-[18px] w-[18px] items-center justify-center rounded-full border text-[10px] transition-colors duration-300',
                  done && 'border-status-green bg-status-green text-white',
                  active && 'border-status-blue bg-status-blue-bg text-status-blue',
                  !done && !active && 'border-border text-muted-foreground',
                )}
              >
                {done ? <Check className="h-2.5 w-2.5" strokeWidth={3} /> : i + 1}
              </span>
              <span
                className={cn(
                  'text-[11px] transition-colors duration-300',
                  active ? 'font-semibold text-foreground' : 'text-muted-foreground',
                )}
              >
                {label}
              </span>
              {i < STEPS.length - 1 && (
                <span
                  className={cn(
                    'mx-1 h-px w-5 transition-colors duration-500',
                    done ? 'bg-status-green' : 'bg-border',
                  )}
                />
              )}
            </div>
          )
        })}
      </div>

      <span className="text-[12px] text-muted-foreground">{hint}</span>
    </div>
  )
}
