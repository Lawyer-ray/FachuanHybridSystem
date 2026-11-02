/**
 * ④ 文书 —— 右栏说明
 *
 * 这一栏不讲新东西，讲的是「为什么这么排」：卡点、利冲先于立案、
 * 条款改到哪一步、换了模板的文书、三档判定、什么时候签。
 * 从 ContractPanel 抽出来是因为面板本身已经到 350 行软红线。
 */

import { Bot } from 'lucide-react'

import { InsetBlock, Pill, RailSection, WorkCard } from '../ui'

export function ContractRail({
  termCount,
  pendingTerms,
  customTemplates,
}: {
  /** 条款总条数 */
  termCount: number
  /** 律师还没定的条数（自动填充标「待定」且没改过） */
  pendingTerms: number
  /** 非 v3.2 的模板选择：文书名 → 模板 id */
  customTemplates: [string, string][]
}) {
  return (
    <WorkCard padded={false}>
      <RailSection title="当前卡点">
        <div className="rounded-[8px] border border-status-red/40 bg-status-red-bg/60 px-2.5 py-2">
          <div className="text-[11.5px] font-medium text-status-red">利冲未通过，OA 立案已停</div>
          <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
            共同借款人李某某与本所在办离婚案当事人为同一人（证件号一致）。
            需由主任律师判定是否属于禁止性冲突。
          </p>
        </div>
      </RailSection>

      <RailSection title="先查利冲再看立案">
        <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
          利冲必须在建卷之前。先建了卷再发现冲突，撤销要走审批；
          而冲突本身可能意味着这个委托根本不能接。
        </p>
      </RailSection>

      <RailSection title="条款改到哪一步">
        <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
          <div>→ 自动填充 {termCount} 条，{pendingTerms} 条律师没定</div>
          <div>→ 改过的标「已修改」，原文仍可对照</div>
          <div>→ 全部确认后才能发给当事人签署</div>
        </div>
      </RailSection>

      <RailSection title="换了模板的文书">
        {customTemplates.length === 0 ? (
          <p className="text-[10.5px] leading-[1.6] text-muted-foreground">
            全部按 v3.2 生成。风险代理类案件改用 v2.8，自定义模板需管理员审核。
          </p>
        ) : (
          <div className="flex flex-col gap-1">
            {customTemplates.map(([name, tpl]) => (
              <div key={name} className="flex items-center gap-2 text-[10.5px]">
                <span className="min-w-0 flex-1 truncate text-muted-foreground">{name}</span>
                <Pill tone="blue">{tpl === 'custom' ? '自定义' : tpl}</Pill>
              </div>
            ))}
          </div>
        )}
      </RailSection>

      <RailSection title="三档判定">
        <div className="flex flex-col gap-2">
          <div>
            <Pill tone="red">红色</Pill>
            <div className="mt-1 text-[10.5px] leading-[1.55] text-muted-foreground">
              同名且证件号相同 —— 同一人在对方阵营，必须停
            </div>
          </div>
          <div>
            <Pill tone="yellow">黄色</Pill>
            <div className="mt-1 text-[10.5px] leading-[1.55] text-muted-foreground">
              同名但证件号不同 —— 疑似重名，律师复核
            </div>
          </div>
          <div>
            <Pill tone="green">无冲突</Pill>
            <div className="mt-1 text-[10.5px] leading-[1.55] text-muted-foreground">
              无命中，或仅历史已结案记录
            </div>
          </div>
        </div>
      </RailSection>

      <RailSection title="文书什么时候签">
        <InsetBlock>
          <div className="flex items-start gap-2">
            <Bot className="mt-[1px] size-3.5 flex-none text-muted-foreground" />
            <p className="text-[10.5px] leading-[1.65] text-muted-foreground">
              生成的委托合同需要律师核对后定稿，再由当事人签署。
              利冲未通过前不建议发出签署。
            </p>
          </div>
        </InsetBlock>
      </RailSection>
    </WorkCard>
  )
}
