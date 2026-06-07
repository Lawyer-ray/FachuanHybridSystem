# Java 微服务开发规范

本目录 `java-services/` 存放所有 Java/Spring Boot 微服务。当前包含 `poi-service`（Apache POI 文档生成）。

## 技术栈

- **Java 25** (LTS)
- **Spring Boot 3.5.14**
- **Apache POI 5.5.1**（poi + poi-ooxml + poi-ooxml-full）
- **Lombok 1.18.38**（@Data 注解替代手写 getter/setter）

## 目录结构

```
java-services/
└── poi-service/
    ├── pom.xml                    # Maven 依赖
    ├── Dockerfile                 # 多阶段构建（Ubuntu Noble + 中文字体）
    ├── mvnw / .mvn/              # Maven Wrapper（无需全局安装 Maven）
    ├── src/main/java/.../
    │   ├── PoiApplication.java   # Spring Boot 入口
    │   ├── controller/           # REST 端点（按业务域拆分）
    │   ├── service/              # 业务逻辑
    │   ├── model/                # 请求/响应模型（@Data）
    │   └── util/                 # 工具类
    └── test_*.py                 # Python 集成测试
```

## 开发命令

```bash
cd java-services/poi-service

# 编译（需要 Java 25）
./mvnw clean compile

# 打包
./mvnw package -DskipTests

# 本地运行
./mvnw spring-boot:run
# 或
java -jar target/poi-service-1.0.0.jar
# 服务启动在 http://127.0.0.1:8090

# Docker 构建
docker build -t poi-service .
docker run -p 8090:8090 poi-service
```

## 经验教训

### 1. POI 5.x OOXML 类名变化

POI 5.x 中 OOXML schema 类名与旧版本不同：
- ❌ `CTPgSz` → ✅ `CTPageSz`（页面尺寸）
- ❌ `CTPgMar` → ✅ `CTPageMar`（页面边距）
- ❌ `sectPr.setType(STSectionMark.NEXT_PAGE)` → ✅ `sectPr.addNewType().setVal(STSectionMark.Enum.forString("nextPage"))`

关键 import：
```java
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTP;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTPPr;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTSectPr;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.CTSimpleField;
import org.openxmlformats.schemas.wordprocessingml.x2006.main.STSectionMark;
```

### 2. HeaderFooterType 的包路径

```java
// ❌ 错误：import org.apache.poi.xwpf.usermodel.HeaderFooterType
// ✅ 正确：
import org.apache.poi.wp.usermodel.HeaderFooterType;
```

`createHeader(HeaderFooterType.DEFAULT)` 的参数类型是 `org.apache.poi.wp.usermodel.HeaderFooterType`，不是 xwpf 包下的。

### 3. Lombok 在 Java 25 下的配置

Lombok 需要在 `pom.xml` 中显式配置 annotation processor：

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>org.projectlombok</groupId>
                <artifactId>lombok</artifactId>
                <version>1.18.38</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
```

没有这个配置，`@Data` 注解不会生效，编译时找不到 getter/setter。

### 4. XWPFTableCell.setText() 已弃用

POI 5.x 中 `cell.setText()` 已弃用。正确做法：
```java
cell.removeParagraph(0);
XWPFParagraph p = cell.addParagraph();
XWPFRun run = p.createRun();
run.setText("内容");
```

### 5. XWPFParagraph.setIndentationLeft() 参数类型

```java
// ❌ 错误：para.setIndentationLeft(BigInteger.valueOf(720))
// ✅ 正确：para.setIndentationLeft(720)  // int, not BigInteger
```

### 6. Docker 中文字体

Alpine 镜像缺少中文字体，POI 生成的 DOCX 在 Word 中打开会字体回退。**必须用 Ubuntu Noble 基础镜像 + fonts-noto-cjk**：

```dockerfile
FROM eclipse-temurin:25-jre-noble
RUN apt-get update && apt-get install -y --no-install-recommends \
    fontconfig fonts-noto-cjk wget && \
    rm -rf /var/lib/apt/lists/* && fc-cache -fv
```

验证：`fc-list :lang=zh` 应列出 Noto CJK 字体。

### 7. format_html 与内联 CSS 的交互

Python Django 的 `format_html` 不影响 Java 端，但 POI 生成的 DOCX 中的格式完全由 Java 代码控制。中文字体需要通过 `run.setFontFamily("微软雅黑")` 显式设置，否则会回退到系统默认字体。

### 8. httpx JSON 序列化与 Python set

Python 的 `{"a", "b"}` 是 set 不是 dict，`json.dumps()` 无法序列化。在构造测试数据时，tableData 等字段必须用 dict 字面量 `{"key": "value"}` 而不是 set。

### 9. Spring Boot 端口冲突

开发时如果上一个进程未完全退出，新进程会报 `Port 8090 already in use`。解决：
```bash
lsof -ti:8090 | xargs kill -9
```

### 10. Maven Wrapper 使用

项目包含 Maven Wrapper（`.mvn/wrapper/`），无需全局安装 Maven：
```bash
./mvnw clean package -DskipTests  # 首次会自动下载 Maven
```

---

# 更新日志规范

## 目录结构

```
changelog/
├── CHANGELOG.md              # 总索引（反向链接到各版本文件）
└── v26.51/                   # 大版本文件夹（YY.WW）
    ├── v26.51.3.md
    ├── v26.51.4.md
    └── ...
```

- **大版本**（`YY.WW`）创建独立文件夹，如 `v26.51/`、`v26.52/`
- **小版本**文件放在对应大版本文件夹内，如 `v26.51/v26.51.8.md`
- `CHANGELOG.md` 中对有独立文件的版本使用 `详见 [v26.51.8.md](v26.51/v26.51.8.md)` 格式链接

## 版本文件格式

```markdown
# v26.51.8 - 2026-06-07

## 后端

### 新功能
- **功能名**: 描述

### 修复
- **问题名**: 描述
  - 具体文件改动

## 前端
## 基础设施
## 依赖更新
```

- H1：`# v{VERSION} - {YYYY-MM-DD}`
- H2：按领域分类（后端、前端、基础设施、CI/CD 等）
- H3：按变更类型分类（新功能、修复、优化、新增、移除）
- 条目：**加粗标题** + 冒号 + 描述
