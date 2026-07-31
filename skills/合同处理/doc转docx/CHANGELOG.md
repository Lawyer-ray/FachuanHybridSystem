# Changelog - doc转docx Skill

所有对此 skill 的更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，

## [1.0.0] - 2026-07-31

### 新增

- 初始版本发布
- 支持批量转换 .doc 文件为 .docx 格式
- 调用后端 API 实现，底层使用 LibreOffice
- 自动打包转换结果为 ZIP 文件
- 支持自定义输出目录
- 命令行接口支持

### 技术实现

- 调用 `/api/v1/doc-converter/jobs` API
- 轮询任务进度直到完成
- 下载并解压转换结果

### 依赖

- 后端服务运行在 `http://127.0.0.1:8002`
- LibreOffice 已安装
- Python 库：`requests`
