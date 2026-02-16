/**
 * 案由和主管机关自动补全组件
 * 使用Alpine.js实现的智能自动补全功能
 */

/**
 * 创建自动补全组件
 * @param {Object} config 配置对象
 * @param {string} config.apiUrl API接口URL
 * @param {string} config.fieldName 字段名称
 * @param {string} config.caseTypeField 案件类型字段选择器（可选，仅案由字段需要）
 * @param {string} config.placeholder 输入框占位符
 * @param {number} config.debounceMs 防抖延迟时间（毫秒）
 * @returns {Object} Alpine.js组件对象
 */
function autocompleteComponent(config) {
    return {
        // 数据属性
        query: '',
        results: [],
        isOpen: false,
        highlightedIndex: -1,
        isLoading: false,
        error: null,

        // 配置属性
        apiUrl: config.apiUrl,
        fieldName: config.fieldName,
        caseTypeField: config.caseTypeField || null,
        placeholder: config.placeholder || '请输入搜索内容...',
        debounceMs: config.debounceMs || 300,

        // 内部属性
        debounceTimer: null,
        currentCaseType: null,

        /**
         * 组件初始化
         */
        init() {
            // 监听案件类型变化（仅案由字段需要）
            if (this.caseTypeField) {
                this.watchCaseTypeChange();
            }

            // 点击外部关闭下拉菜单
            document.addEventListener('click', (e) => {
                if (!this.$el.contains(e.target)) {
                    this.close();
                }
            });
        },

        /**
         * 监听案件类型变化
         */
        watchCaseTypeChange() {
            const caseTypeElement = document.querySelector(this.caseTypeField);
            if (caseTypeElement) {
                // 初始化当前案件类型
                this.currentCaseType = caseTypeElement.value;

                // 监听变化
                caseTypeElement.addEventListener('change', () => {
                    const newCaseType = caseTypeElement.value;
                    if (newCaseType !== this.currentCaseType) {
                        this.currentCaseType = newCaseType;
                        this.onCaseTypeChange();
                    }
                });
            }
        },

        /**
         * 案件类型变化处理
         */
        onCaseTypeChange() {
            // 清空当前输入和结果
            this.query = '';
            this.results = [];
            this.close();

            // 更新输入框的值
            const inputElement = this.$refs.input;
            if (inputElement) {
                inputElement.value = '';
            }

            // 如果是破产类型，禁用自动补全
            if (this.currentCaseType === 'bankruptcy') {
                this.disable();
            } else {
                this.enable();
            }
        },

        /**
         * 禁用自动补全
         */
        disable() {
            const inputElement = this.$refs.input;
            if (inputElement) {
                inputElement.setAttribute('data-autocomplete-disabled', 'true');
            }
        },

        /**
         * 启用自动补全
         */
        enable() {
            const inputElement = this.$refs.input;
            if (inputElement) {
                inputElement.removeAttribute('data-autocomplete-disabled');
            }
        },

        /**
         * 输入事件处理
         */
        onInput(event) {
            const value = event.target.value;
            this.query = value;

            // 检查是否禁用
            if (event.target.hasAttribute('data-autocomplete-disabled')) {
                return;
            }

            // 清除之前的定时器
            if (this.debounceTimer) {
                clearTimeout(this.debounceTimer);
            }

            // 如果输入为空，关闭下拉菜单
            if (!value.trim()) {
                this.close();
                return;
            }

            // 防抖搜索
            this.debounceTimer = setTimeout(() => {
                this.search(value);
            }, this.debounceMs);
        },

        /**
         * 执行搜索
         */
        async search(query) {
            if (!query.trim()) {
                this.close();
                return;
            }

            this.isLoading = true;
            this.error = null;

            try {
                const url = this.buildApiUrl(query);
                const response = await fetch(url, { credentials: 'same-origin' });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();
                this.results = Array.isArray(data) ? data : [];
                this.highlightedIndex = -1;
                this.isOpen = this.results.length > 0;

                // 如果没有结果，显示提示
                if (this.results.length === 0) {
                    this.results = [{ id: null, name: '无匹配结果', disabled: true }];
                    this.isOpen = true;
                }

            } catch (error) {
                console.error('自动补全搜索失败:', error);
                this.error = '搜索失败，请稍后重试';
                this.results = [{ id: null, name: this.error, disabled: true }];
                this.isOpen = true;
            } finally {
                this.isLoading = false;
            }
        },

        /**
         * 构建API URL
         */
        buildApiUrl(query) {
            const url = new URL(this.apiUrl, window.location.origin);
            url.searchParams.set('search', query);

            // 如果是案由字段，添加案件类型参数
            if (this.caseTypeField && this.currentCaseType) {
                url.searchParams.set('case_type', this.currentCaseType);
            }

            return url.toString();
        },

        /**
         * 选择项目
         */
        selectItem(item) {
            if (item.disabled) {
                return;
            }

            this.query = item.raw_name || item.name;
            const inputElement = this.$refs.input;
            if (inputElement) {
                inputElement.value = item.raw_name || item.name;
                // 触发change事件，确保Django表单能够识别
                inputElement.dispatchEvent(new Event('change', { bubbles: true }));
            }

            this.close();
        },

        /**
         * 键盘事件处理
         */
        handleKeydown(event) {
            if (!this.isOpen) {
                return;
            }

            const validResults = this.results.filter(item => !item.disabled);

            switch (event.key) {
                case 'ArrowDown':
                    event.preventDefault();
                    this.highlightedIndex = Math.min(
                        this.highlightedIndex + 1,
                        validResults.length - 1
                    );
                    break;

                case 'ArrowUp':
                    event.preventDefault();
                    this.highlightedIndex = Math.max(this.highlightedIndex - 1, -1);
                    break;

                case 'Enter':
                    event.preventDefault();
                    if (this.highlightedIndex >= 0 && this.highlightedIndex < validResults.length) {
                        this.selectItem(validResults[this.highlightedIndex]);
                    }
                    break;

                case 'Escape':
                    event.preventDefault();
                    this.close();
                    break;
            }
        },

        /**
         * 关闭下拉菜单
         */
        close() {
            this.isOpen = false;
            this.highlightedIndex = -1;
            this.error = null;
        },

        /**
         * 获取项目的CSS类
         */
        getItemClass(index) {
            const item = this.results[index];
            const classes = ['autocomplete-item'];

            if (item.disabled) {
                classes.push('disabled');
            }

            // 计算高亮索引（排除禁用项）
            const validResults = this.results.filter(item => !item.disabled);
            const validIndex = validResults.indexOf(item);

            if (validIndex === this.highlightedIndex) {
                classes.push('highlighted');
            }

            return classes.join(' ');
        }
    };
}

/**
 * 初始化案由自动补全
 * @param {string} inputSelector 输入框选择器
 * @param {string} caseTypeSelector 案件类型选择器
 */
function initCauseAutocomplete(inputSelector, caseTypeSelector) {
    const inputElement = document.querySelector(inputSelector);
    if (!inputElement) {
        console.warn('案由输入框未找到:', inputSelector);
        return;
    }

    // 创建自动补全容器
    const container = createAutocompleteContainer(inputElement, {
        apiUrl: '/api/v1/cases/causes-data',
        fieldName: 'cause_of_action',
        caseTypeField: caseTypeSelector,
        placeholder: '请输入案由关键词...'
    });

    // 替换原输入框
    inputElement.parentNode.replaceChild(container, inputElement);
}

/**
 * 初始化法院自动补全
 * @param {string} inputSelector 输入框选择器
 */
function initCourtAutocomplete(inputSelector) {
    const inputElement = document.querySelector(inputSelector);
    if (!inputElement) {
        console.warn('法院输入框未找到:', inputSelector);
        return;
    }

    // 创建自动补全容器
    const container = createAutocompleteContainer(inputElement, {
        apiUrl: '/api/v1/cases/courts-data',
        fieldName: 'supervising_authority',
        placeholder: '请输入法院名称...'
    });

    // 替换原输入框
    inputElement.parentNode.replaceChild(container, inputElement);
}

/**
 * 创建自动补全容器
 * @param {HTMLElement} originalInput 原始输入框
 * @param {Object} config 配置对象
 * @returns {HTMLElement} 自动补全容器
 */
function createAutocompleteContainer(originalInput, config) {
    const container = document.createElement('div');
    container.className = 'autocomplete-container';
    container.setAttribute('x-data', `autocompleteComponent(${JSON.stringify(config)})`);
    container.setAttribute('x-init', 'init()');

    // 复制原输入框的属性
    const inputAttributes = {
        type: originalInput.type || 'text',
        name: originalInput.name,
        id: originalInput.id,
        value: originalInput.value,
        class: originalInput.className,
        placeholder: config.placeholder,
        required: originalInput.required,
        maxlength: originalInput.maxLength > 0 ? originalInput.maxLength : null
    };

    // 构建HTML
    container.innerHTML = `
        <div class="autocomplete-wrapper">
            <input
                x-ref="input"
                ${Object.entries(inputAttributes)
                    .filter(([key, value]) => value !== null && value !== undefined)
                    .map(([key, value]) => `${key}="${value}"`)
                    .join(' ')}
                x-model="query"
                @input="onInput($event)"
                @keydown="handleKeydown($event)"
                @focus="query && query.trim() && search(query)"
                autocomplete="off"
            />
            <div x-show="isLoading" class="autocomplete-loading">
                搜索中...
            </div>
            <div
                x-show="isOpen"
                x-transition:enter="transition ease-out duration-100"
                x-transition:enter-start="opacity-0 scale-95"
                x-transition:enter-end="opacity-100 scale-100"
                x-transition:leave="transition ease-in duration-75"
                x-transition:leave-start="opacity-100 scale-100"
                x-transition:leave-end="opacity-0 scale-95"
                class="autocomplete-dropdown"
            >
                <template x-for="(item, index) in results" :key="item.id || index">
                    <div
                        :class="getItemClass(index)"
                        @click="selectItem(item)"
                        x-text="item.name"
                    ></div>
                </template>
            </div>
        </div>
    `;

    return container;
}

// 导出函数供全局使用 - 必须在最前面，确保 x-data 能找到
window.autocompleteComponent = autocompleteComponent;
window.initCauseAutocomplete = initCauseAutocomplete;
window.initCourtAutocomplete = initCourtAutocomplete;

// 注册 Alpine.js 组件
(function() {
    function registerComponent() {
        if (typeof Alpine !== 'undefined' && Alpine.data) {
            Alpine.data('autocompleteComponent', autocompleteComponent);
            console.log('[autocomplete] Alpine组件已注册');
        }
    }

    // 方式1: 如果 Alpine 已经存在，直接注册
    if (typeof Alpine !== 'undefined') {
        registerComponent();
    }

    // 方式2: 监听 alpine:init 事件
    document.addEventListener('alpine:init', registerComponent);

    // 方式3: DOM 加载完成后再次尝试注册
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(registerComponent, 0);
    });
})();
