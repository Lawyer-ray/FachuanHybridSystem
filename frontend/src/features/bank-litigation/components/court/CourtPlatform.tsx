import { InsetBlock, KeyValueRow, RailSection, WorkCard } from '../ui'

import { DEMO_COURT_CHECK_RULES, DEMO_COURT_PLATFORM } from '../demo-data'

/**
 * 法院平台信息 + 校验规则口径。
 *
 * 两块放同一张卡：都是「递交前要读一遍」的背景知识，
 * 分开成两张卡反而会把视线从递交按钮上拉走。
 *
 * 平台信息里的电话/地址只到街道级 —— 真实值应在法院配置里，
 * 演示态写成占位即可（pre-commit 隐私闸门的要求）。
 */
export function CourtPlatform() {
  const p = DEMO_COURT_PLATFORM

  return (
    <WorkCard padded={false}>
      <RailSection title="法院平台信息">
        <InsetBlock>
          <dl className="divide-y divide-border-light">
            <KeyValueRow label="法院名称">
              <span className="block truncate" title={p.courtName}>
                {p.courtName}
              </span>
            </KeyValueRow>
            <KeyValueRow label="立案窗口">
              <span>{p.filingChamber}</span>
            </KeyValueRow>
            <KeyValueRow label="立案庭电话">
              <span className="tabular-nums">{p.phone}</span>
            </KeyValueRow>
            <KeyValueRow label="工作时间">
              <span>{p.workTime}</span>
            </KeyValueRow>
            <KeyValueRow label="网上立案">
              <span>{p.onlineChannel}</span>
            </KeyValueRow>
            <KeyValueRow label="法院地址">
              <span className="block truncate" title={p.address}>
                {p.address}
              </span>
            </KeyValueRow>
          </dl>
        </InsetBlock>

        <ol className="mt-2.5 flex flex-col gap-1.5">
          {p.notices.map((n, i) => (
            <li key={n} className="flex items-start gap-2 text-[11px] leading-[1.55] text-secondary-foreground">
              <span className="mt-[1px] grid size-[15px] flex-none place-items-center rounded-[4px] bg-secondary text-[9.5px] font-semibold tabular-nums text-muted-foreground">
                {i + 1}
              </span>
              {n}
            </li>
          ))}
        </ol>
      </RailSection>

      <RailSection title="校验规则口径">
        <div className="flex flex-col gap-2">
          {DEMO_COURT_CHECK_RULES.map((r) => (
            <div
              key={r.id}
              className="rounded-[8px] border border-border-light bg-background px-2.5 py-2"
            >
              <div className="flex items-center gap-1.5">
                <span className="text-[11.5px] font-semibold">{r.title}</span>
                <span className="ml-auto text-[10px] text-muted-foreground">
                  {r.onFail === 'block' ? '不一致则阻断递交' : '不一致仅提示'}
                </span>
              </div>
              <div className="mt-1 text-[10.5px] leading-[1.5] text-muted-foreground">
                <span className="text-secondary-foreground">比对项：{r.fields}</span>
              </div>
              <p className="mt-0.5 text-[10.5px] leading-[1.55] text-muted-foreground">{r.rule}</p>
            </div>
          ))}
        </div>
      </RailSection>
    </WorkCard>
  )
}
