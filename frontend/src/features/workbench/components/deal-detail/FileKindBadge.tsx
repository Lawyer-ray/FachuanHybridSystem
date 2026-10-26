import { FileSpreadsheet, FileText, Image as ImageIcon, File as FileIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * 文件类型的视觉标识。
 *
 * 为什么不用系统默认文件图标：合同文件夹里 80% 是 pdf / docx，同一种灰图标
 * 只能靠读文件名分辨，扫一眼的负担全压给用户。用「色块 + 扩展名文字」标识，
 * 颜色承担第一层识别（PDF 红 / Word 蓝 / 表格绿），文字承担精确确认。
 *
 * 用色块而非彩色图标：彩色 lucide 图标在 15px 尺寸下细节糊成一团，且不同
 * 文件类型的图标轮廓差别很小（FileText 与 FileSpreadsheet 缩到 15px 几乎一样）。
 */

import { kindOf, type FileKind as Kind } from './file-kind'

const KIND_STYLE: Record<Kind, { label: string; cls: string; Icon: typeof FileText }> = {
  pdf: { label: 'PDF', cls: 'bg-status-red/10 text-status-red', Icon: FileText },
  word: { label: 'DOC', cls: 'bg-status-blue/10 text-status-blue', Icon: FileText },
  sheet: { label: 'XLS', cls: 'bg-status-green/10 text-status-green', Icon: FileSpreadsheet },
  image: { label: 'IMG', cls: 'bg-status-purple/10 text-status-purple', Icon: ImageIcon },
  other: { label: 'FILE', cls: 'bg-secondary text-muted-foreground', Icon: FileIcon },
}

/** 紧凑版：列表行用。色块 + 扩展名，21×15 不抢文件名注意力 */
export function FileKindBadge({ name, className }: { name: string; className?: string }) {
  const k = KIND_STYLE[kindOf(name)]
  return (
    <span
      aria-hidden
      className={cn(
        'grid h-[15px] w-[27px] flex-none place-items-center rounded-[3px] text-[8.5px] font-bold tracking-[0.02em]',
        k.cls,
        className,
      )}
    >
      {k.label}
    </span>
  )
}

/** 展开版：预览卡头部用。图标 + 扩展名，信息更完整 */
export function FileKindChip({ name, className }: { name: string; className?: string }) {
  const k = KIND_STYLE[kindOf(name)]
  const Icon = k.Icon
  return (
    <span
      className={cn(
        'inline-flex flex-none items-center gap-1 rounded-[5px] px-1.5 py-0.5 text-[10px] font-[620]',
        k.cls,
        className,
      )}
    >
      <Icon className="size-3" />
      {k.label}
    </span>
  )
}
