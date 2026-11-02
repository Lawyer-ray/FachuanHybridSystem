/**
 * 合同原文 · 锁定修订（OnlyOffice 渲染）
 *
 * 双语对照卡是**演示用的静态正文**；这一张才是真文件：docx 交给 Document Server
 * 整份渲染，`mode='review'` 锁住编辑但保留修订显示，红删绿增是文档里真实的
 * 修订标记，不是前端画的。
 *
 * 鉴权：DS 容器带不了 `Authorization` 头，所以这里传的是**站内下载路径**，
 * 后端 `editor-config` 会换成 HMAC 签名的代理地址写进 config（与
 * `FilePreview` 同一条链路，见 `components/shared/onlyoffice/api.ts`）。
 */

import { useState } from 'react'
import { Maximize2, Minimize2 } from 'lucide-react'

import { OfficeView } from '@/components/shared/onlyoffice/OfficeView'
import { cn } from '@/lib/utils'

import { Card } from '../../ui'

/** /projects/443 的泰国厂房租赁审查任务（demo-nonlit 里那 9 条正文即此文件） */
const TH_LEASE_TASK_ID = '88a5cc96-58eb-48f5-aaf5-84e698c796d6'
const TH_LEASE_FILE_NAME = 'Factory_Lease_Agreement_TH-CN_v3.docx'

export function ContractOfficeCard() {
  /** 全屏态只抬高度（不接管整屏）：演示时要能同时看到下面的双语对照 */
  const [expanded, setExpanded] = useState(false)

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex items-center gap-2">
        <h3 className="text-[13px] font-[620]">合同原文 · 锁定修订</h3>
        <span className="text-[11px] text-muted-foreground">
          docx 原件 · 修订共 5 处 · 只读
        </span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="ml-auto inline-flex h-[27px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[11.5px] text-secondary-foreground transition-colors hover:bg-secondary"
          title={expanded ? '退出全屏' : '全屏查看'}
        >
          {expanded ? <Minimize2 className="size-3" /> : <Maximize2 className="size-3" />}
          {expanded ? '退出全屏' : '全屏'}
        </button>
      </div>

      <div
        className={cn(
          'mt-3 overflow-hidden rounded-[10px] border border-border-light bg-[#f6f6f7]',
          expanded ? 'h-[calc(100vh-200px)]' : 'h-[620px]',
        )}
      >
        <OfficeView
          fileUrl={`/api/v1/contract-review/${TH_LEASE_TASK_ID}/download`}
          fileName={TH_LEASE_FILE_NAME}
          mode="review"
        />
      </div>
    </Card>
  )
}
