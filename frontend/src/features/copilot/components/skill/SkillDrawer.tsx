/**
 * 技能抽屉外壳：tab 栏 / 配额条 / 列表三态 / 编辑器二级视图 / 两个确认框。
 *
 * 开关从 `../skill-drawer` 读（会话侧栏的「技能」按钮与 `/` 菜单的
 * `manage-skills` 命令都写同一个 store），所以本组件不接 props。
 *
 * 本文件只做**装配**：取数、tab、草稿脏标记与确认框的判断都在
 * `use-skill-drawer-state`（有未保存改动时 Sheet 的 Esc / 遮罩关闭会绕过编辑器的
 * 取消按钮，那套判断写错一次就会丢草稿，必须只有一处）；tab 可见性与配额口径在
 * `skill-tabs.ts`（纯函数，可单测）。
 *
 * 三个二级视图互斥，优先级：编辑器 → 审核面板 → 列表。提审对话框独立于这三者
 * （它是弹窗，不占抽屉版面，所以能在列表之上叠一层而不改变抽屉自己的状态机）。
 */

import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { Sheet, SheetBody, SheetContent } from '@/components/ui/sheet'

import { SkillDrawerHeader } from './SkillDrawerHeader'
import { SkillEditor } from './SkillEditor'
import { SkillList } from './SkillList'
import { SkillPromoteDialog } from './SkillPromoteDialog'
import { SkillQuotaBar } from './SkillQuotaBar'
import { SkillReviewPanel } from './SkillReviewPanel'
import { SkillTabs } from './SkillTabs'
import { useSkillDrawerState } from './use-skill-drawer-state'

export function SkillDrawer() {
  const drawer = useSkillDrawerState()

  return (
    <Sheet
      open={drawer.open}
      onOpenChange={(next) => {
        if (!next) drawer.requestClose()
      }}
    >
      <SheetContent className="max-w-[min(620px,calc(100vw-1.75rem))]">
        <SkillDrawerHeader />

        <SheetBody className="px-6 pt-4">
          {drawer.editor ? (
            <SkillEditor
              target={drawer.editor}
              onClose={drawer.closeEditor}
              onDirtyChange={drawer.setEditorDirty}
              onSaved={drawer.handleSaved}
            />
          ) : drawer.reviewTarget ? (
            <SkillReviewPanel
              skill={drawer.reviewTarget}
              onClose={drawer.closeReview}
              onReviewed={drawer.handleReviewed}
            />
          ) : (
            <>
              <SkillTabs
                skills={drawer.skills}
                quota={drawer.quota}
                active={drawer.activeTab}
                onChange={drawer.setTab}
              />
              <SkillQuotaBar tab={drawer.activeTab} cell={drawer.tabQuota} />

              {drawer.skillsLoading ? (
                <LoadingBlock size="sm" />
              ) : drawer.skillsError ? (
                <ErrorBlock
                  error={drawer.skillsErrorObject}
                  fallback="技能清单加载失败"
                  onRetry={drawer.refetchSkills}
                />
              ) : (
                <SkillList
                  tab={drawer.activeTab}
                  skills={drawer.tabSkills}
                  busyKey={drawer.busyKey}
                  contendedNames={drawer.contendedNames}
                  tabQuota={drawer.tabQuota}
                  createScope={drawer.createScope}
                  onCreate={drawer.openCreate}
                  onEdit={drawer.openEdit}
                  onDelete={drawer.setDeleteTarget}
                  onDuplicate={drawer.handleDuplicate}
                  onToggle={drawer.handleToggle}
                  onReview={drawer.openReview}
                  onPromote={drawer.openPromote}
                />
              )}
            </>
          )}
        </SheetBody>
      </SheetContent>

      <SkillPromoteDialog
        skill={drawer.promoteTarget}
        onOpenChange={(next) => {
          if (!next) drawer.closePromote()
        }}
        onPromoted={drawer.handlePromoted}
      />

      <ConfirmDialog
        open={drawer.confirmClose}
        onOpenChange={(next) => {
          if (!next) drawer.setConfirmClose(false)
        }}
        title="放弃未保存的修改？"
        description="关掉之后，这次填写的内容不会保留。"
        confirmText="放弃修改"
        cancelText="继续编辑"
        tone="destructive"
        onConfirm={() => {
          drawer.setConfirmClose(false)
          drawer.closeAll()
        }}
      />

      <ConfirmDialog
        open={drawer.deleteTarget !== null}
        onOpenChange={(next) => {
          if (!next) drawer.setDeleteTarget(null)
        }}
        title={`删除「${drawer.deleteTarget?.title ?? ''}」？`}
        description="删除后不能恢复；只是暂时不想让它生效的话，关掉开关即可。"
        confirmText="删除"
        cancelText="取消"
        tone="destructive"
        pending={drawer.deletePending}
        onConfirm={drawer.confirmDelete}
      />
    </Sheet>
  )
}
