# POI Service

Apache POI 文档生成微服务，为法穿AI提供高质量的 DOCX 文档生成能力。

## 功能

### 通用文档（DocumentController）
| 端点 | 说明 | POI 特性展示 |
|:---|:---|:---|
| `GET /api/documents/health` | 健康检查 | - |
| `POST /api/documents/complaint` | 生成起诉状 | 合并单元格表格、样式段落、落款对齐 |
| `POST /api/documents/report` | 生成尽调报告 | 样式表格、页眉页脚、分节符、水印 |

### 归档文书（ArchiveController）
| 端点 | 说明 | POI 特性展示 |
|:---|:---|:---|
| `POST /api/documents/archive/case-cover` | 案卷封面 | 表单样式表格、交替行背景 |
| `POST /api/documents/archive/closing-register` | 结案归档登记表 | 彩色表头、数据表格 |
| `POST /api/documents/archive/catalog` | 卷内目录 | 页眉页脚（第X页/共X页） |

### 模板渲染（TemplateController）
| 端点 | 说明 | POI 特性展示 |
|:---|:---|:---|
| `POST /api/documents/template/render` | 渲染 .docx 模板 | 跨段落/表格/页眉页脚替换占位符 |
| `GET /api/documents/templates` | 列出可用模板 | - |

## 技术栈

- Java 25 (LTS) + Spring Boot 3.5.14
- Apache POI 5.5.1（poi + poi-ooxml + poi-ooxml-full）
- Docker（Ubuntu Noble + 中文字体 + 非 root + HEALTHCHECK）

## 本地运行

```bash
cd java-services/poi-service
./mvnw spring-boot:run
# 服务启动在 http://127.0.0.1:8090
```

## Docker 运行

```bash
docker build -t poi-service .
docker run -p 8090:8090 poi-service
```

## Django 集成

在 `settings.py` 中配置：
```python
POI_SERVICE_URL = "http://127.0.0.1:8090"
```

通过 Django 客户端调用：
```python
from apps.core.services.poi_client import get_poi_client

client = get_poi_client()

# 生成起诉状
docx_bytes = client.generate_complaint({...})

# 生成尽调报告
docx_bytes = client.generate_report({...})

# 渲染模板
docx_bytes = client.render_template("contract.docx", {"name": "张三"})
```

## 测试

```bash
# 先启动 POI 服务，然后运行测试脚本
cd java-services/poi-service
python3 test_archive_e2e.py
python3 test_poi_integration.py
```
