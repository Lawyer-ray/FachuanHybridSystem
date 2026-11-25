/**
 * 「回传后核对内容」勾选框（受控）。
 *
 * 样式与 `AssignModal` 底部「同时归档到案件文件夹」那个勾选逐字对齐——两个勾选项
 * 上下相邻，视觉上必须是同一种东西，否则律师会以为其中一个更重要。
 *
 * 受控而不是自带状态：勾选值既是**本次归案要落库的策略**，也是**律师的偏好**
 * （关掉弹窗再打开不该弹回来）。偏好由 `use-assign-launch` 的模块级变量持有
 * （与归档勾选同一套写法与理由），本组件只渲染与回调，不做读写——这样它能在
 * 单测里独立验证，也不会把偏好偷偷变成两处状态。
 */
export function PolicyToggle({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: (next: boolean) => void
}) {
  return (
    <label className="mt-1.5 flex cursor-pointer items-start gap-2 text-[12.5px]">
      <input
        type="checkbox"
        className="mt-0.5"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        回传后核对内容（起诉状 / 授权委托书 / 送达地址确认书 / 退费账户确认书）
        <span className="mt-0.5 block text-[11.5px] text-muted-foreground">
          勾选的文书在客户回传后自动比对正文（本地算，约 2 秒/份）
        </span>
      </span>
    </label>
  )
}
