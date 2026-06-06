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

## CI 注意事项

### 本地 CI 必须覆盖所有变更文件

本地 ruff/mypy 检查范围必须与远端 CI 一致，否则会出现"本地绿、远端红"的情况。

**远端 CI 检查范围**：`git diff main --name-only` 中所有变更文件（不只是你改的文件）。

**正确的本地 CI 命令**（在 `backend/` 目录下）：
```bash
# ruff：检查所有变更文件
git diff main --name-only -- '*.py' | xargs -r .venv/bin/ruff check

# mypy：检查所有变更文件
git diff main --name-only -- '*.py' | xargs -r .venv/bin/mypy --ignore-missing-imports

# 语法编译：检查所有 Python 文件
.venv/bin/python -m compileall -q apps apiSystem
```

**错误做法**：只检查自己改的几个文件，忽略了分支上其他变更文件（合并冲突、其他人的提交等）。

### mypy type: ignore 错误码

mypy 的 `type: ignore` 注释需要精确匹配错误码。如果本地 mypy 因 Django 插件崩溃无法运行，不要盲猜错误码。正确做法：
1. 先在 CI 日志中找到确切的错误码（如 `no-any-return`、`attr-defined`、`override`）
2. 用正确的错误码添加 `type: ignore[xxx]`
3. 如果不确定，用通用的 `type: ignore`（不带错误码）

### 远端 CI 包含的检查

| 检查项 | 说明 |
|---|---|
| `Compile Python` | `python -m compileall` 语法编译 |
| `ruff` | ruff lint（变更文件） |
| `mypy` / `mypy-full` / `mypy-strict` | 类型检查（变更文件） |
| `pytest` | 单元测试 |
| `coverage` | 测试覆盖率 |
| `integration-smoke` | 集成冒烟测试 |
| `property-smoke` | 属性测试 |
| `poi-service` | Java 编译 + 测试 |
