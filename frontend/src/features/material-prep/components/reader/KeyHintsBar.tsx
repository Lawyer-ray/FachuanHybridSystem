import { CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** 底栏：键位提示 + 归类进度（原型 rd-keys）。
 *
 *  手机（≤760px）没有键盘：藏掉全部键位提示，只留归类状态，并把「完成拆分与归类」
 *  主按钮放到这里——底部拇指区最顺手，也不用在工具条里横滚去找。 */
export function KeyHintsBar({
  allClassified,
  unclassified,
  onComplete,
}: {
  allClassified: boolean
  unclassified: number
  onComplete: () => void
}) {
  return (
    <div className="flex h-[42px] flex-none items-center gap-3 border-t border-border bg-card px-4 text-[12px] text-muted-foreground max-[760px]:h-[54px] max-[760px]:px-3">
      <span className="max-[760px]:hidden">点页间「在此切开」 = 切开</span>
      <span className="hidden sm:inline max-[760px]:hidden">
        <b>⌘</b> 点页 选页 · <b>⌘⇧</b> 选区间 · <b>S</b> 合并
      </span>
      <span className="ml-auto flex min-w-0 items-center gap-1.5 max-[760px]:ml-0 max-[760px]:flex-1">
        {allClassified ? (
          <>
            <CheckCircle2 className="h-4 w-4 flex-none text-green-600" />
            <span className="truncate text-green-700">全部已归类，可以归案了</span>
          </>
        ) : (
          <span className="truncate text-amber-700">还有 {unclassified} 段没归类</span>
        )}
        <span className="mx-1 h-3 w-px bg-zinc-300 max-[760px]:hidden" />
        <span className="max-[760px]:hidden">Esc 逐级退出</span>
      </span>
      <Button size="sm" className="flex-none min-[761px]:hidden" onClick={onComplete}>
        <CheckCircle2 className="h-4 w-4" />
        完成拆分与归类
      </Button>
    </div>
  )
}
