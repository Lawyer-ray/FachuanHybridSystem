import { PANEL } from '../ui'
import { CourtSmsCard } from './tools/CourtSmsCard'
import { DocConvertCard } from './tools/DocConvertCard'
import { DocConverterCard } from './tools/DocConverterCard'
import { LprCard } from './tools/LprCard'

/**
 * 快捷工具坞：收法院短信 / 要素式转换 / DOC 转 DOCX / LPR 计息。
 * 四张卡各自对接真实后端（路径见 tools/ 内各组件的 api 注释），不搞假提交。
 */
export function ToolDock() {
  return (
    <section className={`${PANEL} mt-5 px-4 pb-[18px]`}>
      <div className="flex items-center gap-2.5 py-[13px]">
        <b className="text-[13.5px] font-semibold">快捷工具</b>
        <span className="text-[11px] text-muted-foreground">收案 · 文书 · 计息，不用进后台</span>
        <span className="flex-1" />
        <span className="rounded-[7px] px-[9px] py-[3px] text-[11px] text-muted-foreground">全部工具 →</span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <CourtSmsCard />
        <DocConvertCard />
        <DocConverterCard />
        <LprCard />
      </div>
    </section>
  )
}
