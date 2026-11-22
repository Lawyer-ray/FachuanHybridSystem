import { Button } from '@/components/ui/button'

import { FixedReader } from './FixedReader'

/** 打开失败：错误文案 + 返回（关闭阅读器） */
export function ReaderError({ error, onBack }: { error: string; onBack: () => void }) {
  return (
    <FixedReader>
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm">
        <p className="text-destructive">{error}</p>
        <Button onClick={onBack}>返回</Button>
      </div>
    </FixedReader>
  )
}
