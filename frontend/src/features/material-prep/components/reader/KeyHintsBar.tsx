import { CheckCircle2 } from 'lucide-react'

/** 底栏：键位提示 + 归类进度（原型 rd-keys） */
export function KeyHintsBar({ allClassified, unclassified }: { allClassified: boolean; unclassified: number }) {
  return (
    <div className="flex h-[42px] flex-none items-center gap-3 border-t border-border bg-card px-4 text-[12px] text-muted-foreground">
      <span>点页间「在此切开」 = 切开</span>
      <span className="hidden sm:inline">
        <b>⌘</b> 点页 选页 · <b>⌘⇧</b> 选区间 · <b>S</b> 合并
      </span>
      <span className="ml-auto flex items-center gap-1.5">
        {allClassified ? (
          <>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <span className="text-green-700">全部已归类，可以归案了</span>
          </>
        ) : (
          <span className="text-amber-700">还有 {unclassified} 段没归类</span>
        )}
        <span className="mx-1 h-3 w-px bg-zinc-300" />
        <span>Esc 逐级退出</span>
      </span>
    </div>
  )
}
