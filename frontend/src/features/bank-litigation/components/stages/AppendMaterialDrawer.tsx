/**
 * 追加材料：客户链接 / 本地上传 / 邮箱拉取 三个入口
 *
 * 只做入口与预览，不真拉取。之所以要有这个弹窗而不是直接放三个按钮：
 * 三条来源拿到的清单不一样（链接里是客户刚传的、邮箱里是近 7 天命中的），
 * 律师选渠道时就要看到「这次能补到哪些」，否则点了才知道要不要补。
 */

import { InsetBlock, Pill } from '../ui'
import { useState } from 'react'

import { DEMO_X1_APPEND_CHANNELS } from '../demo-data'
import { ActionButton } from '../ui'
import { cn } from '@/lib/utils'
import { DetailDrawer } from './DetailDrawer'

export function AppendMaterialDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [channel, setChannel] = useState<'link' | 'upload' | 'mail'>('link')
  const current = DEMO_X1_APPEND_CHANNELS.find((c) => c.key === channel)

  return (
    <DetailDrawer
      open={open}
      onClose={onClose}
      width={520}
      title="追加材料"
      subtitle="补齐后自动拆分、归入本案，不覆盖已有材料"
      footer={
        <>
          <ActionButton dark onClick={onClose}>
            开始拉取
          </ActionButton>
          <ActionButton onClick={onClose}>取消</ActionButton>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {/* 来源选择 */}
        <div className="grid grid-cols-3 gap-2">
          {DEMO_X1_APPEND_CHANNELS.map((c) => {
            const active = c.key === channel
            return (
              <button
                key={c.key}
                type="button"
                onClick={() => setChannel(c.key)}
                aria-pressed={active}
                className={cn(
                  'rounded-[9px] border px-2.5 py-2 text-left transition-colors',
                  active
                    ? 'border-foreground bg-secondary/60'
                    : 'border-border-light bg-card hover:border-input hover:bg-secondary/40',
                )}
              >
                <div className="text-[11.5px] font-medium">{c.name}</div>
                <div className="mt-0.5 text-[10px] leading-[1.5] text-muted-foreground">{c.desc}</div>
              </button>
            )
          })}
        </div>

        <InsetBlock>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11.5px] font-medium">{current?.name}</span>
            <Pill tone="blue">{current?.detail}</Pill>
          </div>

          {current && current.items.length > 0 ? (
            <ul className="mt-2 flex flex-col gap-1">
              {current.items.map((it) => (
                <li key={it} className="flex items-start gap-1.5 text-[11px] leading-[1.6]">
                  <span className="mt-[3px] size-1.5 flex-none rounded-full bg-status-blue" />
                  <span className="min-w-0 flex-1">{it}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[10.5px] leading-[1.65] text-muted-foreground">
              点「开始拉取」后选文件。选中的文件会先合并进整包，再重走一遍拆分与识别。
            </p>
          )}
        </InsetBlock>

        <InsetBlock className="border-status-blue/40 bg-status-blue-bg/50">
          <div className="text-[10.5px] leading-[1.65] text-muted-foreground">
            追加的材料走与首次收案完全相同的流水线：合并 → 逐页提取 → 切分 → 认类型，
            不会因为「补传」就跳过识别直接归案。
          </div>
        </InsetBlock>
      </div>
    </DetailDrawer>
  )
}
