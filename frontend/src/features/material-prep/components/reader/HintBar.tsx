/** 取字 / 选页 顶部提示横条（原型 .pickhint：琥珀底 + Esc 取消/退出） */
export function HintBar({
  mode,
  field,
}: {
  mode: 'pick' | 'sel'
  field?: string
}) {
  return (
    <div className="flex h-[34px] flex-none items-center gap-2.5 border-b border-amber-200 bg-amber-50 px-4 text-[12px] text-amber-800">
      {mode === 'pick' ? (
        <>
          <span>
            给「{field || '字段'}」取字：在页面上按住拖一个框 → RapidOCR 识别；只点一下则只记页码
          </span>
          <span className="flex-1" />
          <span className="rounded border border-amber-200 bg-white px-1.5 py-px text-[11px] text-amber-700">Esc 取消</span>
        </>
      ) : (
        <>
          <span>选页：点一张选中，⇧+点 选区间，S 把选中的页合成一份，Esc 退出</span>
          <span className="flex-1" />
          <span className="rounded border border-amber-200 bg-white px-1.5 py-px text-[11px] text-amber-700">Esc 退出</span>
        </>
      )}
    </div>
  )
}
