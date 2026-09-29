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

/** 识别进行中的等待态：堆叠纸张扫描场景 + 三步流光进度。 */
export function RecognitionProgress({ phase, fileName, hint }: Props) {
  const activeStep = phase === 'submitting' ? 0 : 1
  return (
    <div className="flex animate-in fade-in flex-col items-center justify-center gap-7 py-10">
      {/* 堆叠双纸张 + 扫描线 */}
      <div className="relative flex h-[132px] w-[168px] items-center justify-center">
        {/* 底层错位纸张 */}
        <div className="absolute inset-x-6 top-3 h-[112px] rotate-[5deg] rounded-[10px] border border-border bg-secondary/60" />
        <div className="absolute inset-x-4 top-1.5 h-[118px] -rotate-[3deg] rounded-[10px] border border-border bg-secondary/80" />
        {/* 前层纸张：图标 + 檀纸条 + 扫描线 */}
        <div className="relative flex h-[126px] w-[104px] flex-col items-center justify-center gap-2.5 overflow-hidden rounded-[10px] border border-border bg-card shadow-md">
          <FileText className="dr-glow h-8 w-8 text-status-blue" />
          <div className="flex w-full flex-col items-center gap-[3px] px-4">
            <span className="h-[3px] w-full rounded-full bg-border" />
            <span className="h-[3px] w-4/5 rounded-full bg-border" />
            <span className="h-[3px] w-3/5 rounded-full bg-border" />
          </div>
          <div className="dr-scanline absolute inset-x-2 top-1/2 h-[2px] -translate-y-1/2 rounded-full" />
        </div>
      </div>

      <span className="max-w-[320px] truncate text-center text-[11.5px] text-muted-foreground">{fileName}</span>

      {/* 三步进度：完成绿勾 / 激活流光连接线 */}
      <div className="flex items-center gap-1">
        {STEPS.map((label, i) => {
          const done = i < activeStep
          const active = i === activeStep
          return (
            <div key={label} className="flex items-center gap-1.5">
              {i > 0 && (
                <span
                  className={cn(
                    'mx-1 h-[2px] w-9 overflow-hidden rounded-full',
                    done ? 'bg-status-green' : active ? 'dr-connector-active' : 'bg-border',
                  )}
                />
              )}
              <span
                className={cn(
                  'flex h-[20px] w-[20px] items-center justify-center rounded-full border text-[10px] transition-all duration-300',
                  done && 'border-status-green bg-status-green text-white',
                  active && 'border-status-blue bg-status-blue-bg text-status-blue shadow-[0_0_0_4px] shadow-status-blue/10',
                  !done && !active && 'border-border bg-card text-muted-foreground',
                )}
              >
                {done ? <Check className="h-2.5 w-2.5" strokeWidth={3} /> : i + 1}
              </span>
              <span
                className={cn(
                  'text-[11.5px] transition-colors duration-300',
                  active ? 'font-semibold text-foreground' : 'text-muted-foreground',
                )}
              >
                {label}
              </span>
            </div>
          )
        })}
      </div>

      <span className="flex items-center gap-2 text-[12px] text-muted-foreground">
        <span className="dr-pulse-dot h-1.5 w-1.5 rounded-full bg-status-blue" />
        {hint}
      </span>
    </div>
  )
}
