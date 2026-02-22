"""Django admin configuration."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from django import forms
from django.forms.renderers import BaseRenderer
from django.utils.html import format_html
from django.utils.safestring import SafeString


class AutocompleteWidget(forms.TextInput):
    def __init__(
        self,
        api_url: str,
        field_name: str,
        case_type_field: str | None = None,
        placeholder: str | None = None,
        listen_case_type: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self.api_url = api_url
        self.field_name = field_name
        self.case_type_field = case_type_field
        self.placeholder = placeholder or "请输入搜索内容..."
        self.listen_case_type = listen_case_type
        super().__init__(*args, **kwargs)

    def render(
        self,
        name: str,
        value: Any,
        attrs: dict[str, Any] | None = None,
        renderer: BaseRenderer | None = None,
    ) -> SafeString:
        if attrs is None:
            attrs = {}

        attrs.update(
            {
                "class": "vTextField",
                "placeholder": self.placeholder,
                "autocomplete": "off",
                "style": "width: 300px;",
            }
        )

        input_html = super().render(name, value, attrs, renderer)

        api_url_js = json.dumps(self.api_url)
        case_type_field_js = json.dumps(self.case_type_field) if self.case_type_field else "null"
        initial_value_js = json.dumps(value or "")
        listen_case_type_js = json.dumps(self.listen_case_type)

        component_name = f"autocomplete_{name.replace('-', '_').replace('[', '_').replace(']', '_')}"

        # 提取长 JS/SVG 内容为变量,避免 E501
        _spinner_circle = (
            '<circle style="opacity: 0.25;" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3"></circle>'
        )
        _spinner_path = (
            '<path style="opacity: 0.75;" fill="currentColor"'
            ' d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2'
            " 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824"
            ' 3 7.938l3-2.647z"></path>'
        )
        _search_svg = (
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor">'
            '<path stroke-linecap="round" stroke-linejoin="round"'
            ' stroke-width="1.5"'
            ' d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>'
            "</svg>"
        )

        container_html = f"""
        <script>
        (function() {{
            window.{component_name} = function() {{
                return {{
                    query: {initial_value_js},
                    results: [],
                    isOpen: false,
                    highlightedIndex: -1,
                    isLoading: false,
                    debounceTimer: null,
                    apiUrl: {api_url_js},
                    caseTypeField: {case_type_field_js},
                    listenCaseType: {listen_case_type_js},
                    dropdownStyle: '',
                    noResults: false,

                    init() {{
                        document.addEventListener('click', (e) => {{
                            if (!this.$el.contains(e.target)) {{
                                this.isOpen = false;
                            }}
                        }});

                        window.addEventListener('scroll', () => {{
                            if (this.isOpen) this.updateDropdownPosition();
                        }}, true);

                        window.addEventListener('resize', () => {{
                            if (this.isOpen) this.updateDropdownPosition();
                        }});

                        this.$watch('query', () => {{
                            if (this.debounceTimer) clearTimeout(this.debounceTimer);
                            this.debounceTimer = setTimeout(() => this.search(), 300);
                        }});
                    }},

                    updateDropdownPosition() {{
                        if (!this.$refs.input) return;
                        const rect = this.$refs.input.getBoundingClientRect();
                        this.dropdownStyle = `
                            position: fixed;
                            left: ${{rect.left}}px;
                            top: ${{rect.bottom + 4}}px;
                            width: ${{rect.width}}px;
                            z-index: 999999;
                        `;
                    }},

                    highlightMatch(text) {{
                        if (!this.query || !text) return text;
                        const re = /[.*+?^${{}}()|[\\]\\]/g;
                        const esc = this.query.replace(re, '\\$&');
                        const regex = new RegExp(
                            `(${{esc}})`, 'gi');
                        const mk = '<mark style="background: #fef08a;'
                            + ' padding: 0 2px; border-radius: 2px;">'
                            + '$1</mark>';
                        return text.replace(regex, mk);
                    }},

                    onInput(e) {{
                        if (this.debounceTimer) clearTimeout(this.debounceTimer);
                        this.debounceTimer = setTimeout(() => this.search(), 300);
                    }},

                    onFocus() {{
                        if (this.$refs.input && this.$refs.input.value !== this.query) {{
                            this.query = this.$refs.input.value;
                        }}
                        if (this.results.length > 0) {{
                            this.updateDropdownPosition();
                            this.isOpen = true;
                        }} else {{
                            this.search();
                        }}
                    }},

                    async search() {{
                        this.isLoading = true;
                        this.noResults = false;
                        try {{
                            let url = new URL(this.apiUrl, window.location.origin);
                            if (this.query.trim()) {{
                                url.searchParams.set('search', this.query);
                            }}
                            if (this.caseTypeField) {{
                                const el = document.querySelector(this.caseTypeField);
                                if (el && el.value) url.searchParams.set('case_type', el.value);
                            }}
                            const resp = await fetch(url, {{ credentials: 'same-origin' }});
                            const data = await resp.json();
                            this.results = Array.isArray(data) ? data : [];
                            this.noResults = this.results.length === 0;
                            this.updateDropdownPosition();
                            this.isOpen = true;
                            this.highlightedIndex = -1;
                        }} catch (e) {{
                            console.error('搜索失败:', e);
                            this.results = [];
                            this.noResults = true;
                        }} finally {{
                            this.isLoading = false;
                        }}
                    }},

                    selectItem(item) {{
                        if (item.disabled) return;
                        const v = item.raw_name || item.name;
                        this.query = v;
                        if (this.$refs.input) {{
                            this.$refs.input.value = v;
                        }}
                        this.isOpen = false;
                    }},

                    onKeydown(e) {{
                        if (!this.isOpen) return;
                        if (e.key === 'ArrowDown') {{
                            e.preventDefault();
                            this.highlightedIndex = Math.min(this.highlightedIndex + 1, this.results.length - 1);
                            this.scrollToHighlighted();
                        }} else if (e.key === 'ArrowUp') {{
                            e.preventDefault();
                            this.highlightedIndex = Math.max(this.highlightedIndex - 1, 0);
                            this.scrollToHighlighted();
                        }} else if (e.key === 'Enter') {{
                            e.preventDefault();
                            if (this.highlightedIndex >= 0 && this.results[this.highlightedIndex]) {{
                                this.selectItem(this.results[this.highlightedIndex]);
                            }}
                        }} else if (e.key === 'Escape') {{
                            this.isOpen = false;
                        }}
                    }},

                    scrollToHighlighted() {{
                        this.$nextTick(() => {{
                            if (!this.$refs.list[Any]) return;
                            const items = this.$refs.list[Any].querySelectorAll('.ac-item');
                            const el = items[this.highlightedIndex];
                            if (el) el.scrollIntoView({{ block: 'nearest' }});
                        }});
                    }},
                }};
            }}
        }})();
        </script>
        <div x-data="{component_name}()" class="ac-wrap">
            {input_html}
            <div x-show="isLoading" class="ac-loading">
                <div class="ac-spinner">
                    <svg class="ac-spin" viewBox="0 0 24 24">
                        {_spinner_circle}
                        {_spinner_path}
                    </svg>
                </div>
            </div>
            <div x-show="isOpen" x-cloak :style="dropdownStyle" class="ac-dropdown">
                <div x-show="noResults && !isLoading" class="ac-empty">
                    {_search_svg}
                    <span>未找到匹配结果</span>
                </div>
                <div x-ref="list[Any]" class="ac-list[Any]">
                    <template x-for="(item, index) in results" :key="item.id || index">
                        <div @click="selectItem(item)" @mouseenter="highlightedIndex = index"
                             x-html="highlightMatch(item.name)"
                             class="ac-item" :class="{{'ac-active': index === highlightedIndex}}"></div>
                    </template>
                </div>
                <div x-show="results.length > 0" class="ac-footer">
                    <span>共 <strong x-text="results.length"></strong> 条结果</span>
                    <span x-show="results.length > 10" class="ac-hint">↑↓ 滚动查看</span>
                </div>
            </div>
        </div>
        """

        container_html = container_html.replace("{component_name}", component_name)
        return format_html("{}", container_html)

    class Media:
        css: ClassVar = {"all": ("cases/css/autocomplete.css",)}
