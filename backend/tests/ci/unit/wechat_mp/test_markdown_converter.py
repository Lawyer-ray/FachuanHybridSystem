"""微信公众号 Markdown 转换服务测试。"""

from __future__ import annotations

from apps.wechat_mp.services.markdown_converter import (
    ThemeConfig,
    THEMES,
    THEME_CLASSIC,
    THEME_ELEGANT,
    THEME_GREEN,
    _build_callout_html,
    _process_alerts,
    _apply_inline_styles,
    _wrap_section,
    _get_styles,
    _add_table_striping,
    convert_markdown_to_wechat_html,
    extract_summary,
)


class TestThemeConfig:
    """ThemeConfig 测试。"""

    def test_default_theme(self) -> None:
        theme = ThemeConfig()
        assert theme.name == "default"
        assert theme.primary_color == "#0F4C81"
        assert theme.font_size == "15px"
        assert theme.line_height == "1.8"
        assert theme.code_theme == "github"
        assert theme.hr_style == "gradient"

    def test_predefined_themes(self) -> None:
        """预定义主题。"""
        assert "classic" in THEMES
        assert "elegant" in THEMES
        assert "green" in THEMES
        assert THEME_CLASSIC.name == "classic"
        assert THEME_ELEGANT.name == "elegant"
        assert THEME_GREEN.name == "green"


class TestCalloutHtml:
    """Callout 盒子测试。"""

    def test_build_callout_html(self) -> None:
        html = _build_callout_html("NOTE", "📘 注意", "#478be6", "注意内容")
        assert "📘 注意" in html
        assert "注意内容" in html
        assert "#478be6" in html

    def test_build_callout_html_strips_p_tags(self) -> None:
        html = _build_callout_html("NOTE", "标题", "#478be6", "<p>内容</p>")
        assert "<p>" not in html or "内容" in html


class TestProcessAlerts:
    """GFM Alert 处理测试。"""

    def test_process_note_alert(self) -> None:
        html = "<blockquote><p>[!NOTE]</p><p>注意内容</p></blockquote>"
        result = _process_alerts(html)
        assert "📘 注意" in result
        assert "注意内容" in result

    def test_process_warning_alert(self) -> None:
        html = "<blockquote><p>[!WARNING]</p><p>警告内容</p></blockquote>"
        result = _process_alerts(html)
        assert "⚠️ 警告" in result

    def test_process_unknown_alert(self) -> None:
        """未知 alert 类型不变。"""
        html = "<blockquote><p>[!UNKNOWN]</p><p>内容</p></blockquote>"
        result = _process_alerts(html)
        # 未知类型不做处理，原样返回
        assert "UNKNOWN" in result


class TestInlineStyles:
    """内联样式测试。"""

    def test_apply_inline_styles(self) -> None:
        styles = {"p": "color:red;", "h1": "color:blue;"}
        html = "<p>段落</p><h1>标题</h1>"
        result = _apply_inline_styles(html, styles)
        assert 'style="color:red;"' in result
        assert 'style="color:blue;"' in result

    def test_apply_inline_styles_no_duplicate(self) -> None:
        """不重复添加 style。"""
        styles = {"p": "color:red;"}
        html = '<p style="existing">段落</p>'
        result = _apply_inline_styles(html, styles)
        assert result == html

    def test_wrap_section(self) -> None:
        styles = {"section": "font-size:15px;"}
        html = "<p>内容</p>"
        result = _wrap_section(html, styles)
        assert result.startswith("<section")
        assert result.endswith("</section>")
        assert "font-size:15px;" in result


class TestGetStyles:
    """样式生成测试。"""

    def test_classic_theme_styles(self) -> None:
        styles = _get_styles(THEME_CLASSIC)
        assert "section" in styles
        assert "h1" in styles
        assert "h2" in styles
        assert "p" in styles
        assert "strong" in styles
        assert "blockquote" in styles
        assert "table" in styles
        assert "code" in styles
        assert "pre" in styles
        assert "hr" in styles

    def test_green_theme_styles(self) -> None:
        styles = _get_styles(THEME_GREEN)
        # green 主色调在 h2 等元素样式中
        assert "#07c160" in styles["h2"]


class TestAddTableStriping:
    """表格斑马纹测试。"""

    def test_striping(self) -> None:
        html = "<tr><td>1</td></tr><tr><td>2</td></tr><tr><td>3</td></tr><tr><td>4</td></tr>"
        result = _add_table_striping(html, "#0F4C81")
        # 偶数行被替换为带 style 的 tr
        assert "background:linear-gradient" in result
        # 总共4行，2行有背景色
        assert result.count("background:linear-gradient") == 2


class TestConvertMarkdownToWechatHtml:
    """主转换函数测试。"""

    def test_basic_conversion(self) -> None:
        md = "## 标题\n\n段落内容"
        html = convert_markdown_to_wechat_html(md, theme="classic")
        assert "<section" in html
        assert "</section>" in html
        assert "标题" in html
        assert "段落内容" in html

    def test_conversion_removes_first_h1(self) -> None:
        md = "# 文章标题\n\n正文内容"
        html = convert_markdown_to_wechat_html(md)
        assert "文章标题" not in html
        assert "正文内容" in html

    def test_conversion_with_theme_config(self) -> None:
        md = "正文内容"
        theme = ThemeConfig(name="custom", primary_color="#ff0000")
        html = convert_markdown_to_wechat_html(md, theme=theme)
        assert "正文内容" in html

    def test_conversion_unknown_theme_fallback(self) -> None:
        md = "正文内容"
        html = convert_markdown_to_wechat_html(md, theme="nonexistent")
        assert "正文内容" in html

    def test_conversion_with_code_block(self) -> None:
        md = "```python\nprint('hello')\n```"
        html = convert_markdown_to_wechat_html(md)
        assert "print" in html

    def test_conversion_with_table(self) -> None:
        md = "| 列1 | 列2 |\n| --- | --- |\n| 值1 | 值2 |"
        html = convert_markdown_to_wechat_html(md)
        assert "值1" in html

    def test_conversion_with_bold(self) -> None:
        md = "**加粗文本**"
        html = convert_markdown_to_wechat_html(md)
        assert "加粗文本" in html

    def test_conversion_with_list(self) -> None:
        md = "- 项目1\n- 项目2\n- 项目3"
        html = convert_markdown_to_wechat_html(md)
        assert "项目1" in html


class TestExtractSummary:
    """摘要提取测试。"""

    def test_extract_summary_basic(self) -> None:
        md = "# 标题\n\n这是一段正文内容，用于提取摘要。"
        summary = extract_summary(md)
        assert "这是一段正文内容" in summary

    def test_extract_summary_removes_markdown(self) -> None:
        md = "**加粗** *斜体* [链接](http://example.com)"
        summary = extract_summary(md)
        assert "**" not in summary
        assert "*" not in summary
        assert "[" not in summary

    def test_extract_summary_max_length(self) -> None:
        md = "这是一段很长的文本" * 100
        summary = extract_summary(md, max_length=50)
        assert len(summary) <= 53  # 50 + "..."

    def test_extract_summary_short_text(self) -> None:
        md = "短文本"
        summary = extract_summary(md, max_length=100)
        assert summary == "短文本"
