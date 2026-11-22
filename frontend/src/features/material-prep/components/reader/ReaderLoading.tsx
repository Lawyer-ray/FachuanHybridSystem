import { Loader2 } from 'lucide-react'

import { FixedReader } from './FixedReader'

/** 打开中：解析页数（detail 已到、draft 未就绪） */
export function ReaderLoading() {
  return (
    <FixedReader>
      <div className="flex flex-1 items-center justify-center gap-2 text-sm text-secondary-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> 正在打开材料包，解析页数…
      </div>
    </FixedReader>
  )
}
