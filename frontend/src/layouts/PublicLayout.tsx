import { Outlet } from 'react-router'

/**
 * 公开页面布局
 * 用于首页、关于页等无需登录的公开页面
 * 始终使用深色背景，不受明暗模式影响
 */
export function PublicLayout() {
  return (
    <div className="min-h-screen bg-gray-950">
      <Outlet />
    </div>
  )
}
