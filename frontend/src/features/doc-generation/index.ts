/**
 * 文书生成（doc-generation）的对外出口。
 *
 * 其它 feature / app 层**只从这里引**，不穿透内部目录（api / components）。
 * 当前只有项目详情页（features/workbench）用它：诉讼分支的案件卡上「生成文书」
 * → 打开本域的 `DraftDialog` → 成稿回落到 workbench 已有的文件夹画布。
 *
 * 不新增路由：入口就是详情页里的一个弹窗，一份文书没有自己的 URL
 * （谁挂在哪份文件上由后端返回的 kind/owner_id/subpath 决定）。
 */
export { DraftDialog } from './components/DraftDialog'
export type { DocType, DraftRequest, DraftResult } from './types'
