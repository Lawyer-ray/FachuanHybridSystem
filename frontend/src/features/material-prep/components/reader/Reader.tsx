import { countUnclassified, matLabel } from '../../draft'
import { ReviewLaunchDrawer } from '@/features/contract-review'
import { FixedReader, ReaderError, ReaderLoading } from './ReaderChrome'
import { ReaderTopBar } from './ReaderTopBar'
import { ReaderToolbar } from './ReaderToolbar'
import { ReaderBody } from './ReaderBody'
import { ReaderDialogs } from './ReaderDialogs'
import { loadDocxBytes, partiesOf } from './use-assign-launch'
import { useReaderScreen } from './use-reader-screen'
import { READER_FILE_ACCEPT } from './ui'

/**
 * 阅读器：阅读器顶层编排。状态、loading/error 分支、三栏布局组合，
 * 具体的 ops / 键位 / 列宽 / 弹窗各自下沉到子模块。
 *
 * 本文件只剩「早返回 + 布局骨架」：20 多个 hook 调用与 props 装配都在
 * use-reader-screen（store 字段在 use-reader-store-fields 按 selector 一次取齐）。
 */
export function Reader() {
  // 逐个解构而不是用 screen.xxx：React Compiler 的 ref 规则会把「含 useRef 的自定义
  // hook 返回值」整体视作 ref 对象，经对象属性读任何字段都会被判成访问 ref。
  const {
    data,
    meta,
    store,
    actions,
    launch,
    readerRef,
    narrow,
    toolbarProps,
    bodyProps,
    pickField,
    ocrOk,
    showAssign,
    renaming,
    setRenaming,
    renameMat,
    setRenameMat,
    setAddInputRef,
    launchFile,
  } = useReaderScreen()
  const { draft, detail, openId, ocrPending } = data

  if (!openId || !detail) return null
  if (meta.status === 'loading') return <ReaderLoading />
  if (meta.status === 'error') return <ReaderError error={meta.error} onBack={store.close} />
  // 草稿未就绪时继续显示骸架，而不是把 null 传给需要 DraftState 的三栏主体。
  // bodyProps.draft / toolbarProps.draft 的类型都是非空 DraftState
  // （use-reader-screen.ts 里用 as DraftState 收窄，依赖的就是这个前置判断）。
  if (!draft) return <ReaderLoading />

  const unclassified = countUnclassified(draft)
  const pages = draft.mats.reduce((s, m) => s + m.pages, 0)
  // 副标题只说必要信息：页数 + 产出份数；源文件数只在多源时出现（单源是常态，不是属性）
  const subtitle = `${pages} 页 · ${draft.segs.length} 份材料${draft.mats.length > 1 ? ` · ${draft.mats.length} 个源文件` : ''}`
  const ocrFrom = ocrPending ? `${matLabel(draft.mats, ocrPending.mi)} P${ocrPending.p}` : ''

  return (
    <FixedReader closing={meta.closing} rootRef={readerRef}>
      <ReaderTopBar
        title={detail.subject || '材料包'}
        subtitle={subtitle}
        unclassified={unclassified}
        tools={<ReaderToolbar {...toolbarProps} narrow={false} inline />}
        onBack={store.close}
        onReject={actions.onReject}
        onAssign={toolbarProps.handleAssign}
        onRename={() => setRenaming(true)}
      />

      {/* 窄于 1100（抽屉布局 / 手机，按阅读器净宽）：工具组独立一行，放不下就横滚 */}
      <div className="hidden @max-[1100px]:block">
        <ReaderToolbar {...toolbarProps} narrow={narrow} />
      </div>

      <ReaderBody {...bodyProps} />

      {/* 追加材料文件选择（input 隐藏，由工具组的「追加」触发） */}
      <input
        ref={setAddInputRef}
        type="file"
        multiple
        accept={READER_FILE_ACCEPT}
        className="hidden"
        onChange={(e) => {
          // 追加（不是替换）：多选后整体交给 store；input 复位以便再次选同一文件
          if (e.target.files?.length) void store.appendFiles(Array.from(e.target.files))
          e.target.value = ''
        }}
      />

      <ReaderDialogs
        draft={draft}
        detail={detail}
        ocrPending={ocrPending}
        ocrFrom={ocrFrom}
        ocrTo={pickField}
        onOcrText={(v) => {
          if (ocrPending) store.setOcrPending({ ...ocrPending, text: v })
        }}
        onOcrRedo={() => store.setOcrPending(null)}
        // 取消取字：清掉待确认 OCR 并复位取字目标（与 HintBar 的退出、Esc 同一口径）
        onOcrCancel={() => {
          store.setOcrPending(null)
          store.setPickInfo(-1)
        }}
        onOcrOk={ocrOk}
        showAssign={showAssign}
        onAssignCancel={() => store.setAssignOpen(false)}
        onAssignConfirm={(a) => void launch.onAssignConfirm(a)}
        deleteTarget={actions.deleteTarget}
        onDeleteCancel={() => actions.setDeleteTarget(null)}
        onDeleteConfirm={actions.confirmDelete}
        renaming={renaming}
        onRenamingChange={setRenaming}
        renameMat={renameMat}
        onRenameMatClose={() => setRenameMat(null)}
      />

      {/* 归案 → 发起审查。抽屉自己负责上传 + 确认立场，完成后通知跳复审台。 */}
      {launchFile && (
        <ReviewLaunchDrawer
          open
          fileName={launchFile}
          loadFile={() => loadDocxBytes(detail.id, draft, launchFile)}
          parties={partiesOf(draft)}
          onClose={launch.onCloseDrawer}
          onStarted={launch.onStarted}
        />
      )}
    </FixedReader>
  )
}
