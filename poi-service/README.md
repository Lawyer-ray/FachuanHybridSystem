# POI Service

Apache POI 文档生成微服务，为法穿AI提供高质量的 DOCX 文档生成能力。

## 功能

| 端点 | 说明 | POI 特性展示 |
|:---|:---|:---|
| `POST /api/documents/complaint` | 生成起诉状 | 合并单元格表格、样式段落、落款对齐 |
| `POST /api/documents/report` | 生成尽调报告 | 嵌入图表、样式表格、页眉页脚、分节符、水印、目录域、内容控件 |
| `POST /api/documents/template/render` | 渲染 .docx 模板 | 跨段落/表格/页眉页脚替换占位符 |
| `GET /api/documents/templates` | 列出可用模板 | - |
| `GET /api/documents/health` | 健康检查 | - |

## 技术栈

- Java 21 + Spring Boot 3.4
- Apache POI 5.3.0（poi + poi-ooxml + poi-ooxml-full）
- Docker（多阶段构建）

## 本地运行

```bash
cd poi-service
mvn spring-boot:run
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
cd poi-service
python test_poi_integration.py
```

## POI 能力展示

### 起诉状生成
- 合并单元格表格（当事人信息、落款签名）
- 混合格式段落（黑体标题 + 仿宋正文）
- 首行缩进、两端对齐
- 编号列表（诉讼请求）

### 尽调报告生成
- **图表嵌入**：Excel 嵌入式柱状图（营收趋势）
- **样式表格**：交替行背景色、自定义列宽、表头配色
- **页眉页脚**：项目名/密级 + "第X页/共X页"
- **分节符**：封面页→目录→正文（每节独立布局）
- **水印**：密级水印文字
- **目录域**：Word 目录自动生成
- **内容控件**：SDT 标签
- **合并单元格表**：公司基本信息表
