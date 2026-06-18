import { useState } from 'react'
import { ArrowLeft, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DocSpaceFrame,
  DocumentList,
  UploadButton,
  useDocSpaceConfig,
  useDocSpaceDocuments,
} from '@/features/docspace'
import { useCreateDocSpaceDocument } from '@/features/docspace/hooks/use-upload'
import type { DocSpaceDocument } from '@/features/docspace'

export function DocSpaceTool() {
  const { data: config, isLoading: configLoading } = useDocSpaceConfig()
  const { data: documents = [], isLoading: docsLoading } = useDocSpaceDocuments()
  const [activeDoc, setActiveDoc] = useState<DocSpaceDocument | null>(null)
  const createMut = useCreateDocSpaceDocument()

  if (configLoading) {
    return <div className="p-6 text-muted-foreground">加载配置中…</div>
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

  // 编辑器模式
  if (activeDoc) {
    return (
      <div className="flex flex-col h-[calc(100vh-4rem)]">
        <div className="flex items-center gap-3 px-4 py-2 border-b shrink-0">
          <Button variant="ghost" size="sm" onClick={() => setActiveDoc(null)}>
            <ArrowLeft className="h-4 w-4 mr-1" />
            返回列表
          </Button>
          <span className="font-medium truncate">{activeDoc.title}</span>
        </div>
        <div className="flex-1 min-h-0">
          <DocSpaceFrame
            fileId={activeDoc.docspace_file_id}
            editorUrl={activeDoc.web_url}
            onClose={() => setActiveDoc(null)}
            className="h-full"
          />
        </div>
      </div>
    )
  }

  // 列表模式
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">云文档</h1>
          <p className="text-muted-foreground text-sm mt-1">
            在线编辑 Word、Excel、PPT 文档
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => createMut.mutate(undefined, {
              onSuccess: (result) => {
                setActiveDoc({
                  id: result.id,
                  title: result.title,
                  docspace_file_id: result.docspace_file_id,
                  docspace_folder_id: 0,
                  file_ext: result.file_ext,
                  content_length: result.content_length,
                  web_url: result.web_url,
                  created_at: '',
                  updated_at: '',
                })
              },
            })}
            disabled={createMut.isPending}
          >
            <Plus className="h-4 w-4 mr-2" />
            {createMut.isPending ? '创建中…' : '新建文档'}
          </Button>
          <UploadButton />
        </div>
      </div>
      <DocumentList
        documents={documents}
        isLoading={docsLoading}
        onOpen={setActiveDoc}
      />
    </div>
  )
}
