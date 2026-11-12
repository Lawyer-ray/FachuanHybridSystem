/**
 * ③ 缺件 —— 缺件详情抽屉。
 *
 * 能看完整沟通时间线、判定依据、改等级、单独重发、或判定不用补（忽略）。
 * 忽略是演示态：判定过的项在标题胶囊上标「已忽略」，数据本身不动。
 */
import { DEMO_GAP_NOTICES } from '../../demo-data'
import { ActionButton, InsetBlock, KeyValueRow, Pill } from '../../ui'
import { DetailDrawer } from '../DetailDrawer'

import { sourceOf } from './gap-utils'
import { GapTimelineBlock } from './GapTimelineBlock'

/** 缺件详情：能看完整沟通时间线、判定依据、改等级、单独重发、或判定不用补 */
export function GapDrawer({
  item,
  onClose,
  dismissed,
  onDismiss,
}: {
  item: string | null
  onClose: () => void
  dismissed: Set<string>
  onDismiss: (item: string) => void
}) {
  const g = item ? DEMO_GAP_NOTICES.find((x) => x.item === item) : null
  const isDismissed = g ? dismissed.has(g.item) : false

  return (
    <DetailDrawer
      open={g != null}
      onClose={onClose}
      title={g?.item ?? ''}
      subtitle={
        g ? `${g.severity === 'blocker' ? '硬阻塞' : '一般'} · ${sourceOf(g.item)} · ${g.channel} · ${g.sentAt}` : undefined
      }
      badge={
        g ? (
          <Pill tone={isDismissed ? 'neutral' : g.status === 'received' ? 'green' : g.status === 'pending' ? 'yellow' : 'red'}>
            {isDismissed ? '已忽略' : g.status === 'received' ? '已补齐' : g.status === 'pending' ? '已发出' : '等待客户'}
          </Pill>
        ) : null
      }
      footer={
        g ? (
          <>
            <ActionButton dark onClick={onClose}>
              重新发送通知
            </ActionButton>
            <ActionButton onClick={() => onDismiss(g.item)}>判定不用补</ActionButton>
          </>
        ) : null
      }
    >
      {g ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="缺件原因">{g.reason}</KeyValueRow>
            <KeyValueRow label="等级">
              <span className={g.severity === 'blocker' ? 'text-status-red' : 'text-muted-foreground'}>
                {g.severity === 'blocker' ? '硬阻塞 —— 不补齐无法送法院' : '一般 —— 不影响先立案'}
              </span>
            </KeyValueRow>
            <KeyValueRow label="来源">{sourceOf(g.item)}</KeyValueRow>
            <KeyValueRow label="通知渠道">{g.channel}</KeyValueRow>
            <KeyValueRow label="发出时间">{g.sentAt}</KeyValueRow>
            <KeyValueRow label="客户回复">{g.reply}</KeyValueRow>
          </dl>

          {/* 客户往来时间线：这一条缺件的完整沟通过程 */}
          <GapTimelineBlock item={g.item} />

          <InsetBlock className="bg-secondary/25">
            <div className="text-[10px] text-muted-foreground">系统判定依据</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">
              {g.severity === 'blocker'
                ? '这项材料属于「借贷类必备清单」中的必需项。信源比对时在已转换的 markdown 正文里没找到对应内容，且该清单项在合同条款中明确要求提供。'
                : '这项材料不在必备清单里，但同类案件基本都会提交。缺失不会导致立案被拒，但可能在审理中被法官要求补充。'}
            </p>
          </InsetBlock>

          <InsetBlock>
            <div className="text-[10px] text-muted-foreground">发给客户的话术</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">
              【{g.severity === 'blocker' ? '影响立案的缺件' : '建议补充的材料'}】
              您好，关于「{g.item}」还需要补充：{g.reason}。
              请点此链接上传（免登录）：https://…/u/xxxx 或直接微信发给经办律师。
            </p>
          </InsetBlock>
        </div>
      ) : null}
    </DetailDrawer>
  )
}
