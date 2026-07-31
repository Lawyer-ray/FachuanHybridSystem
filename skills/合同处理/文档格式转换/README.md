# 文档格式转换 Skill

将 .doc 文件转换为 .docx 格式。

## 功能

- 支持批量转换 .doc 文件为 .docx 格式
- 调用后端 API，底层使用 LibreOffice
- 自动打包转换结果为 ZIP 文件
- 支持自定义输出目录

## 使用方式

```bash
# 命令行调用
python -m skills.合同处理.文档格式转换 /path/to/document.doc

# 批量转换
python -m skills.合同处理.文档格式转换 /path/to/*.doc

# 指定输出目录
python -m skills.合同处理.文档格式转换 /path/to/document.doc --output-dir /path/to/output

# 在 Claude 中调用
/文档格式转换 /path/to/document.doc
```

## API 接口

本 skill 调用后端 API 实现转换：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/doc-converter/health` | 检查 LibreOffice 是否可用 |
| POST | `/api/v1/doc-converter/jobs` | 创建转换任务 |
| GET | `/api/v1/doc-converter/jobs/{job_id}` | 查询转换进度 |
| GET | `/api/v1/doc-converter/jobs/{job_id}/download` | 下载转换结果 |
| DELETE | `/api/v1/doc-converter/jobs/{job_id}` | 删除任务 |

## 依赖

- 后端服务运行在 `http://127.0.0.1:8002`
- LibreOffice 已安装并在 PATH 中
- Python 库：`requests`

## 输出

- 转换后的 .docx 文件保存在 `{输出目录}/converted_docx/`
- ZIP 打包文件保存在 `{输出目录}/converted_{job_id}.zip`

## 限制

- 仅支持 .doc 格式（不支持 .docx、.pdf 等）
- 单个文件最大 50MB
- 需要后端服务运行

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
