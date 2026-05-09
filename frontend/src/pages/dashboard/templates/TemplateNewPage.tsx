import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { TemplateForm } from '@/features/templates'
import { useTemplateMutations } from '@/features/templates/hooks/use-template-mutations'
import { PATHS } from '@/routes/paths'

export default function TemplateNewPage() {
  const navigate = useNavigate()
  const { create } = useTemplateMutations()

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">新建文件模板</h1>
        <p className="text-muted-foreground text-sm mt-1">
          创建新的法律文书模板，支持上传 .docx 文件或引用模板库路径
        </p>
      </div>
      <TemplateForm
        onSubmit={(data) => {
          create.mutate(data, {
            onSuccess: () => {
              toast.success('模板创建成功')
              navigate(PATHS.ADMIN_TEMPLATES)
            },
            onError: (error) => {
              toast.error(error.message || '创建失败，请重试')
            },
          })
        }}
      />
    </div>
  )
}
