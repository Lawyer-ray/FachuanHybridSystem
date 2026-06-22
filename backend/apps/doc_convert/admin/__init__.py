"""Stub: doc_convert admin moved to plugins/doc_convert/admin/"""

try:
    from plugins.doc_convert.admin import DocConvertToolAdmin
except ImportError:
    DocConvertToolAdmin = None  # type: ignore[assignment]
