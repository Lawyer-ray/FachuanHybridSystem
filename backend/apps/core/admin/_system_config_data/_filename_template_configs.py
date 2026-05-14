"""文件名模板配置数据"""

from typing import Any

__all__ = ["get_filename_template_configs"]


def get_filename_template_configs() -> list[dict[str, Any]]:
    """获取文件名模板配置项"""
    return [
        {
            "key": "FILENAME_TEMPLATE_COURT_DOC",
            "category": "court_sms",
            "description": (
                "法院文书文件名模板。可用占位符：{title}=文书标题, {case_name}=案件名, {date}=日期(YYYYMMDD)。"
                "示例：{title}（{case_name}）_{date}收"
            ),
            "value": "{title}（{case_name}）_{date}收",
            "is_secret": False,
        },
        {
            "key": "FILENAME_TEMPLATE_GENERATED_DOC",
            "category": "general",
            "description": (
                "生成文档文件名模板（合同/诉讼/证据等）。"
                "可用占位符：{doc_type}=文档类型, {case_name}=案件名, {version}=版本号, {date}=日期(YYYYMMDD)。"
                "示例：{doc_type}（{case_name}）V{version}_{date}"
            ),
            "value": "{doc_type}（{case_name}）V{version}_{date}",
            "is_secret": False,
        },
    ]
