/**
 * ① 收案的右栏：当前进度 / 下一步 / 识别口径。
 *
 * 右栏只讲「现在到哪了、还差什么、按什么口径判的」，不放可操作的表。
 */

import { Pill, RailSection, WorkCard } from '../../ui'

/** 已剔除的源文件个数会实时反映到进度里 */
export function IntakeRail({ droppedCount }: { droppedCount: number }) {
  return (
        <WorkCard padded={false}>
      <RailSection title="当前进度">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-[11.5px]">
            <span className="text-muted-foreground">拆分</span>
            <Pill tone="green">已完成</Pill>
          </div>
          <div className="flex items-center justify-between text-[11.5px]">
            <span className="text-muted-foreground">归入本案</span>
            <Pill tone="green">8 份已归</Pill>
          </div>
          <div className="flex items-center justify-between text-[11.5px]">
            <span className="text-muted-foreground">待人工核对</span>
            <Pill tone="yellow">2 份</Pill>
          </div>
          <div className="flex items-center justify-between text-[11.5px]">
            <span className="text-muted-foreground">已剔除源文件</span>
            <Pill tone={droppedCount ? 'yellow' : 'neutral'}>{droppedCount} 个</Pill>
          </div>
        </div>
      </RailSection>

      <RailSection title="下一步">
        <div className="rounded-[8px] border border-status-blue/40 bg-status-blue-bg/60 px-2.5 py-2">
          <div className="text-[11.5px] font-medium">需要你确认 2 处</div>
          <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
            差额补足承诺函落款被印章遮盖；手写便签疑非案件材料。
            确认后才能进入「读懂」阶段。
          </p>
        </div>
      </RailSection>

      <RailSection title="识别口径">
        <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
          按每页内容判断材料类型，不按文件名猜。
          认不准的标「待核对」，完全认不出的标「未识别」—— 都不会被硬塞进某个类型。
          每一份的置信度都能点开看是哪几个因子撑起来的。
        </p>
      </RailSection>
    </WorkCard>
  )
}
