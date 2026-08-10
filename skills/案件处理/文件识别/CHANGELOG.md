# Changelog - 文件识别 Skill

所有对此 Skill 的更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),

## [1.0.0] - 2026-08-10

### 新增

- 初始版本,接入 `http://127.0.0.1:8002/api/v1/document-parsing/` 文档解析服务
- 支持 15+ 种文件格式统一转为 Markdown:
  - 文档:PDF / DOC / DOCX / PPT / PPTX / XLS / XLSX / OFD / RTF
  - 图片:JPG / JPEG / PNG / BMP / TIFF
  - 其他:HTML / CSV / TXT
- 自动选择解析后端(auto 模式按 textin > mineru > local 优先级)
- 支持单文件识别和批量目录扫描(可递归)
- 异步任务自动轮询(默认间隔 2s,超时 600s,可配置)
- 同步结果直接返回
- 支持两种认证方式:JWT Token(优先) / Session 登录
- 通过环境变量或 CLI 参数配置认证
- 退出码区分全成功(0)/部分失败(1)/全失败(2)
- 模块化设计:formats/detector/converter/utils/cli 职责清晰
- 复用工作流级公共工具 `..utils`(APIClient / DocumentParsingClient)

### 模块结构

```
文件识别/
├── __init__.py    # 入口(导出 recognize_file / recognize_files)
├── __main__.py    # 模块执行入口
├── formats.py     # 支持格式定义、后端配置
├── detector.py    # 文件格式检测、后端选择、目录扫描
├── converter.py   # 调用 API 解析并保存 Markdown
├── utils.py       # 工具函数(输出路径生成、结果汇总)
└── cli.py         # 命令行入口
```
