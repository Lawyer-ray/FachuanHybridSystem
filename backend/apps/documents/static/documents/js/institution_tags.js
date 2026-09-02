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
                         style="position:absolute;right:10px;top:50%;transform:translateY(-50%);font-size:12px;color:var(--fc-text-muted);">
                        搜索中...
                    </div>
                    <div x-show="isOpen && results.length > 0"
                         x-transition
                         class="ac-dropdown"
                         style="position:absolute;top:100%;left:0;right:0;z-index:1000;margin-top:2px;">
                        <div class="ac-select-all">
                            <label @click.prevent.stop="toggleAllResults()">
                                <input type="checkbox"
                                       :checked="isAllSelected()" />
                                <span>全选当前结果（<span x-text="results.length"></span> 项）</span>
                            </label>
                        </div>
                        <div class="ac-list">
                            <template x-for="(item, index) in results" :key="item.id || index">
                                <div class="ac-item"
                                     :class="{ 'ac-active': index === highlightedIndex }"
                                     @click="selectItem(item)">
                                    <input type="checkbox"
                                           class="ac-item-checkbox"
                                           :checked="isSelected(item.name)"
                                           @click.stop.prevent="toggleItem(item)" />
                                    <span class="ac-item-name" x-text="item.name"></span>
                                </div>
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

                component.isSelected = function (name) {
                    return !!name && this.tags.includes(name);
                };

                component.toggleItem = function (item) {
                    if (!item || !item.name) return;
                    if (this.tags.includes(item.name)) {
                        this.tags = this.tags.filter(function (t) { return t !== item.name; });
                    } else {
                        this.addTag(item.name);
                    }
                    this.syncToHidden();
                    // 勾选/取消时保持下拉打开，便于连续勾选多个
                };

                component.isAllSelected = function () {
                    return this.results.length > 0 &&
                        this.results.every(function (item) {
                            return item && this.tags.includes(item.name);
                        }, this);
                };

                component.toggleAllResults = function () {
                    if (!this.results || this.results.length === 0) return;
                    if (this.isAllSelected()) {
                        // 已全选 -> 取消选择这些结果（不清空已勾选的其余机构）
                        var names = this.results.map(function (r) { return r.name; });
                        var removing = new Set(names);
                        this.tags = this.tags.filter(function (t) { return !removing.has(t); });
                    } else {
                        // 未全选 -> 全部加入，已存在的会自动去重
                        var self = this;
                        this.results.forEach(function (item) {
                            if (item && item.name) self.addTag(item.name);
                        });
                    }
                    this.syncToHidden();
                    if (this.tags.length > 0) {
                        this.query = '';
                    }
                    // 全选或取消选择后关闭下拉，方便查看已生成的标签
                    this.closeDropdown();
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
