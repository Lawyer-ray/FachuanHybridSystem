"""Tests for legal_solution report HTML sanitization (bleach whitelist)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


class TestSanitizeReportHtmlStripsAttacks:
    """攻击向量全部被剥离：script / 内联事件 / javascript: 链接 / iframe / 注释。"""

    def test_script_stripped(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html("<p>正文</p><script>alert('xss')</script>")
        assert "<script" not in result
        assert "<p>正文</p>" in result

    def test_inline_event_handler_stripped(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html('<img src="https://example.com/a.png" alt="图" onerror="alert(1)">')
        assert "onerror" not in result
        assert '<img src="https://example.com/a.png" alt="图">' in result

    def test_javascript_protocol_link_stripped(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html('<a href="javascript:alert(1)" title="提示">点我</a>')
        assert "javascript:" not in result
        assert 'title="提示"' in result

    def test_iframe_stripped(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html('<iframe src="https://evil.example.com"></iframe><p>正文</p>')
        assert "<iframe" not in result
        assert "evil.example.com" not in result
        assert "<p>正文</p>" in result

    def test_html_comment_stripped(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html("<!-- conditional comment --><p>keep</p>")
        assert "<!--" not in result
        assert "<p>keep</p>" in result

    def test_data_protocol_link_stripped(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html('<a href="data:text/html,<script>alert(1)</script>">data</a>')
        assert "data:" not in result


class TestSanitizeReportHtmlKeepsLegitContent:
    """正常报告内容不受影响：表格 / 链接 / 标题 / 加粗斜体 / 引用 / 列表 / 代码。"""

    def test_table_preserved(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        html = '<table><thead><tr><th>项目</th></tr></thead><tbody><tr><td>诉讼费</td></tr></tbody></table>'
        result = sanitize_report_html(html)
        for tag in ("<table>", "<thead>", "<tbody>", "<tr>", "<th>项目</th>", "<td>诉讼费</td>"):
            assert tag in result

    def test_table_text_align_preserved(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html('<table><tr><th style="text-align: left;">项目</th><td style="text-align: right;">金额</td></tr></table>')
        assert "text-align: left" in result
        assert "text-align: right" in result

    def test_dangerous_style_stripped(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html('<table><tr><td style="position:fixed;top:0">evil</td></tr></table>')
        assert "position" not in result
        assert "<td" in result
        assert "evil" in result

    def test_link_preserved(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html('<a href="https://example.com" title="示例">链接</a>')
        assert '<a href="https://example.com" title="示例">链接</a>' in result

    def test_mailto_link_preserved(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        result = sanitize_report_html('<a href="mailto:lawyer@example.com">邮件</a>')
        assert 'href="mailto:lawyer@example.com"' in result

    def test_heading_and_inline_tags_preserved(self):
        from apps.legal_solution.services.solution_generator import sanitize_report_html

        html = (
            "<h2>标题</h2>"
            "<p><strong>加粗</strong><em>斜体</em><del>删除</del><code>条文</code></p>"
            "<blockquote>引用</blockquote>"
            "<ul><li>无序</li></ul><ol><li>有序</li></ol>"
            "<pre><code>代码块</code></pre>"
        )
        result = sanitize_report_html(html)
        for tag in ("<h2>", "<strong>加粗</strong>", "<em>斜体</em>", "<del>删除</del>", "<code>条文</code>",
                    "<blockquote>引用</blockquote>", "<ul><li>无序</li></ul>", "<ol><li>有序</li></ol>",
                    "<pre><code>代码块</code></pre>"):
            assert tag in result


class TestMdToHtmlSanitized:
    """markdown 渲染后即消毒（_generate_section 落库路径复用 _md_to_html）。"""

    def test_raw_script_in_markdown_stripped(self):
        from apps.legal_solution.services.solution_generator import _md_to_html

        result = _md_to_html("正常段落\n\n<script>alert(1)</script>")
        assert "<script" not in result
        assert "<p>正常段落</p>" in result

    def test_img_onerror_in_markdown_stripped(self):
        from apps.legal_solution.services.solution_generator import _md_to_html

        result = _md_to_html('<img src="https://example.com/b.png" onerror="alert(1)">')
        assert "onerror" not in result
        assert 'src="https://example.com/b.png"' in result

    def test_markdown_table_rendered_and_kept(self):
        from apps.legal_solution.services.solution_generator import _md_to_html

        result = _md_to_html("| 项目 | 金额 |\n|:--|--:|\n| 诉讼费 | 100 |")
        for tag in ("<table>", "<thead>", "<th", "<td"):
            assert tag in result
        assert "text-align: left" in result
        assert "text-align: right" in result

    def test_markdown_link_preserved(self):
        from apps.legal_solution.services.solution_generator import _md_to_html

        result = _md_to_html("[裁判文书](https://example.com/case)")
        assert '<a href="https://example.com/case">裁判文书</a>' in result


class TestHtmlRendererSanitizesLegacyRows:
    """admin regenerate_html / adjust 链路统一经 HtmlRenderer → 同一消毒函数（存量数据兜底）。"""

    def test_render_sanitizes_unsafe_legacy_section_html(self):
        from apps.legal_solution.services.html_renderer import HtmlRenderer

        section = SimpleNamespace(
            section_type="case_analysis",
            status="completed",
            title="案情分析",
            version=1,
            html_content="<p>ok</p><script>alert(1)</script><img src=x onerror=alert(2)>",
        )
        task = MagicMock()
        task.case_summary = "案情摘要"
        task.created_by = None
        task.sections.order_by.return_value = [section]

        html = HtmlRenderer().render(task)

        assert "<script" not in html
        assert "onerror" not in html
        assert "<p>ok</p>" in html
