/**
 * ③ 缺件 —— 右栏（现在卡在哪 / 客户怎么补 / 补件到位后）。
 *
 * 右栏只回答三件事：卡点是什么、客户该怎么补、补齐之后会自动发生什么。
 * 「催办这 2 项」带自己的执行态，所以整栏自己持有催办动作。
 */
import { RailSection, ActionButton, WorkCard } from '../../ui'
import { useStageAction } from '../use-stage-action'

/** 缺件右栏 */
export function GapRail({ blockerOpen }: { blockerOpen: number }) {
  /* 催办：给还没补的项再发一次 */
  const remind = useStageAction({
    steps: [
      { text: '统计仍未补齐项：2 项', ms: 320 },
      { text: '发送催办短信（含免登录上传链接）', ms: 480 },
      { text: '同步通知主办律师', ms: 280 },
    ],
    toSummary: () => '已向客户发送催办提醒，2 项待补',
  })

  return (
    <WorkCard padded={false}>
      <RailSection title="现在卡在哪">
        {blockerOpen > 0 ? (
          <div className="rounded-[8px] border border-status-red/40 bg-status-red-bg/60 px-2.5 py-2">
            <div className="text-[11.5px] font-medium text-status-red">还有 {blockerOpen} 项硬阻塞未补齐</div>
            <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              抵押物权属证明与共同借款人身份证明未到位，
              这两项不齐无法确认抵押关系与共同债务，诉讼请求会缺依据。
            </p>
            <div className="mt-2">
              <ActionButton sm dark disabled={remind.phase === 'running'} onClick={() => void remind.execute()}>
                {remind.phase === 'running' ? '发送中…' : '催办这 2 项'}
              </ActionButton>
            </div>
            {remind.phase === 'done' ? (
              <div className="mt-1.5 text-[10.5px] text-status-green">{remind.summary}</div>
            ) : null}
          </div>
        ) : (
          <div className="rounded-[8px] border border-status-green/40 bg-status-green-bg/60 px-2.5 py-2">
            <div className="text-[11.5px] font-medium text-status-green">硬阻塞项已全部补齐</div>
          </div>
        )}
      </RailSection>

      <RailSection title="客户怎么补">
        <div className="flex flex-col gap-2 text-[10.5px] leading-[1.65] text-muted-foreground">
          <div>
            <span className="font-medium text-foreground">1. 点链接直接传</span>
            <div className="mt-0.5">短信里的链接免登录，链接本身即凭证，客户手机拍完就传。</div>
          </div>
          <div>
            <span className="font-medium text-foreground">2. 微信发文件</span>
            <div className="mt-0.5">收到的文件系统会自动识别属于哪个案件、放进哪个槽位。</div>
          </div>
          <div>
            <span className="font-medium text-foreground">3. 纸质邮寄</span>
            <div className="mt-0.5">寄回后行政扫描，系统扫邮箱自动归案（见「⑤ 回扫」）。</div>
          </div>
        </div>
      </RailSection>

      <RailSection title="补件到位后">
        <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
          <div>→ 自动重新校验缺件清单</div>
          <div>→ 硬阻塞清零后解锁「④ 文书」阶段</div>
          <div>→ 客户会收到「已收妥」回执</div>
        </div>
      </RailSection>
    </WorkCard>
  )
}
