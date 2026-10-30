import { Link2, Loader2, PackagePlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { PREP_STAGES, type PrepStage } from '../stages'
import { DemoButton } from './DemoButton'

/**
 * 预处理页头部：一级阶段页签（收件箱 / 待处理 / 已归案 / 不接归档）+ 右侧全局动作。
 *
 * 动作区固定在页签**之上**的公共头部、四个阶段下都可见：上传即建包，
 * 新包落在「待处理」，所以它在收件箱阶段同样成立。把动作收拢到这一处，
 * 让「新建」不再需要挂在全局 navbar 上弹一句「去别的地方做」。
 */
export function DeskTabs({
  stage,
  setStage,
  counts,
  uploading,
  onPickFiles,
  onOpenShareLinks,
}: {
  stage: PrepStage
  setStage: (s: PrepStage) => void
  counts: Record<PrepStage, number>
  uploading: boolean
  onPickFiles: () => void
  onOpenShareLinks: () => void
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end gap-4">
      <div className="flex items-center gap-1.5">
        <div className="flex items-center gap-0.5 rounded-[9px] bg-secondary p-[3px]">
          {PREP_STAGES.map((t) => (
            <button
              key={t.key}
              type="button"
              data-testid={`prep-stage-${t.key}`}
              onClick={() => setStage(t.key)}
              className={cn(
                'flex items-center gap-[6px] rounded-[7px] px-[13px] py-[6px] text-[13px] transition-colors',
                stage === t.key
                  ? 'bg-card font-medium text-foreground shadow-sm'
                  : 'text-secondary-foreground hover:text-foreground',
              )}
            >
              {t.label}
              <span
                className={cn(
                  'text-[11.5px] tabular-nums',
                  stage === t.key ? 'text-secondary-foreground' : 'text-muted-foreground',
                )}
              >
                {counts[t.key]}
              </span>
            </button>
          ))}
        </div>
        <span className="mx-2 hidden h-[18px] w-px bg-zinc-300 sm:block" />
        <span className="hidden text-[11.5px] text-muted-foreground sm:inline">全部材料都靠手划，机器不猜</span>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <Button onClick={onOpenShareLinks} size="sm" variant="outline">
          <Link2 className="h-4 w-4" />
          客户链接
        </Button>
        {/* 演示：一键铺好演示数据（建合同/案件/当事人 + 整包 PDF 进收件箱）。
            放在「新建材料包」左边 —— 两者语义同类（都是往系统送一包材料），
            演示的这包是准备好的。 */}
        <DemoButton />
        <Button onClick={onPickFiles} disabled={uploading} size="sm">
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" />}
          新建材料包
        </Button>
      </div>
    </div>
  )
}
