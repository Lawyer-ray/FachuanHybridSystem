/**
 * 案件建档编号前端交互 Alpine.js 组件
 *
 * 功能：
 * - 监听 is_filed 复选框的变化
 * - 勾选时显示建档编号或"保存后自动生成"
 * - 取消勾选时清空显示（但不修改数据库）
 *
 * Requirements: 6.1, 6.2, 8.1, 8.2, 8.3
 */

/**
 * 建档编号处理器 Alpine.js 组件
 * @returns {Object} Alpine.js 组件数据对象
 */
function filingNumberHandler() {
    return {
        // ========== 状态 ==========
        isArchived: false,           // 是否已建档
        filingNumber: '',            // 当前显示的建档编号
        originalFilingNumber: '',    // 原始建档编号（从数据库读取）

        // ========== 初始化 ==========
        init() {
            console.log('[FilingNumberHandler] 初始化建档编号组件');

            // 获取 DOM 元素
            const checkbox = document.querySelector('#id_is_filed');
            const display = document.querySelector('.field-filing_number_display .readonly');

            if (!checkbox || !display) {
                console.warn('[FilingNumberHandler] 未找到必需的 DOM 元素');
                return;
            }

            // 初始化状态
            this.isArchived = checkbox.checked;
            this.originalFilingNumber = display.textContent.trim();

            // 设置初始显示
            this.updateDisplay();

            // 监听复选框变化
            checkbox.addEventListener('change', (e) => {
                this.handleArchivedChange(e.target.checked);
            });

            console.log('[FilingNumberHandler] 初始化完成', {
                isArchived: this.isArchived,
                originalFilingNumber: this.originalFilingNumber
            });
        },

        // ========== 事件处理 ==========

        /**
         * 处理建档状态变化
         * @param {boolean} checked - 复选框是否勾选
         */
        handleFiledChange(checked) {
            this.isFiled = checked;
            this.updateDisplay();
        },

        /**
         * 更新建档编号显示
         */
        updateDisplay() {
            const display = document.querySelector('.field-filing_number_display .readonly');
            if (!display) return;

            if (this.isArchived) {
                // 勾选：显示编号或"保存后自动生成"
                const hasFilingNumber = this.originalFilingNumber &&
                                       this.originalFilingNumber !== '未生成';

                if (hasFilingNumber) {
                    this.filingNumber = this.originalFilingNumber;
                    display.textContent = this.filingNumber;
                    display.style.fontStyle = 'normal';
                    display.style.color = '';
                } else {
                    this.filingNumber = '保存后自动生成';
                    display.textContent = this.filingNumber;
                    display.style.fontStyle = 'italic';
                    display.style.color = '#666';
                }
            } else {
                // 取消勾选：清空显示
                this.filingNumber = '';
                display.textContent = '未生成';
                display.style.fontStyle = 'normal';
                display.style.color = '';
            }
        }
    };
}

// ========== Alpine.js 组件注册 ==========

// 注册 Alpine.js 组件
document.addEventListener('alpine:init', () => {
    Alpine.data('filingNumberHandler', filingNumberHandler);
    console.log('[FilingNumberHandler] Alpine.js 组件已注册');
});

// 兼容性：如果 Alpine 已经初始化，直接初始化组件
if (typeof Alpine !== 'undefined' && document.readyState !== 'loading') {
    // 手动初始化（用于动态加载的情况）
    const initHandler = filingNumberHandler();
    if (typeof initHandler.init === 'function') {
        initHandler.init();
    }
}
