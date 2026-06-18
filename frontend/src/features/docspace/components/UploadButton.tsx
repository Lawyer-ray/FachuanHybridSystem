import { useRef } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useUploadDocSpace } from '../hooks/use-upload'

interface UploadButtonProps {
  folderId?: number
}

export function UploadButton({ folderId }: UploadButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const uploadMut = useUploadDocSpace()

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    uploadMut.mutate(
      { file, folderId },
      {
        onSuccess: () => {
          if (inputRef.current) inputRef.current.value = ''
        },
      },
    )
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".docx,.doc,.xlsx,.xls,.pptx,.ppt,.pdf"
        className="hidden"
        onChange={handleChange}
      />
      <Button onClick={() => inputRef.current?.click()} disabled={uploadMut.isPending}>
        <Upload className="h-4 w-4 mr-2" />
        {uploadMut.isPending ? '上传中…' : '上传文档'}
      </Button>
      {uploadMut.isError && (
        <p className="text-sm text-destructive mt-1">上传失败: {uploadMut.error.message}</p>
      )}
    </>
  )
}
