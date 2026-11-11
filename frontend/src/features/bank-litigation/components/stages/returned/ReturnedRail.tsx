/**
 * 回扫 —— 右栏答疑（这一阶段在解决什么 / 怎么认案 / 认不准怎么办 / 归案之后）。
 *
 * 全是静态说明文案：这一屏为什么存在、系统靠什么认案、低于阈值为什么不硬塞、
 * 归案后还会自动发生什么。没有交互，也没有状态。
 */
import { RailSection, WorkCard } from '../../ui'

/** 回扫右栏 */
export function ReturnedRail() {
  return (
    <WorkCard padded={false}>
      <RailSection title="这一阶段在解决什么">
        <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
          材料回流是散的：快递寄回、行政扫描、法院短信、客户微信。
          律师不该挨个去找「刚才那份传票放哪了」。
          系统扫邮箱、认案号、认当事人，认出来的直接挂到本案。
        </p>
      </RailSection>

      <RailSection title="怎么认案">
        <div className="flex flex-col gap-2 text-[10.5px] leading-[1.6] text-muted-foreground">
          <div>
            <span className="font-medium text-foreground">案号精确匹配</span>
            <div className="mt-0.5">（20XX）粤0106民初XXXX号 → 直接定位到案件</div>
          </div>
          <div>
            <span className="font-medium text-foreground">当事人名 + 案由</span>
            <div className="mt-0.5">「谭某某 金融借款」命中唯一在办案件</div>
          </div>
          <div>
            <span className="font-medium text-foreground">文件名关键词</span>
            <div className="mt-0.5">「不动产权证」「催收记录」按类型归槽</div>
          </div>
        </div>
      </RailSection>

      <RailSection title="认不准怎么办">
        <div className="rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg/60 px-2.5 py-2">
          <div className="text-[11px] font-medium">低于 80% 匹配度不硬塞</div>
          <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
            放进「待处理」让律师定。硬塞错案的代价远大于让律师多点一下。
          </p>
        </div>
      </RailSection>

      <RailSection title="归案之后">
        <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
          <div>→ 自动拆分成单份材料</div>
          <div>→ 自动转 markdown</div>
          <div>→ 重跑缺件检测（见「③ 缺件」）</div>
        </div>
      </RailSection>
    </WorkCard>
  )
}
