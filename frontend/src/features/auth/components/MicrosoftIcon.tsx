/**
 * 微软四色窗口标（官方 Microsoft logo 几何）。
 *
 * 内联 SVG 而非外部图片：与 GitHubIcon 同理，登录页不依赖可能加载失败的外链。
 * 四色落在浅底上（配套 `.fc-btn--brand` 的白底），黄铜底上不可辨。
 */
export function MicrosoftIcon({ size = 18 }: { size?: number }) {
  return (
    <svg viewBox="0 0 23 23" width={size} height={size} aria-hidden="true" focusable="false">
      <path fill="#F25022" d="M1 1h10v10H1z" />
      <path fill="#7FBA00" d="M12 1h10v10H12z" />
      <path fill="#00A4EF" d="M1 12h10v10H1z" />
      <path fill="#FFB900" d="M12 12h10v10H12z" />
    </svg>
  )
}
