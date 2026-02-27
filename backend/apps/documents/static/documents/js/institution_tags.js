/**
 * 适用机构标签输入组件
 * 支持自由输入和法院名称搜索自动补全
 * 依赖: Alpine.js (全局已引入), autocomplete.js (法院搜索API)
 */
(function () {
    'use strict';

    const API_URL = '/api/v1/cases/courts-data';
    const DEBOUNCE_MS = 300;

    function initInstitutionTags() {
        const hiddenInput = document.getElementById('id_applicable_institutions_field');
        if (!hiddenInput) return;

        // 避免重复初始化
        if (hiddenInput.dataset.initialized === 'true') return;
        hiddenInput.dataset.initialized = 'true';

        // 找到隐藏字段所在的 form-row
        const formRow = hiddenInput.closest('.form-row');
        if (!formRow) return;

        // 解析已有数据
        let existingTags = [];
        try {
            existingTags = JSON.parse(hiddenInput.value || '[]');
        } catch (e) {
            existingTags = [];
        }

        // 创建组件容器
        const container = document.createElement('div');
        container.className = 'institution-tags-component';
        container.setAttribute('x-data', JSON.stringify({
            tags: existingTags,
            query: '',
            results: [],
            isOpen: false,
            highlightedIndex: -1,
            isLoading: false,
            debounceTimer: null
        }));

        container.innerHTML = `
            <div class="institution-tags-wrapper">
                <div class="institution-tags-list" x-ref="tagsList">
                    <template x-for="(tag, idx) in tags" :key="idx">
                        <span class="institution-tag">
                            <span x-text="tag"></span>
                            <button type="button" class="institution-tag-remove"
                                    @click.prevent="removeTag(idx)"
                                    title="删除">&times;</button>
                        </span>
                    </template>
                </div>
                <div class="institution-input-wrapper" style="position:relative;">
                    <input type="text"
                           class="institution-input vTextField"
                           x-model="query"
                           @input="onInput($event)"
                           @keydown.enter.prevent="addCurrentQuery()"
                           @keydown.arrow-down.prevent="moveHighlight(1)"
                           @keydown.arrow-up.prevent="moveHighlight(-1)"
                           @keydown.escape="closeDropdown()"
                           placeholder="输入机构名称后回车添加，或搜索法院..."
                           autocomplete="off" />
                    <div x-show="isLoading" class="autocomplete-loading"
                         style="position:absolute;right:10px;top:50%;transform:translateY(-50%);font-size:12px;color:#9ca3af;">
                        搜索中...
                    </div>
                    <div x-show="isOpen && results.length > 0"
                         x-transition
                         class="ac-dropdown"
                         style="position:absolute;top:100%;left:0;right:0;z-index:1000;margin-top:2px;">
                        <div class="ac-list">
                            <template x-for="(item, index) in results" :key="item.id || index">
                                <div class="ac-item"
                                     :class="{ 'ac-active': index === highlightedIndex }"
                                     @click="selectItem(item)"
                                     x-text="item.name"></div>
                            </template>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // 插入到 form-row 中隐藏字段之后
        hiddenInput.parentNode.insertBefore(container, hiddenInput.nextSibling);

        // 用 Alpine 初始化后绑定方法
        // Alpine.js 会自动发现 x-data 并初始化
        // 我们需要在 Alpine 初始化后注入方法
        requestAnimationFrame(function () {
            if (typeof Alpine === 'undefined') return;

            Alpine.nextTick(function () {
                const component = Alpine.$data(container);
                if (!component) return;

                component.syncToHidden = function () {
                    hiddenInput.value = JSON.stringify(this.tags);
                    hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
                };

                component.addTag = function (name) {
                    const trimmed = name.trim();
                    if (!trimmed) return;
                    if (this.tags.includes(trimmed)) return;
                    this.tags.push(trimmed);
                    this.syncToHidden();
                };

                component.removeTag = function (idx) {
                    this.tags.splice(idx, 1);
                    this.syncToHidden();
                };

                component.addCurrentQuery = function () {
                    if (this.highlightedIndex >= 0 && this.highlightedIndex < this.results.length) {
                        this.selectItem(this.results[this.highlightedIndex]);
                    } else if (this.query.trim()) {
                        this.addTag(this.query);
                        this.query = '';
                        this.closeDropdown();
                    }
                };

                component.selectItem = function (item) {
                    if (item && item.name) {
                        this.addTag(item.name);
                        this.query = '';
                        this.closeDropdown();
                    }
                };

                component.closeDropdown = function () {
                    this.isOpen = false;
                    this.highlightedIndex = -1;
                };

                component.moveHighlight = function (dir) {
                    if (!this.isOpen || this.results.length === 0) return;
                    this.highlightedIndex = Math.max(-1,
                        Math.min(this.results.length - 1, this.highlightedIndex + dir));
                };

                component.onInput = function () {
                    const val = this.query.trim();
                    if (this.debounceTimer) clearTimeout(this.debounceTimer);
                    if (!val) {
                        this.closeDropdown();
                        return;
                    }
                    this.debounceTimer = setTimeout(() => this.search(val), DEBOUNCE_MS);
                };

                component.search = async function (q) {
                    if (!q) return;
                    this.isLoading = true;
                    try {
                        const url = new URL(API_URL, window.location.origin);
                        url.searchParams.set('search', q);
                        const resp = await fetch(url.toString(), { credentials: 'same-origin' });
                        if (!resp.ok) throw new Error('HTTP ' + resp.status);
                        const data = await resp.json();
                        this.results = Array.isArray(data) ? data : [];
                        this.highlightedIndex = -1;
                        this.isOpen = this.results.length > 0;
                    } catch (e) {
                        console.error('机构搜索失败:', e);
                        this.results = [];
                        this.isOpen = false;
                    } finally {
                        this.isLoading = false;
                    }
                };

                // 点击外部关闭
                document.addEventListener('click', function (e) {
                    if (!container.contains(e.target)) {
                        component.closeDropdown();
                    }
                });

                // 同步初始数据
                component.syncToHidden();
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initInstitutionTags);
    } else {
        initInstitutionTags();
    }
})();
