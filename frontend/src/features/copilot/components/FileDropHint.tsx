/**
 * 拖拽悬停提示层：文件拖进 AI 助手区域时盖住宿主，告诉用户「松手即可添加」。
 *
 * 抽屉面板与独立页共用同一段文案与观感——文件能否拖入不该因为宿主不同而变。
 * 定位（absolute inset-0）由本组件自己出：两个宿主的根节点都是有定位的容器。
 */

import { Paperclip } from 'lucide-react'

export function FileDropHint() {
  return (
    <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center bg-background/70 backdrop-blur-[1px]">
      <div className="flex flex-col items-center gap-2 rounded-[14px] border-2 border-dashed border-primary/60 bg-card px-8 py-6 text-center shadow-lg">
        <Paperclip className="h-6 w-6 text-primary" />
        <p className="text-[14px] font-semibold text-foreground">松手添加附件</p>
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          PDF / Word / 图片（PNG·JPG·TIFF）/ TXT · 单个 ≤ 20MB
          <br />
          附件随下一条消息一起发送，AI 会自动读取内容
        </p>
      </div>
    </div>
  )
}
