import { toast } from 'sonner'

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { safeHttpUrl } from '@/lib/url'
import { useContractCases } from '../hooks/use-contract-cases'
import type { WorkbenchDeal } from '../types'

import {
  CasesSection,
  FactsSection,
  MoneySection,
  PartiesSection,
  PaymentsSection,
  RemindersSection,
  SupplementsSection,
  TeamSection,
} from './DealSheetSections'

interface DealSheetProps {
  deal: WorkbenchDeal | null
  /** 开关与 deal 分离：关闭时父组件保留最后一份 deal，让退出动画播完再由 Radix 卸载 */
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 「详情 →」去向：争议解决进详情页；不传（测试）退化为开发中提示 */
  onOpenDetail?: (deal: WorkbenchDeal) => void
}

/**
 * 合同详情抽屉（办案主页唯一浮层）：九节全字段，空节不渲染。
 * 「详情 →」= 各自详情页（争议解决 / 非诉同 onOpenDetail 分流）；当事人/律师行内可复制。
 * 头部只放类型/状态/OA 编号——日期类信息统一在「合同要素」一节，不在头部重复。
 *
 * 八个正文节各自成组件（见 `DealSheetSections`），本组件只负责开关、头部与数据装配。
 */
export function DealSheet({ deal, open, onOpenChange, onOpenDetail }: DealSheetProps) {
  /* 案件明细按需加载：抽屉打开才请求该合同的案件（列表期不拉全量） */
  const { cases, isLoading: casesLoading, error: casesError, refetch: refetchCases } = useContractCases(
    open ? (deal?.id ?? null) : null,
  )
  if (!deal) return null

  /* 右键空白遮罩 = 左键点空白同效：不弹原生菜单，收起抽屉（播退出动画） */
  const closeByContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    onOpenChange(false)
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent overlayProps={{ onContextMenu: closeByContextMenu }}>
        <SheetHeader>
          {/* 详情按钮右浮动进标题流：长案名首行文字自动绕开按钮，不再被盖住；
              flow-root 兜住浮动高度，下方标签行不会钻到按钮下面；mr 对齐右侧 X（54px） */}
          <div className="flow-root">
            <button
              type="button"
              className="-mt-1 float-right ml-3 mr-[30px] h-[30px] rounded-[9px] bg-foreground px-[13px] text-xs font-semibold text-background transition-opacity hover:opacity-85"
              onClick={() => (onOpenDetail && deal ? onOpenDetail(deal) : toast.info('详情页正在开发中'))}
            >
              详情 →
            </button>
            <SheetTitle>{deal.client}</SheetTitle>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11.5px] text-muted-foreground">
            <span className="rounded-full bg-secondary px-[9px] py-0.5 text-[10.5px] font-[550] text-secondary-foreground">
              {deal.ctype}
            </span>
            <span className="rounded-full bg-secondary px-[9px] py-0.5 text-[10.5px] font-[550] text-secondary-foreground">
              {deal.statusLabel}
            </span>
            {deal.no &&
              (deal.oaUrl ? (
                <a
                  href={safeHttpUrl(deal.oaUrl, '#')}
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-3 tabular-nums hover:text-foreground"
                >
                  {deal.no}
                </a>
              ) : (
                <span className="tabular-nums">{deal.no}</span>
              ))}
          </div>
        </SheetHeader>

        <SheetBody>
          <MoneySection deal={deal} />
          <PartiesSection deal={deal} />
          <TeamSection deal={deal} />
          <FactsSection deal={deal} />
          <PaymentsSection deal={deal} />
          <RemindersSection deal={deal} />
          <SupplementsSection deal={deal} />
          <CasesSection
            deal={deal}
            cases={cases}
            isLoading={casesLoading}
            error={casesError}
            onRetry={() => refetchCases()}
          />
        </SheetBody>
      </SheetContent>
    </Sheet>
  )
}
