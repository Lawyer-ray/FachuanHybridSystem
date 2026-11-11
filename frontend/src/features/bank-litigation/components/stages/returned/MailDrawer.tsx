/**
 * 回扫 —— 邮件详情抽屉。
 *
 * 点开一封邮件看得见：发件人、匹配到哪个案、靠什么匹配的、处理结果，
 * 以及附件（点一行就地预览）。底部三个动作：指定归属（低匹配度那封才有）、
 * 改归其他案件、标记为无关。
 *
 * 「哪封打开着」「哪些标了无关」是页面级状态（列表行会跟着变），所以由面板持有。
 */
import { DEMO_RETURNED_MAILS, DEMO_X2_MAIL_ATTACHMENTS } from '../../demo-data'
import { ActionButton, InsetBlock, KeyValueRow, Pill } from '../../ui'
import { DetailDrawer } from '../DetailDrawer'
import { AttachmentRow } from './AttachmentRow'
import { claimKindOf } from './claim-kind'

/** 邮件详情：附件可点开预览、匹配依据、可改归属 */
export function MailDrawer({
  subject,
  onClose,
  ignored,
  onIgnore,
  onAssign,
}: {
  subject: string | null
  onClose: () => void
  ignored: Set<string>
  onIgnore: (subject: string) => void
  onAssign: (subject: string) => void
}) {
  const raw = subject ? DEMO_RETURNED_MAILS.find((x) => x.subject === subject) : null
  const m = raw && ignored.has(raw.subject) ? { ...raw, action: '已标记无关' } : raw
  const kind = m ? claimKindOf(m.action) : 'manual'
  const files = m ? DEMO_X2_MAIL_ATTACHMENTS.filter((a) => a.subject === m.subject) : []

  return (
    <DetailDrawer
      open={m != null}
      onClose={onClose}
      title={m?.subject ?? ''}
      subtitle={m ? `${m.from} · ${m.attachments} 个附件 · ${m.at}` : undefined}
      badge={
        m ? (
          <Pill tone={kind === 'auto' ? 'green' : kind === 'ignored' ? 'neutral' : 'yellow'}>
            {kind === 'auto' ? '已自动归案' : kind === 'ignored' ? '已标记无关' : '待人工'}
          </Pill>
        ) : null
      }
      footer={
        m ? (
          <>
            {kind === 'manual' ? (
              <ActionButton dark onClick={() => onAssign(m.subject)}>
                指定归属
              </ActionButton>
            ) : (
              <ActionButton dark onClick={onClose}>
                确认归属
              </ActionButton>
            )}
            <ActionButton onClick={onClose}>改归其他案件</ActionButton>
            <ActionButton onClick={() => onIgnore(m.subject)} disabled={kind === 'ignored'}>
              标记为无关
            </ActionButton>
          </>
        ) : null
      }
    >
      {m ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="发件人">{m.from}</KeyValueRow>
            <KeyValueRow label="匹配案件">{m.matchedCase}</KeyValueRow>
            <KeyValueRow label="匹配依据">{m.matchedBy}</KeyValueRow>
            <KeyValueRow label="处理结果">{m.action}</KeyValueRow>
          </dl>

          <InsetBlock>
            <div className="text-[10px] text-muted-foreground">附件（{m.attachments}）· 点一行看预览</div>
            <div className="mt-1.5 flex flex-col gap-1">
              {files.length > 0 ? (
                files.map((f) => <AttachmentRow key={f.name} attachment={f} />)
              ) : (
                Array.from({ length: m.attachments }).map((_, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="size-3 rounded-[2px] bg-secondary" />
                    <span className="min-w-0 flex-1 truncate">附件_{i + 1}.pdf</span>
                    <span className="text-[10px] text-muted-foreground">{(1.2 + i * 0.4).toFixed(1)} MB</span>
                  </div>
                ))
              )}
            </div>
          </InsetBlock>

          {kind === 'manual' ? (
            <InsetBlock className="border-status-yellow/40 bg-status-yellow-bg/60">
              <div className="text-[10.5px] font-medium">匹配度低于阈值</div>
              <p className="mt-1 text-[10.5px] leading-[1.65] text-muted-foreground">
                系统没法确定这封邮件属于哪个案子，放进了待处理。硬塞错案的代价远大于让律师多点一下。
              </p>
            </InsetBlock>
          ) : null}
        </div>
      ) : null}
    </DetailDrawer>
  )
}
