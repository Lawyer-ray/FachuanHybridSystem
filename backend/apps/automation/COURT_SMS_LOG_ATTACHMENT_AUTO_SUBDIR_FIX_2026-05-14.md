# 法院短信日志附件自动子目录修复记录

## 变更时间

- 2026-05-14

## 变更背景

此前法院短信处理流程虽然已经支持：

- 自动创建案件日志
- 自动下载文书
- 自动重命名文书
- 自动把文书挂到案件日志

但“挂到案件日志”这一步走的是旧链路：

1. 先把文件复制到 `media/case_logs`
2. 再直接创建 `CaseLogAttachment`
3. 没有复用“日志附件自动推荐子目录”能力

这会导致一个明显问题：

- 日志附件虽然能看到
- 但不会根据文件命名自动进入案件业务目录下的对应子目录

例如：

- `起诉状.pdf` 不会自动进入 `一审/1-立案材料/1-起诉材料`
- `微信聊天记录.pdf` 不会自动进入 `一审/1-立案材料/5-证据材料`
- `保全申请书.pdf` 不会自动进入 `一审/1-立案材料/8-保全申请书及保函`

## 本次修改内容

### 1. 调整法院短信附件导入路径

修改文件：

- `apps/automation/services/sms/document_attachment_service.py`

修改前：

- 法院短信附件先复制到 `media/case_logs`
- 再以 `case_logs/xxx.pdf` 的相对路径写入日志附件

修改后：

- 法院短信附件不再先手工复制到 `media/case_logs`
- 直接把本地下载文件交给案件日志内部附件导入入口

作用：

- 让法院短信附件不再绕开统一存储服务
- 为后续命中“自动推荐子目录”创造条件

### 2. 增强内部日志附件导入能力

修改文件：

- `apps/cases/services/case/case_log_internal_service.py`

修改前：

- `add_case_log_attachment_internal(...)` 更适合处理已经存在的相对路径
- 对“本地绝对路径文件导入”支持不完整

修改后：

- 当传入的是本地绝对路径且文件存在时：
  - 读取本地文件
  - 走 `CaseLogAttachmentStorageService.save_attachment(...)`
  - 自动触发子目录推荐逻辑
  - 生成标准化的 `CaseLogAttachment`

- 当传入的仍是旧相对路径时：
  - 保持原有兼容逻辑不变

作用：

- 不只法院短信能受益
- 其他“内部导入日志附件”的场景也能复用统一存储逻辑

### 3. 优化日志附件字段写入方式

本次同时修正了一个实现细节：

- 案件目录场景下，`CaseLogAttachment.file` 不再保存绝对路径
- 改为保存相对路径
- 真实解析仍依赖 `storage_root_type + relative_file_path`

作用：

- 避免绝对路径过长导致字段长度风险
- 保持与现有附件解析逻辑一致
- 对历史数据兼容

## 这次修改最终实现了什么

本次修改完成后，法院短信流程新增了下面这项能力：

- 法院短信自动创建的日志附件，可以根据文件名自动进入推荐子目录

也就是说，现在法院短信这条链路已经真正接入了你之前做的：

- 日志附件自动推荐子目录
- 优先命中已有目录
- 根据文件命名规则分类
- 默认回退目录逻辑

## 用户可见效果

修改完成后，后台验收时应看到：

1. 法院短信状态最终变成 `已完成`
2. 对应案件日志已经自动生成
3. 日志附件已经自动生成
4. 附件的“保存子目录”不再为空
5. 且子目录会根据文件名自动命中

例如可能看到：

- `一审/1-立案材料/1-起诉材料`
- `一审/1-立案材料/5-证据材料`
- `一审/1-立案材料/8-保全申请书及保函`

## 影响范围

### 直接影响

- 法院短信自动加日志附件
- 内部通过本地文件导入案件日志附件的场景

### 不影响

- 手工在案件日志页上传附件的已有逻辑
- 旧的相对路径附件解析逻辑
- 已存在的历史日志附件数据

## 本次修改的主要作用总结

- 修复“法院短信附件没有走自动子目录规则”的问题
- 让法院短信流程和日志附件统一存储规则打通
- 减少附件只落在 `media/case_logs` 的情况
- 提高日志附件自动整理能力
- 为后续自动归档、自动整理材料提供更稳定基础

## 相关文件

- `apps/automation/services/sms/document_attachment_service.py`
- `apps/cases/services/case/case_log_internal_service.py`
- `tests/ci/unit/automation/test_court_sms_document_attachment_service.py`
- `tests/ci/unit/test_case_log_internal_service.py`

## 测试结果

本次相关测试已通过：

- `tests/ci/unit/automation/test_court_sms_document_attachment_service.py`
- `tests/ci/unit/test_case_log_internal_service.py`
- `tests/ci/unit/test_case_log_attachment_storage.py`

结果：

- `16 passed`
