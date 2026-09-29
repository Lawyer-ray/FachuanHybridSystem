import { useEffect } from 'react'
import { PANEL } from '../ui'
import { CourtSmsCard } from './tools/CourtSmsCard'
import { DocConvertCard } from './tools/DocConvertCard'
import { DocConverterCard } from './tools/DocConverterCard'
import { DocParseCard } from './tools/DocParseCard'

/**
 * 快捷工具坞：收法院短信 / 要素式转换 / DOC 转 DOCX / 文档解析。
 * 四张卡各自对接真实后端（路径见 tools/ 内各组件的 api 注释），不搞假提交。
 *
 * 文档解析卡接的是后台「文档解析工作台」同一套能力（MinerU / TextinParse / 本地），
 * 把原本只能进 admin 的上传解析搬到首页，律师不必为解析一份文书去登后台。
 */
export function ToolDock() {
  // 全局拦截文件拖放的浏览器默认行为：不接卡的角落拖文件会整页跳到文件预览
  // （表现即「屏幕闪一下」）；卡片各自接管自己范围内的 drop
  useEffect(() => {
    const prevent = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes('Files')) e.preventDefault()
    }
    window.addEventListener('dragover', prevent)
    window.addEventListener('drop', prevent)
    return () => {
      window.removeEventListener('dragover', prevent)
      window.removeEventListener('drop', prevent)
    }
  }, [])

  return (
    <section className={`${PANEL} mt-5 px-4 pb-[18px]`}>
      <div className="flex items-center gap-2.5 py-[13px]">
        <b className="text-[13.5px] font-semibold">快捷工具</b>
        <span className="text-[11px] text-muted-foreground">收案 · 文书 · 解析，不用进后台</span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <CourtSmsCard />
        <DocConvertCard />
        <DocConverterCard />
        <DocParseCard />
      </div>
    </section>
  )
}
