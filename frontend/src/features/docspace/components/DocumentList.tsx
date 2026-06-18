import { FileText, Trash2, Download, RefreshCw, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import type { DocSpaceDocument } from '../types'
import { useDeleteDocSpaceDocument, useSyncDocSpaceDocument } from '../hooks/use-documents'

interface DocumentListProps {
  documents: DocSpaceDocument[]
  isLoading: boolean
  onOpen: (doc: DocSpaceDocument) => void
}

export function DocumentList({ documents, isLoading, onOpen }: DocumentListProps) {
  const deleteMut = useDeleteDocSpaceDocument()
  const syncMut = useSyncDocSpaceDocument()

  if (isLoading) {
    return <div className="text-muted-foreground py-8 text-center">加载中…</div>
  }

  if (documents.length === 0) {
    return (
      <div className="text-muted-foreground py-12 text-center">
        暂无文档，上传一个 .docx 开始编辑
      </div>
    )
  }

  return (
    <div className="grid gap-3">
      {documents.map((doc) => (
        <Card key={doc.id} className="hover:shadow-md transition-shadow">
          <CardContent className="flex items-center gap-4 p-4">
            <FileText className="h-8 w-8 text-blue-500 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{doc.title}</p>
              <p className="text-sm text-muted-foreground">
                {doc.file_ext} · {(doc.content_length / 1024).toFixed(1)} KB ·{' '}
                {new Date(doc.updated_at).toLocaleString()}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button size="sm" onClick={() => onOpen(doc)}>
                <ExternalLink className="h-4 w-4 mr-1" />
                编辑
              </Button>
              <Button
                size="icon"
                variant="ghost"
                title="下载"
                onClick={() => {
                  import('../api').then(({ docspaceApi }) => docspaceApi.downloadDocument(doc.id))
                }}
              >
                <Download className="h-4 w-4" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                title="刷新"
                onClick={() => syncMut.mutate(doc.id)}
                disabled={syncMut.isPending}
              >
                <RefreshCw className={`h-4 w-4 ${syncMut.isPending ? 'animate-spin' : ''}`} />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                title="删除"
                className="text-destructive hover:text-destructive"
                onClick={() => {
                  if (confirm(`确定删除「${doc.title}」？`)) deleteMut.mutate(doc.id)
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
