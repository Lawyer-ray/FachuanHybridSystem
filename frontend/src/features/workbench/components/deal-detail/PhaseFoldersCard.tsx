import { toast } from 'sonner'

import { Card } from './ui'

/**
 * 右栏「合同文件夹」——**由阶段树派生**，不另存一份目录清单。
 *
 * 阶段即文件夹：目录名 = `<编号>-<阶段名>`（`3.1-职工安置文书`）。律师在系统里看到的
 * 树与磁盘上交付给客户的结构逐字一致，改名/重排/加子阶段后右栏同步。
 *
 * 为什么不复用 FolderTree：那棵树读的是磁盘真实目录（含发票/邮寄等档案目录、可右键
 * 管理），而这里表达的是**阶段结构**（含律师刚设计、还没建目录的阶段）。两者混在一
 * 起会让「右栏多出一个律师没设计过的目录」或「设计好的阶段右栏却不显示」。点目录
 * 仍然落到真实文件夹（有文件的），相当于树的一个入口，不重复磁盘事实。
 */
export function PhaseFoldersCard({
  rows,
  onOpenDir,
}: {
  rows: Array<{ no: string; name: string; depth: number }>
  /** 点目录行（`subpath` 由调用方按同一口径拼） */
  onOpenDir: (name: string) => void
}) {
  return (
    <Card>
      <div className="border-t-0 px-[18px] pt-[15px] pb-[15px]">
        <div className="mb-[9px] flex items-center gap-2">
          <h4 className="text-[11px] font-[650] tracking-[0.07em] text-muted-foreground/80">合同文件夹</h4>
          <button
            type="button"
            onClick={() => toast.info('新建文件夹正在开发中')}
            className="ml-auto cursor-pointer text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          >
            ＋ 新建文件夹
          </button>
        </div>

        {rows.length === 0 ? (
          <div className="text-[12px] text-muted-foreground">还没有阶段，设计阶段后这里自动出现对应目录</div>
        ) : (
          <div className="flex flex-col gap-px">
            {rows.map((r) => {
              const name = `${r.no}-${r.name}`
              return (
                <button
                  key={r.no}
                  type="button"
                  title={name}
                  onClick={() => onOpenDir(name)}
                  style={{ paddingLeft: 4 + (r.depth - 1) * 12 }}
                  className="flex cursor-pointer items-center gap-1.5 rounded-[6px] py-1 pr-1 text-left transition-colors hover:bg-secondary/50"
                >
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-secondary-foreground">{name}</span>
                </button>
              )
            })}
          </div>
        )}
        <div className="mt-2 text-[11px] leading-[1.6] text-muted-foreground/80">
          目录名由阶段树派生，改名后同步
        </div>
      </div>
    </Card>
  )
}
