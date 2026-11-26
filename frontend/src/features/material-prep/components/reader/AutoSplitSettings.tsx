import { ChevronDown } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { SegmentStrategy } from '../../types'
import { CheckItem } from './CheckItem'
import { PickItem } from './PickItem'
import { costBadges, SPLIT_TIERS, tierOf, type SplitTierId } from './split-plan'
import {
  CLOUD_ENGINES,
  cloudEngineLabel,
  crossChecks,
  type CloudEngine,
  type CloudSelection,
} from './platform-selection'

/**
 * 「自动分段」设置菜单：版面策略 + 解析平台。
 *
 * 从 ReaderToolbar 拆出（工具条本体与设置菜单是两个关注点，合在一起顶过软红线）。
 *
 * ## 为什么每一项都要写后果
 *
 * 这两组选项**直接决定这一包要花多少云端费用**：补版面让电子页也上云（按页计费），
 * 勾两个引擎意味着同一份 PDF 付两次钱。只写名词用户无从判断，所以每项带一句后果，
 * 底部再按勾选数说明当前组合的后果。
 *
 * ## 为什么标注「本包记住」
 *
 * 选择按包持久化（draft.recognition）：律师对「银行流水包开双引擎、电子合同包只抽
 * 文本层」的判断是按包做的，换包不继承、重开同一包保留。新建包默认开双引擎
 * （见 constants.defaultRecognition），所以这里必须给一键关闭的入口。
 */
/**
 * 一个引擎项的副标题。
 *
 * DeepSeek 单独一种说法：它**不参与交叉比对**（后端 `DUAL_ENGINE_CHOICES` 里没有它），
 * 所以不能沿用「再勾一个就比对」那句，否则用户勾了 DeepSeek + MinerU 会以为开了比对。
 */
function engineHintOf(engine: CloudEngine, selection: CloudSelection): string {
  const picked = selection.includes(engine)
  if (engine === 'deepseek') {
    return picked ? '锁定 · 不参与交叉比对' : '取字引擎 · 可单独使用'
  }
  return picked && !crossChecks(selection) ? '锁定 · 失败不降级' : '版面解析 · 可定位'
}

export function AutoSplitSettings({
  disabled,
  layoutMode,
  onLayoutModeChange,
  cloudSelection,
  onToggleCloudEngine,
  onClearCrossCheck,
  onResetSegments,
  segmentStrategy,
  onSegmentStrategyChange,
  judgeOn,
  onToggleJudge,
  onApplyTier,
}: {
  /** 识别进行中禁用：不能改正在跑的策略 */
  disabled: boolean
  layoutMode: 'fast_text' | 'layout'
  onLayoutModeChange: (m: 'fast_text' | 'layout') => void
  cloudSelection: CloudSelection
  onToggleCloudEngine: (e: CloudEngine) => void
  /** 一键关闭交叉比对（回到自动容灾）；选择随包保存 */
  onClearCrossCheck: () => void
  onResetSegments: () => void
  /** 分段策略：决定分段 LLM 调用次数（wholebook_cross 翻倍） */
  segmentStrategy: SegmentStrategy
  onSegmentStrategyChange: (s: SegmentStrategy) => void
  /** 分歧自动裁定：只在 ≥2 个可比对引擎时有事可做 */
  judgeOn: boolean
  onToggleJudge: () => void
  /** 应用一档成本预设（一次性设引擎 / 分段策略 / 判定） */
  onApplyTier: (id: SplitTierId) => void
}) {
  const activeTier = tierOf({ engines: cloudSelection, segmentStrategy, judge: judgeOn })
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="自动分段设置"
          title="自动分段设置：版面策略 / 解析平台（按包记住）"
          disabled={disabled}
          className="flex w-[26px] items-center justify-center rounded-r-[6px] border border-l-0 border-input text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[300px]">
        {/* ── 简易：按成本选 ──
            放在最上面是因为绝大多数律师只需要回答一个问题：「这一包值得花多少钱」。
            每档都把两笔账分开写（取字几遍 / 分段几遍），合成一个"费用倍数"会误导。 */}
        <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
          简易 · 按成本选
          {activeTier === null && <span className="ml-1 text-[10.5px]">（已自定义）</span>}
        </DropdownMenuLabel>
        {SPLIT_TIERS.map((tier) => (
          <PickItem
            key={tier.id}
            checked={activeTier === tier.id}
            onSelect={() => onApplyTier(tier.id)}
            label={`${tier.label} · ${costBadges(tier)}`}
            hint={tier.hint}
          />
        ))}

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
          高级 · 逐项设置
        </DropdownMenuLabel>
        <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
          版面策略（本包记住）
        </DropdownMenuLabel>
        <PickItem
          checked={layoutMode === 'fast_text'}
          onSelect={() => onLayoutModeChange('fast_text')}
          label="仅文本层"
          hint="电子版不上云 · 最快 · 无坐标与结构"
        />
        <PickItem
          checked={layoutMode === 'layout'}
          onSelect={() => onLayoutModeChange('layout')}
          label="补版面"
          hint="电子页也送云端：更准但更慢更贵（按页计费）"
        />

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
          解析平台（本包记住）
        </DropdownMenuLabel>
        {/* 多选而不是单选：律师要能自己勾「同时用哪几个引擎」，勾两个就交叉比对。
            「自动容灾」不做成菜单项——它是**没勾任何引擎时的后果**，做成可勾项
            会和勾选状态互相打架（勾了自动又勾 MinerU 算什么）。 */}
        {CLOUD_ENGINES.map((e) => (
          <CheckItem
            key={e}
            checked={cloudSelection.includes(e)}
            onToggle={() => onToggleCloudEngine(e)}
            label={cloudEngineLabel(e)}
            hint={engineHintOf(e, cloudSelection)}
          />
        ))}
        {/* 新建包默认双引擎，所以「关掉」必须一步可达：勾掉两个引擎要两次点击，
            而多付一次云端费用这件事不该让人找开关 */}
        {crossChecks(cloudSelection) && (
          <DropdownMenuItem onSelect={onClearCrossCheck} className="text-[12.5px]">
            关闭交叉比对（回到自动容灾）
          </DropdownMenuItem>
        )}
        {/* 底部说明随勾选数变。三态缺一不可：勾两个时以前这里直接返回 null，
            于是最需要提示的那一态反而什么都没有——用户看不到「要交叉比对」这个后果，
            更看不到它会**再付一次云端费用**。 */}
        {crossChecks(cloudSelection) ? (
          <>
            <p className="px-2 pb-1 pt-0.5 text-[11px] leading-4 text-muted-foreground">
              已选 {cloudSelection.length} 个引擎 → 将交叉比对（多付一次云端费用）
            </p>
            <p className="px-2 pb-1 text-[11px] leading-4 text-muted-foreground">
              换来的是「两个引擎读得不一样」的错字清单；不需要就一键关闭，选择随包保存。
            </p>
          </>
        ) : cloudSelection.length === 0 ? (
          <p className="px-2 pb-1 pt-0.5 text-[11px] leading-4 text-muted-foreground">
            不勾任何引擎 = 自动容灾（首选失败自动切下一个）
          </p>
        ) : cloudSelection.some((e) => e === 'deepseek') && cloudSelection.length === 1 ? (
          <p className="px-2 pb-1 pt-0.5 text-[11px] leading-4 text-muted-foreground">
            仅 DeepSeek 取字：读得更准（旋转页也不读反），但约 1/5 的页会整页崩，需靠单页重试救回
          </p>
        ) : (
          <p className="px-2 pb-1 pt-0.5 text-[11px] leading-4 text-muted-foreground">
            只勾一个 = 锁定该引擎，不比对 · 再勾一个可交叉比对
          </p>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
          分段策略（本包记住）
        </DropdownMenuLabel>
        <PickItem
          checked={segmentStrategy === 'batch'}
          onSelect={() => onSegmentStrategyChange('batch')}
          label="分批摘要"
          hint="稳 · 大卷宗不会撞 LLM 超时 · 看得不全，可能把两份并成一份"
        />
        <PickItem
          checked={segmentStrategy === 'wholebook'}
          onSelect={() => onSegmentStrategyChange('wholebook')}
          label="整本一次"
          hint="边界更准 · 大卷宗可能超时，失败会自动退回分批"
        />
        <PickItem
          checked={segmentStrategy === 'wholebook_cross'}
          onSelect={() => onSegmentStrategyChange('wholebook_cross')}
          label="两种都跑"
          hint="最准 · 切法不一致的段标出来交人工 · 分段调用翻倍"
        />

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
          分歧处理（本包记住）
        </DropdownMenuLabel>
        <CheckItem
          checked={judgeOn}
          onToggle={onToggleJudge}
          label="分歧自动裁定"
          hint={
            judgeOn
              ? '两个引擎读得不一样时打分裁定；判不了才进人工'
              : '分歧全部进人工清单，不自动定任何一条'
          }
        />
        {/* 判定只在双引擎分歧上跑：单引擎时开着也是空转。不偷偷关掉用户的开关，
            但必须把这个后果说出来——否则「开了却没反应」会被当成坏了。 */}
        {judgeOn && !crossChecks(cloudSelection) && (
          <p className="px-2 pb-1 text-[11px] leading-4 text-muted-foreground">
            当前只勾了不到两个可比对引擎：不会有分歧可判，这一项暂时是空转
          </p>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onResetSegments} className="text-[12.5px]">
          恢复初始分段
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
