#!/usr/bin/env python3
"""添加新的翻译条目到 po 文件."""

po_file = 'apps/litigation_ai/locale/en/LC_MESSAGES/django.po'

new_entries = '''
#: apps/litigation_ai/templates/litigation_ai/mock_trial.html:25
msgid "导出报告"
msgstr "Export Report"

#: apps/litigation_ai/templates/litigation_ai/mock_trial.html:25
msgid "导出中..."
msgstr "Exporting..."

#: apps/litigation_ai/templates/litigation_ai/mock_trial.html:55
msgid "选择难度:"
msgstr "Select Difficulty:"

#: apps/litigation_ai/templates/litigation_ai/mock_trial.html:57
msgid "简单 - 温和反驳"
msgstr "Easy - Gentle Rebuttal"

#: apps/litigation_ai/templates/litigation_ai/mock_trial.html:58
msgid "中等 - 有理有据"
msgstr "Medium - Reasoned Argument"

#: apps/litigation_ai/templates/litigation_ai/mock_trial.html:59
msgid "困难 - 犀利精准"
msgstr "Hard - Sharp and Precise"

#: apps/litigation_ai/templates/litigation_ai/mock_trial.html:91
msgid "AI 分析中..."
msgstr "AI Analyzing..."
'''

with open(po_file, 'a', encoding='utf-8') as f:
    f.write(new_entries)

print('翻译条目已添加')
