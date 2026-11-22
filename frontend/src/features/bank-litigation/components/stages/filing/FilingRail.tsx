/**
 * ⑥ 校验的右栏：一卡六段（照 `ContractRail` / `ReturnedRail` 的结构）。
 *
 * 右栏只回答「为什么这样设计」：为什么最后才查签章、机器到底查什么、
 * 三处金额怎么算一致、一键修正改哪些、通知为什么分两阶段、以及
 * 「真正的提交不在这里」。左列是可操作的表，右列是口径说明。
 */

import { AlertTriangle } from 'lucide-react'

import { RailSection, WorkCard } from '../../ui'

export function FilingRail({ diffCount }: { diffCount: number }) {
  return (
    <WorkCard padded={false}>
      <RailSection title="为什么最后才查签章">
        <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
          签章是**不可逆**的一步。前面材料不齐可以补、金额错了可以改，
          但盖了章签了字再发现不对，就要重新走一遍签署流程。
          所以放在送法院之前的最后一关。
        </p>
      </RailSection>

      <RailSection title="这台机器查什么">
        <div className="flex flex-col gap-2 text-[10.5px] leading-[1.6] text-muted-foreground">
          <div>
            <span className="font-medium text-foreground">印章</span>
            <div className="mt-0.5">识别印章图像，比对类型（公章/法代章/财务章）与位置</div>
          </div>
          <div>
            <span className="font-medium text-foreground">签名</span>
            <div className="mt-0.5">检测签名区域是否有笔迹，空白页会直接标红</div>
          </div>
          <div>
            <span className="font-medium text-foreground">骑缝</span>
            <div className="mt-0.5">核对骑缝章是否覆盖全部附件页</div>
          </div>
        </div>
      </RailSection>

      <RailSection title="三处金额怎么算一致">
        <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
          <div>→ 起诉状定稿 = 基准，不改</div>
          <div>→ 立案表单按基准重算，回读比对</div>
          <div>→ 要素式由起诉状转换，天然同源</div>
          <div className="text-status-yellow">→ 口径不同（360/365 天）会差几毛几分</div>
        </div>
      </RailSection>

      <RailSection title="一键修正会改什么">
        <div className="rounded-[8px] border border-border-light bg-background px-2.5 py-2">
          <div className="text-[10.5px] font-medium text-secondary-foreground">
            {diffCount} 项字段变更，先看 diff 才执行
          </div>
          <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
            改的是立案表单与要素式，起诉状定稿一张不改。
            签章那 2 项不在自动范围里。
          </p>
        </div>
      </RailSection>

      <RailSection title="通知是两阶段的">
        <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
          <div>→ 发出 ≠ 送达，送达 ≠ 已读</div>
          <div>→ 站内待办回「已读」才算律师看到了</div>
          <div>→ 短信只到「已发送」，没有回执</div>
        </div>
      </RailSection>

      <RailSection title="一张网那一步">
        <div className="rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg/60 px-2.5 py-2">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-[1px] size-3 flex-none text-status-yellow" />
            <p className="text-[10.5px] leading-[1.6] text-muted-foreground">
              本页只负责「能不能去」。真正提交在「一张网立案」页，
              由律师本人点击 —— 提交即对法院作出意思表示。
            </p>
          </div>
        </div>
      </RailSection>
    </WorkCard>
  )
}
