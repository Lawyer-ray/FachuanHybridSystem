/**
 * 自动分段纯逻辑助手的**出口（barrel）**，本文件只做 re-export。
 *
 * 为什么还留着这个文件：它原本是 356 行的「什么都装一点」的助手集合，按关注点
 * 拆成三个模块——轮询机制 `poll-job.ts`、分段来源归因 `segment-backend-note.ts`、
 * OCR 块几何 `ocr-blocks.ts`（`api/index.ts` 是同一手法：拆分后 barrel 保留原路径）。
 *
 * 保留而不是删掉、让 5 个生产消费方（`auto-split-tracks` / `auto-split-apply` /
 * `use-auto-split-task` / `AutoSplitProgress` / `ReaderOverlays`）与 3 个测试文件
 * 改 import 路径的理由：路径与它装的是什么无关，改名只会制造一次纯噪声的
 * 全量改动，还容易在并行分支上撞冲突。**新代码请直接 import 对应的子模块**，
 * 不要再往这里加东西——这个文件不该再长出内容。
 */

export * from './poll-job'
export * from './segment-backend-note'
export * from './ocr-blocks'
