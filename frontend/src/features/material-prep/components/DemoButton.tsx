import { useState } from 'react'
import { useNavigate } from 'react-router'
import { Loader2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import { DEMO_SCENARIOS, fetchDemoPdf, resetDemoData, seedDemoScenario, type DemoScenario } from '../demo-api'
import { uploadPack } from '../api'

/**
 * 「演示」按钮 —— 一键铺好场景 2 的演示环境。
 *
 * ═══ 它做完什么、留下什么 ═══
 * 做完（机械操作，没人想看）：
 *   · 建合同 + 案件 + 当事人 + 主办律师
 *   · 把整包 PDF 传进收件箱（生成一个材料包）
 * 留下（需要判断，正是要演示的）：
 *   · 自动分段 → 复核低置信度 → 确认归案
 *   · 起诉条件校验 → 要素式转换 → OA/一张网立案 → 盖章归档
 *
 * ═══ 为什么放在 material-prep 页 ═══
 * 材料预处理是整条链路的入口：律师拿到整包的第一步就在这里。
 * 演示按钮贴着「新建材料包」放，语义一致 —— 都是「往系统里送一包材料」，
 * 区别只是演示的这包是准备好的。
 */
export function DemoButton() {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const navigate = useNavigate()

  async function run(sc: DemoScenario) {
    setBusy(sc.key)
    try {
      // ① 先清空上一轮演示 —— 让「演示」可重复，每次都是干净的初始态。
      //    不清的话点几次就有几套同名案件/材料包，演示现场分不清讲哪个。
      toast.loading('正在重置演示数据…', { id: 'demo' })
      const cleared = await resetDemoData()
      if (cleared.cases || cleared.packs) {
        toast.loading(
          `已清理上一轮（${cleared.cases} 件案件 / ${cleared.packs} 个材料包）`,
          { id: 'demo' },
        )
      }

      // ② 建数据
      toast.loading('正在准备演示数据…', { id: 'demo' })
      const { caseId } = await seedDemoScenario(sc)

      // ③ 整包 PDF 进收件箱
      toast.loading('正在上传演示材料…', { id: 'demo' })
      const file = await fetchDemoPdf(sc)
      // subject 决定材料包卡片上显示什么标题。不传的话后端会给一个
      // 默认的「前端材料预处理上传材料」—— 演示时看不出这是哪个案子。
      await uploadPack([file], `${sc.title} · ${file.name}`)

      toast.success('演示数据已就绪', { id: 'demo', duration: 4000 })
      setOpen(false)

      // ④ 跳到材料预处理，让律师接着操作（分段 → 归案 → 立案）
      //    用 navigate 而不是 window.location：保住 React 状态，切换无闪白。
      void navigate(`/material-prep?stage=todo&demoCase=${caseId}`)
    } catch (e) {
      toast.error(`演示数据准备失败：${errMessage(e)}`, { id: 'demo', duration: 6000 })
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Sparkles className="h-4 w-4" />
        演示
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-[560px]">
          <DialogHeader>
            <DialogTitle>选择演示场景</DialogTitle>
            <DialogDescription>
              每次点击都会**先清空上一轮演示数据**，再新建一套（合同 / 案件 / 当事人）
              并把整包 PDF 传进收件箱。你已有的真实案件与材料包不会被改动。
            </DialogDescription>
          </DialogHeader>

          <div className="mt-2 flex flex-col gap-2">
            {DEMO_SCENARIOS.map((sc) => (
              <button
                key={sc.key}
                type="button"
                disabled={busy !== null}
                onClick={() => void run(sc)}
                className={cn(
                  'flex flex-col gap-1 rounded-[9px] border border-border px-3.5 py-3 text-left transition-colors',
                  busy === null ? 'hover:border-foreground/30 hover:bg-secondary/50' : 'opacity-60',
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-[13.5px] font-medium">{sc.title}</span>
                  {busy === sc.key ? (
                    <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
                  ) : null}
                </div>
                <span className="text-[11.5px] leading-[1.6] text-muted-foreground">{sc.point}</span>
              </button>
            ))}
          </div>

          <p className="mt-1 text-[10.5px] leading-[1.6] text-muted-foreground">
            演示数据全部虚构（当事人、证件号、地址均为示例）。重复点击会重置到干净初始态，
            不会越点越多。
          </p>
        </DialogContent>
      </Dialog>
    </>
  )
}
