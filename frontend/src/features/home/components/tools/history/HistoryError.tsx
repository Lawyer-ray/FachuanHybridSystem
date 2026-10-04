/**
 * 历史弹窗共用的「加载失败」行：错误文案 + 重试按钮。
 * 四张工具卡的历史弹窗（解析 / 要素式转换 / DOC 转 DOCX / 法院短信）同构复用——
 * 此前列表查询失败会静默渲染成空列表，用户会把服务端故障误读成「没有历史记录」。
 * 样式与各弹窗的空态文案行同款（px-4 py-8 居中小字），仅色用 destructive。
 */
export function HistoryError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="px-4 py-8 text-center text-[12px] text-destructive">
      {error}
      <button type="button" className="ml-2 cursor-pointer underline underline-offset-3" onClick={onRetry}>
        重试
      </button>
    </div>
  )
}
