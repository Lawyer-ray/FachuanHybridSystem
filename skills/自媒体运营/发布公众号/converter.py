#!/usr/bin/env python3
"""Markdown → HTML 转换与 HTML 包装。"""


def _inline_format(text: str) -> str:
    """处理行内加粗、斜体。"""
    while "**" in text:
        parts = text.split("**", 2)
        if len(parts) < 3:
            break
        text = f"{parts[0]}<strong>{parts[1]}</strong>{parts[2]}"
    while text.count("*") >= 2:
        parts = text.split("*", 2)
        if len(parts) < 3:
            break
        text = f"{parts[0]}<em>{parts[1]}</em>{parts[2]}"
    return text


def markdown_to_html(md_text: str) -> str:
    """极简 Markdown 转 HTML，适合公众号图文。"""
    lines = md_text.splitlines()
    html_lines: list[str] = []
    in_blockquote = False
    in_list = False

    def flush_blockquote() -> None:
        nonlocal in_blockquote
        if in_blockquote:
            html_lines.append("</blockquote>")
            in_blockquote = False

    def flush_list() -> None:
        nonlocal in_list
        if in_list:
            html_lines.append("</ol>")
            in_list = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            flush_blockquote()
            flush_list()
            html_lines.append("<p>&nbsp;</p>")
            continue

        if stripped.startswith("```"):
            flush_blockquote()
            flush_list()
            html_lines.append("<p><strong>代码块</strong></p>")
            continue

        if stripped.startswith("> "):
            if not in_blockquote:
                flush_list()
                html_lines.append("<blockquote>")
                in_blockquote = True
            html_lines.append(f"<p>{_inline_format(stripped[2:].strip())}</p>")
            continue

        flush_blockquote()

        if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
            if not in_list:
                html_lines.append("<ol>")
                in_list = True
            html_lines.append(f"<li>{_inline_format(stripped.split('.', 1)[1].strip())}</li>")
            continue

        flush_list()

        if stripped.startswith("# "):
            html_lines.append(f"<h2>{_inline_format(stripped[2:])}</h2>")
            continue
        if stripped.startswith("## "):
            html_lines.append(f"<h3>{_inline_format(stripped[3:])}</h3>")
            continue
        if stripped.startswith("### "):
            html_lines.append(f"<h4>{_inline_format(stripped[4:])}</h4>")
            continue

        html_lines.append(f"<p>{_inline_format(stripped)}</p>")

    flush_blockquote()
    flush_list()
    return "".join(html_lines)


def wrap_full_html(body_html: str, title: str = "") -> str:
    """把正文 HTML 包装成完整页面（微信友好基础样式）。"""
    style = (
        'font-family: -apple-system, "PingFang SC", "Helvetica Neue", '
        "Helvetica, Arial, sans-serif; font-size: 17px; line-height: 1.8; "
        "color: #333; max-width: 680px; margin: 0 auto; padding: 16px;"
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body {{ {style} }}
h2 {{ font-size: 20px; font-weight: bold; margin-top: 24px; margin-bottom: 12px; }}
h3 {{ font-size: 18px; font-weight: bold; margin-top: 20px; margin-bottom: 10px; }}
p {{ margin: 14px 0; text-align: justify; word-break: break-word; }}
strong {{ font-weight: bold; }}
blockquote {{ border-left: 4px solid #ddd; padding-left: 14px; color: #666; margin: 16px 0; }}
li {{ margin: 8px 0; }}
</style>
</head>
<body>
{body_html}
</body>
</html>
"""
