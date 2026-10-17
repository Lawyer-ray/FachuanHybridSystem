/** 取字 / 选页 顶部提示横条（原型 .pickhint：琥珀底 + Esc 取消/退出）。
 *
 *  退出是一个真按钮而不只是「Esc」文字：手机没有 Esc 键，提示条是选页 / 取字态唯一
 *  显式的退出口；桌面保留 Esc 徽标作为键位提示。文案按断点分两版——⇧+点 / S 键
 *  这些在触屏上不存在，手机版只说"点一下"与"去底部确认"。 */
export function HintBar({
  mode,
  field,
  onExit,
}: {
  mode: 'pick' | 'sel'
  field?: string
  onExit: () => void
}) {
  const pick = mode === 'pick'
  return (
    <div className="flex min-h-[34px] flex-none items-center gap-2.5 border-b border-amber-200 bg-amber-50 px-4 py-1 text-[12px] text-amber-800 max-[760px]:px-3">
      {pick ? (
        <>
          <span className="min-w-0 flex-1 max-[760px]:hidden">
            给「{field || '字段'}」取字：在页面上按住拖一个框 → RapidOCR 识别；只点一下则只记页码
          </span>
          <span className="hidden min-w-0 flex-1 leading-snug max-[760px]:inline">
            给「{field || '字段'}」取字：按住拖框识别，点一下只记页码
          </span>
        </>
      ) : (
        <>
          <span className="min-w-0 flex-1 max-[760px]:hidden">选页：点一张选中，⇧+点 选区间，S 把选中的页合成一份，Esc 退出</span>
          <span className="hidden min-w-0 flex-1 leading-snug max-[760px]:inline">选页：点页面选中，选好后在底部确认</span>
        </>
      )}
      <button
        type="button"
        onClick={onExit}
        className="flex h-[24px] flex-none items-center gap-1 rounded border border-amber-200 bg-white px-2 text-[11px] text-amber-700 transition-colors hover:bg-amber-100"
      >
        <kbd className="font-sans max-[760px]:hidden">Esc</kbd>
        {pick ? '取消' : '退出'}
      </button>
    </div>
  )
}
