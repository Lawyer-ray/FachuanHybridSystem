/**
 * 要素式转换面板里的**三张只读展示卡**：转换统计 + 文书类型库、转换内容映射、
 * 转换前后对比。
 *
 * 为什么从 DocConvertPanel 拆出去：那三张卡渲染的全是 `DEMO_CONVERT_*` 里写死的
 * 演示数据，**不带任何 props、不接任何回调、不参与转换流程**；而 DocConvertPanel
 * 剩下的部分是「选类型 → 选文件 → 请求后端 → 下载」的真实操作编排（含 mbid 自动
 * 匹配 effect、busy/error/done 三态）。两类关注点混在一个文件里，读的人分不清
 * 哪段代码会真的影响转换结果——拆开后一眼可见：这个文件里的东西一个字节都不会
 * 进后端请求。
 *
 * 视觉口径来自 `../ui`（按 deal-detail 的四层手法复刻），className 与拆分前逐字一致。
 */
import { cn } from '@/lib/utils'

import {
  DEMO_CONVERT_MAPPING_DETAIL,
  DEMO_CONVERT_PREVIEW,
  DEMO_CONVERT_STATS,
  DEMO_CONVERT_TEMPLATES,
} from '../demo-data'
import { Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'

/** 转换统计 + 文书类型库：一卡两段，铺满内容区宽度 */
export function ConvertOverviewCard() {
  return (
    <WorkCard padded={false}>
      <RailSection title="转换统计" action={<Pill tone="green">本月失败 {DEMO_CONVERT_STATS.failed} 次</Pill>}>
        <StatStrip className="grid-cols-2 sm:grid-cols-4">
          <StatCell label="累计转换" value={`${DEMO_CONVERT_STATS.total.toLocaleString('en-US')} 次`} />
          <StatCell label="本月转换" value={`${DEMO_CONVERT_STATS.monthly} 次`} tone="blue" />
          <StatCell label="平均耗时" value={`${DEMO_CONVERT_STATS.avgMs.toLocaleString('en-US')} ms`} />
          <StatCell
            label="失败率"
            value={`${DEMO_CONVERT_STATS.failRate}%`}
            tone={DEMO_CONVERT_STATS.failRate > 5 ? 'red' : 'yellow'}
          />
        </StatStrip>
        <p className="mt-2 text-[10.5px] leading-[1.6] text-muted-foreground">
          失败集中在原文件格式不支持（扫描件无文字层）与后端开关未开两种情况，重试前先确认这两项。
        </p>
      </RailSection>

      <RailSection
        title="文书类型库"
        action={<span className="text-[10.5px] text-muted-foreground">共 {DEMO_CONVERT_TEMPLATES.length} 类 · 按本月用量排序</span>}
      >
        <div className="grid grid-cols-[76px_minmax(0,1fr)_140px_64px_56px] gap-2 border-b border-border-light pb-1 text-[10px] text-muted-foreground">
          <span>mbid</span>
          <span>文书名称</span>
          <span>适用案由</span>
          <span>模板版本</span>
          <span className="text-right">本月</span>
        </div>
        <ul className="divide-y divide-border-light">
          {DEMO_CONVERT_TEMPLATES.map((t) => (
            <li key={t.mbid} className="grid grid-cols-[76px_minmax(0,1fr)_140px_64px_56px] items-center gap-2 py-[6px]">
              <span className="truncate font-mono text-[10.5px] text-muted-foreground" title={t.mbid}>
                {t.mbid}
              </span>
              <span className="min-w-0 truncate text-[11.5px]" title={t.name}>
                {t.name}
              </span>
              <span className="min-w-0 truncate text-[11px] text-muted-foreground" title={t.cause}>
                {t.cause}
              </span>
              <span className="text-[11px] tabular-nums text-secondary-foreground">{t.version}</span>
              <span className="text-right text-[11.5px] font-medium tabular-nums">{t.monthly}</span>
            </li>
          ))}
        </ul>
      </RailSection>
    </WorkCard>
  )
}

/** 转换内容：传统字段 → 要素式栏位的映射清单（右栏，全演示数据） */
export function MappingDetailCard() {
  return (
    <WorkCard padded={false}>
      <div className="border-b border-border-light px-5 py-3">
        <SectionTitle
          title="转换内容"
          hint={`传统字段 → 要素式栏位 · ${DEMO_CONVERT_MAPPING_DETAIL.length} 项`}
        />
      </div>
      <ul className="divide-y divide-border-light">
        {DEMO_CONVERT_MAPPING_DETAIL.map((m) => (
          <li key={m.from} className="px-5 py-[7px]">
            <div className="flex items-center gap-2">
              <span className="w-[64px] flex-none text-[11.5px] text-secondary-foreground">{m.from}</span>
              <span className="flex-none text-[10px] text-border">→</span>
              <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground" title={m.to}>
                {m.to}
              </span>
              <span
                className={cn(
                  'flex-none text-[9.5px] font-semibold',
                  m.required ? 'text-status-red' : 'text-muted-foreground/70',
                )}
              >
                {m.required ? '必填' : '选填'}
              </span>
            </div>
            <div className="mt-[3px] truncate pl-[74px] text-[10px] text-muted-foreground" title={m.sample}>
              例：{m.sample}
            </div>
          </li>
        ))}
      </ul>
    </WorkCard>
  )
}

/** 转换前后对比：左传统起诉状摘要 vs 右要素式摘要（含底部脚注） */
export function BeforeAfterCard() {
  return (
    <WorkCard padded={false}>
      <div className="border-b border-border-light px-5 py-3">
        <SectionTitle title="转换前后对比" hint="同一段事实，两种写法 · 预览已脱敏" />
      </div>
      <div className="grid grid-cols-1 gap-[18px] px-5 py-3.5 lg:grid-cols-2">
        {[true, false].map((legacySide) => (
          <div key={legacySide ? 'legacy' : 'elemental'} className="flex min-w-0 flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-[650] tracking-[0.06em] text-muted-foreground/80">
                {legacySide ? '传统起诉状' : '要素式示范文本'}
              </span>
              <Pill tone={legacySide ? 'neutral' : 'blue'}>{legacySide ? '原稿' : '转换结果'}</Pill>
            </div>
            <ul className="flex flex-col gap-1.5">
              {DEMO_CONVERT_PREVIEW.map((p) => (
                <li key={p.label} className="rounded-[9px] border border-border-light bg-background px-3 py-2">
                  <div className="flex items-baseline gap-2">
                    <span className="text-[10px] font-medium text-muted-foreground">{p.label}</span>
                    {!p.matched && !legacySide ? (
                      <span className="text-[9px] font-semibold text-status-blue">要素式新增</span>
                    ) : null}
                    {!p.matched && legacySide ? (
                      <span className="text-[9px] text-muted-foreground/70">原稿无此栏</span>
                    ) : null}
                  </div>
                  <p
                    className={cn(
                      'mt-1 whitespace-pre-line text-[11px] leading-[1.65]',
                      p.matched ? 'text-secondary-foreground' : 'text-muted-foreground/70',
                    )}
                  >
                    {legacySide ? p.legacy : p.elemental}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-border-light px-5 py-2.5 text-[10.5px] leading-[1.6] text-muted-foreground">
        转换只做<b className="font-medium text-secondary-foreground">栏位重组与格式规整</b>
        ，不改写事实表述 —— 新增的两栏（利息计算方式、是否同意调解）在传统起诉状里没有对应内容，
        转换后会留空并标黄，需律师补填后再递交。
      </div>
    </WorkCard>
  )
}
