import { useDocSpaceConfig } from '@/features/docspace'

export function DocSpaceTool() {
  const { data: config, isLoading } = useDocSpaceConfig()

  if (isLoading) {
    return <div className="p-6 text-muted-foreground">加载中…</div>
  }

  if (!config?.enabled) {
    return (
      <div className="p-6 text-center text-muted-foreground">
        <p className="text-lg mb-2">DocSpace 未启用</p>
        <p className="text-sm">
          请在系统设置 → DocSpace 配置中填写 Portal URL 和 API Token
        </p>
      </div>
    )
  }

  return (
    <iframe
      src={`${config.portal_url}/`}
      style={{ width: '100%', height: 'calc(100vh - 4rem)', border: 'none' }}
      title="DocSpace 云文档"
    />
  )
}
