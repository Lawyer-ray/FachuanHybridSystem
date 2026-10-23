/**
 * 合同绑定文件夹引用的拖拽通道常量——copilot 与 workbench 两个 feature 共用
 * （面板内目录树、详情页文件夹树都以此为拖拽源），故上提 lib。
 */

/** 拖拽携带引用 JSON 的自定义 MIME；系统外文件走原生 Files 通道互不混淆 */
export const FOLDER_REF_MIME = 'application/x-fachuan-folder-ref'
