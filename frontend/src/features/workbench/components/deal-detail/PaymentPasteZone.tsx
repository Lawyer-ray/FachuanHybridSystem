import { useRef, useState } from 'react'
import { ImageIcon, Loader2, Sparkles, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { fileFromClipboard } from '@/features/home/components/clipboard-file'

/**
 * 记收款弹窗第①节「粘贴到账凭据」：**文字和图片走同一个入口**。
 *
 * 律师手上的凭据一半是银行到账短信（文字），一半是网银 App 的电子回单截图
 * （图片：金额、大写金额、付款人/收款人、完整交易时间都在图上）。只支持文字
 * 等于把后一半逼回手抄——而回单上恰恰有「大写金额」这种专门用来防抄错的字段。
 *
 * 因此这里刻意不做「文字一个框、图片另一个框」：把图**粘到文本框里**是最顺手
 * 的动作（⌘V 之后什么都不用想）。粘贴时若剪贴板里是文件，就拦下来走图片识别；
 * 若只是文字，放行给 Textarea 的默认粘贴。
 *
 * 图片识别结果回填表单后**不留下图片**：这张图只是取字段的中间产物，不当附件
 * 存（要留原件就走下方「发票」区上传，那是正式材料）。
 */
export function PaymentPasteZone({
  raw,
  hints,
  imageName,
  parsing,
  disabled,
  onRawChange,
  onParseText,
  onPickImage,
  onClearImage,
}: {
  raw: string
  hints: string[]
  /** 已选中/已识别的图片名（null = 没有图片挂在输入框上） */
  imageName: string | null
  parsing: boolean
  /** 收款保存后整段禁用（再改字段也不会写库） */
  disabled: boolean
  onRawChange: (v: string) => void
  onParseText: () => void
  onPickImage: (file: File) => void
  onClearImage: () => void
}) {
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  return (
    <section className="border-b border-border-light pb-4">
      <div className="mb-1.5 flex items-baseline gap-2">
        <span className="text-[12px] font-[650]">粘贴到账凭据</span>
        <span className="text-[11px] text-muted-foreground">
          （短信直接粘文字；银行回单截图/PDF 直接 ⌘V 或拖进来）
        </span>
      </div>

      <div
        className={
          'rounded-[10px] border transition-colors ' +
          (dragOver ? 'border-foreground bg-secondary/60' : 'border-transparent')
        }
        onDragOver={(e) => {
          if (disabled) return
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          if (disabled) return
          e.preventDefault()
          setDragOver(false)
          const f = e.dataTransfer.files?.[0]
          if (f) onPickImage(f)
        }}
      >
        <Textarea
          value={raw}
          onChange={(e) => onRawChange(e.target.value)}
          onPaste={(e) => {
            if (disabled) return
            const f = fileFromClipboard(e.clipboardData)
            if (!f) return // 纯文字粘贴：交给 Textarea 默认行为
            e.preventDefault()
            onPickImage(f)
          }}
          placeholder={
            '【建设银行】某某公司10月15日17时5分向贵公司4501账户律师费存入人民币9000元。\n' +
            '或：把网银电子回单截图 ⌘V 粘到这里，自动读金额 / 日期 / 付款人'
          }
          rows={3}
          className="text-[12.5px]"
          disabled={disabled}
        />
      </div>

      {imageName && (
        <div className="mt-1.5 flex items-center gap-1.5 rounded-[6px] bg-secondary/60 px-2 py-1 text-[11.5px]">
          <ImageIcon className="size-3 flex-none text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate" title={imageName}>
            {imageName}
          </span>
          {!disabled && (
            <button
              type="button"
              title="移除这张图"
              aria-label="移除这张图"
              className="flex-none rounded-[4px] p-0.5 text-muted-foreground/70 hover:text-foreground"
              onClick={onClearImage}
            >
              <X className="size-3" />
            </button>
          )}
        </div>
      )}

      <div className="mt-2 flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => fileRef.current?.click()}
          disabled={parsing || disabled}
        >
          {parsing ? <Loader2 className="size-3.5 animate-spin" /> : <ImageIcon className="size-3.5" />}
          选图片
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onParseText}
          disabled={parsing || !raw.trim() || disabled}
        >
          {parsing ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
          识别文字
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            e.target.value = ''
            if (f) onPickImage(f)
          }}
        />
        {hints.length > 0 && (
          <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground" title={hints.join(' · ')}>
            {hints.join(' · ')}
          </span>
        )}
      </div>
    </section>
  )
}
