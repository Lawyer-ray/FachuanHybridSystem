/**
 * 全屏拖放层：拖文件进来时显示「松手即新建」遮罩，并承载隐藏的 file input。
 * fileInputRef 由 DeskPage 持有，各处「选文件」按钮都通过它触发点击。
 */
export function DeskDropLayer({
  dragging,
  fileInputRef,
  onFiles,
}: {
  dragging: boolean
  fileInputRef: React.RefObject<HTMLInputElement | null>
  onFiles: (files: FileList | null) => void
}) {
  return (
    <>
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-foreground/20 backdrop-blur-[1px]">
          <div className="rounded-2xl border border-primary bg-card px-10 py-8 text-center shadow-xl">
            <p className="text-lg font-medium">松手即新建材料包</p>
            <p className="mt-1 text-sm text-secondary-foreground">PDF · Word · 图片 · 视频，混着来都行</p>
          </div>
        </div>
      )}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          onFiles(e.target.files)
          e.target.value = ''
        }}
      />
    </>
  )
}
