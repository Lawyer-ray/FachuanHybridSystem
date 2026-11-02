import { ChevronDown } from 'lucide-react'

import { DEMO_BUNDLE_FAQ, DEMO_BUNDLE_RULES } from '../demo-data'
import { SectionTitle, WorkCard } from '../ui'

/**
 * 拆分规则：这一版引擎**按什么拆**、模板怎么选、归案后能不能改名。
 *
 * 为什么要把规则摆到界面上：律师判断「这包能不能直接拆」靠的是这几条
 * （有没有分隔页、是不是二审包），而不是靠猜。规则写在页面上，
 * 出错时他也能自己定位是哪一环没对上。
 */
export function RuleBook() {
  return (
    <WorkCard padded={false}>
      <div className="border-b border-border-light px-5 py-3">
        <SectionTitle title="拆分规则" hint="引擎按什么切开、按什么命名" />
      </div>
      <div className="grid grid-cols-1 gap-x-5 gap-y-0 divide-border-light md:grid-cols-2 md:divide-x">
        {DEMO_BUNDLE_RULES.map((rule) => (
          <div key={rule.title} className="border-b border-border-light px-5 py-3 last:border-b-0">
            <div className="text-[12px] font-medium text-foreground">{rule.title}</div>
            <p className="mt-1 text-[11px] leading-[1.6] text-muted-foreground">{rule.body}</p>
            <div className="mt-1.5 rounded-[6px] border border-border-light bg-background px-2 py-1 text-[10.5px] text-secondary-foreground">
              {rule.example}
            </div>
          </div>
        ))}
      </div>
    </WorkCard>
  )
}

/** 常见问题折叠块：扫描质量、重复页、空白页、超时、耗时 */
export function FaqList() {
  return (
    <WorkCard padded={false}>
      <div className="border-b border-border-light px-5 py-3">
        <SectionTitle title="常见问题" hint="扫描质量与异常页怎么处理" />
      </div>
      <div className="divide-y divide-border-light">
        {DEMO_BUNDLE_FAQ.map((item) => (
          <details key={item.q} className="group px-5 py-2.5">
            <summary className="flex cursor-pointer list-none items-center gap-2 text-[12px] font-medium text-foreground">
              <ChevronDown className="size-3.5 flex-none text-muted-foreground transition-transform group-open:rotate-180" />
              {item.q}
            </summary>
            <p className="mt-1.5 pl-[22px] text-[11px] leading-[1.65] text-muted-foreground">{item.a}</p>
          </details>
        ))}
      </div>
    </WorkCard>
  )
}
