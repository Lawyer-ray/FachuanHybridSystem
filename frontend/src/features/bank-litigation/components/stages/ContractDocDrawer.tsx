/**
 * ④ 文书 —— 单份委托材料的预览抽屉
 *
 * 点开一份文书，看的是「系统到底填了什么」：生成方式、条款填充值、正文占位。
 * 条款的逐条编辑在 `ContractTermsCard` 那一条链上（合同抽屉里不放两份编辑入口）。
 */

import { DEMO_CONTRACT_GEN, DEMO_CONTRACT_TERMS } from '../demo-data'
import { ActionButton, InsetBlock, Pill } from '../ui'
import { DetailDrawer } from './DetailDrawer'

export function DocDrawer({ name, onClose }: { name: string | null; onClose: () => void }) {
  const doc = name ? DEMO_CONTRACT_GEN.find((d) => d.name === name) : null
  const terms = name === '民事委托代理合同' ? DEMO_CONTRACT_TERMS : []

  return (
    <DetailDrawer
      open={doc != null}
      onClose={onClose}
      width={560}
      title={doc?.name ?? ''}
      subtitle={doc ? `${doc.pages} 页 · ${doc.source}` : undefined}
      badge={doc ? <Pill tone={doc.status === 'generated' ? 'green' : 'yellow'}>{doc.status === 'generated' ? '已生成' : '待生成'}</Pill> : null}
      footer={
        doc ? (
          <>
            <ActionButton dark onClick={onClose}>
              下载 docx
            </ActionButton>
            <ActionButton onClick={onClose}>发给当事人签署</ActionButton>
          </>
        ) : null
      }
    >
      {doc ? (
        <div className="flex flex-col gap-3">
          <InsetBlock className="bg-secondary/25">
            <div className="text-[10px] text-muted-foreground">生成方式</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">{doc.source}</p>
          </InsetBlock>

          {terms.length > 0 ? (
            <div>
              <div className="mb-1.5 text-[10.5px] text-muted-foreground">
                填充的条款（逐条改在「委托合同条款逐条审核」那张卡）
              </div>
              <div className="flex flex-col divide-y divide-border-light">
                {terms.map((t) => (
                  <div key={t.clause} className="flex items-center gap-2 py-1.5">
                    <span className="w-[70px] flex-none text-[11px] text-muted-foreground">{t.clause}</span>
                    <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium" title={t.value}>
                      {t.value}
                    </span>
                    <Pill tone={t.filled ? 'green' : 'yellow'}>{t.filled ? '已填' : '待定'}</Pill>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <InsetBlock>
            <div className="text-[10px] text-muted-foreground">正文预览</div>
            <div className="mt-2 grid aspect-[3/4] place-items-center rounded-[4px] border border-border-light bg-secondary/30">
              <span className="text-[10.5px] text-muted-foreground">（docx 预览）</span>
            </div>
          </InsetBlock>
        </div>
      ) : null}
    </DetailDrawer>
  )
}
