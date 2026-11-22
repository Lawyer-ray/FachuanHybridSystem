/**
 * ② 读懂的右栏：为什么先转 markdown / 转换方法 / 质量标记 / 与后续阶段的关系。
 *
 * 右栏只讲口径，不放可操作的东西 —— 与方法清单共用 `METHOD_HINT`，
 * 避免文档卡上的方法说明与右栏的方法说明各写一份。
 */

import { Pill, RailSection, WorkCard } from '../../ui'
import { METHOD_HINT } from './convert-methods'

export function UnderstandRail() {
  return (
    <WorkCard padded={false}>
      <RailSection title="为什么先转 markdown">
        <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
          律师看的、AI 读的、后续抽字段用的，必须是**同一份正文**。
          如果三处各读各的，就会出现「AI 说合同写了 5%，律师看是 6%」这种扯不清的事。
        </p>
      </RailSection>

      <RailSection title="转换方法">
        <div className="flex flex-col gap-2">
          {Object.entries(METHOD_HINT).map(([k, v]) => (
            <div key={k}>
              <div className="text-[11.5px] font-medium">{k}</div>
              <div className="mt-0.5 text-[10.5px] leading-[1.55] text-muted-foreground">{v}</div>
            </div>
          ))}
        </div>
      </RailSection>

      <RailSection title="质量标记">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <Pill tone="green">高保真</Pill>
            <span className="text-[10.5px] text-muted-foreground">可直接用于抽取</span>
          </div>
          <div className="flex items-center gap-2">
            <Pill tone="yellow">需复核</Pill>
            <span className="text-[10.5px] text-muted-foreground">表格错行/字迹模糊</span>
          </div>
        </div>
      </RailSection>

      <RailSection title="与后续阶段的关系">
        <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
          <div>→ 缺件检测：拿正文里的类型与日期判断</div>
          <div>→ 委托合同生成：抽当事人/标的/管辖填模板</div>
          <div>→ 起诉条件：核合同条款、利率、逾期天数</div>
        </div>
      </RailSection>
    </WorkCard>
  )
}
