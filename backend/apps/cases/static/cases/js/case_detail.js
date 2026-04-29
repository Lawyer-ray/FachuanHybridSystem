/**
 * 案件详情页 Alpine.js 组件
 * Requirements: 3.1, 3.6, 3.7, 7.9, 7.10, 7.11
 */
(() => {
    const el = document.querySelector('.case-detail-page');
    if (!el) return;
    if (window.CASE_ID) return;
    const raw = el.getAttribute('data-case-id');
    if (!raw) return;
    const parsed = parseInt(raw, 10);
    if (Number.isFinite(parsed)) window.CASE_ID = parsed;
})();

/**
 * 格式化材料文件名显示
 * 1. 去掉开头的序号（如 1-、2-3-、1-2-3- 等）
 * 2. 去掉括号及括号内的内容，将括号前后拼接
 * @param {string} filename - 原始文件名
 * @returns {string} 格式化后的文件名
 */
function formatMaterialFileName(filename) {
    if (!filename) return '';

    // 1. 去掉开头的序号（支持 1-、1-2-、1-2-3- 等格式）
    let result = filename.replace(/^(\d+-)+/, '');

    // 2. 去掉所有括号及括号内的内容（支持中英文括号）
    // 先处理中文括号
    result = result.replace(/（[^）]*）/g, '');
    // 再处理英文括号
    result = result.replace(/\([^)]*\)/g, '');

    // 3. 清理多余的空格
    result = result.replace(/\s+/g, ' ').trim();

    return result;
}

/**
 * 应用文件名格式化到材料列表
 */
function applyMaterialFileNameFormatting() {
    const fileNameElements = document.querySelectorAll('.material-file-name');
    fileNameElements.forEach(el => {
        // 避免重复处理
        if (el.hasAttribute('data-formatted')) return;

        const originalName = el.textContent || '';
        const formattedName = formatMaterialFileName(originalName);
        if (formattedName && formattedName !== originalName) {
            el.textContent = formattedName;
            // 保存原始文件名到父级 <a> 标签的 title 属性，鼠标悬停时显示
            const parentLink = el.closest('.material-file');
            if (parentLink) {
                parentLink.setAttribute('title', '原始文件名：' + originalName);
            }
        }
        el.setAttribute('data-formatted', 'true');
    });
}

// 页面加载完成后应用格式化
document.addEventListener('DOMContentLoaded', function() {
    applyMaterialFileNameFormatting();

    // 监听 Tab 切换，延迟应用格式化（处理 Alpine.js 的 x-show 延迟渲染）
    const tabButtons = document.querySelectorAll('[data-materials-tab], .detail-tabs button');
    tabButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            setTimeout(applyMaterialFileNameFormatting, 100);
        });
    });
});

function caseDetailApp() {
    return {
        // 当前激活的标签页，从 localStorage 恢复或默认为 'basic'
        activeTab: (() => {
            const saved = localStorage.getItem('caseDetailTab');
            // 'parties' tab已合并到'basic'，回退到'basic'
            return (saved && saved !== 'parties') ? saved : 'basic';
        })(),
        isLoading: false,
        loadingType: null,  // 'folder'
        message: null,
        messageType: 'success',

        // 文档生成按钮状态（从服务端传递）
        canGenerateFolder: window.CAN_GENERATE_FOLDER || false,

        // 案件ID和合同ID
        caseId: window.CASE_ID || null,
        contractId: window.CONTRACT_ID || null,

        // 窄屏标签模式：tab 溢出时自动切换短文字
        tabsCompact: false,
        _tabResizeObserver: null,

        /**
         * 初始化组件
         */
        init() {
            // 监听标签页变化，保存到 localStorage
            this.$watch('activeTab', (value) => {
                localStorage.setItem('caseDetailTab', value);
            });

            window.addEventListener('case-detail-toast', (event) => {
                const detail = (event && event.detail) || {};
                const message = detail.message || '';
                if (!message) return;
                this.showMessage(message, detail.type || 'success');
            });

            // 初始化 tab 溢出检测
            this.$nextTick(() => this._initTabOverflowDetection());
        },

        /**
         * 显示消息提示
         * @param {string} msg - 消息内容
         * @param {string} type - 消息类型 ('success' | 'error')
         */
        showMessage(msg, type = 'success') {
            this.message = msg;
            this.messageType = type;
            setTimeout(() => {
                this.message = null;
            }, 5000);
        },

        /**
         * 获取 CSRF Token
         * @returns {string} CSRF Token
         */
        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        /**
         * 生成文件夹
         * Requirements: 7.10, 7.11
         */
        async generateFolder() {
            if (this.isLoading || !this.canGenerateFolder) return;
            if (!this.caseId) {
                this.showMessage('案件ID不存在', 'error');
                return;
            }

            this.isLoading = true;
            this.loadingType = 'folder';

            try {
                const url = `/api/v1/cases/${this.caseId}/generate-folder`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': this.getCsrfToken(),
                    },
                });

                const contentType = response.headers.get('content-type');

                if (response.ok) {
                    if (contentType && contentType.includes('application/json')) {
                        // JSON 响应 - 文件夹已创建到绑定目录
                        const data = await response.json();
                        if (data.success) {
                            this.showMessage(data.message || '文件夹生成成功', 'success');
                        } else {
                            this.showMessage(data.message || '生成失败', 'error');
                        }
                    } else {
                        // ZIP 文件下载响应
                        const blob = await response.blob();
                        const filename = this.getFilenameFromResponse(response) || '案件文件夹.zip';
                        this.downloadBlob(blob, filename);
                        this.showMessage('文件夹生成成功，正在下载...', 'success');
                    }
                } else {
                    let errorMessage = '生成失败';
                    try {
                        const data = await response.json();
                        errorMessage = data.message || data.detail || errorMessage;
                    } catch (e) {
                        // 无法解析 JSON
                    }
                    this.showMessage(errorMessage, 'error');
                }
            } catch (error) {
                console.error('生成文件夹失败:', error);
                this.showMessage('网络错误，请稍后重试', 'error');
            } finally {
                this.isLoading = false;
                this.loadingType = null;
            }
        },

        /**
         * 从响应头获取文件名
         * @param {Response} response - fetch 响应对象
         * @returns {string|null} 文件名
         */
        getFilenameFromResponse(response) {
            const disposition = response.headers.get('content-disposition');
            if (!disposition) return null;

            // 尝试解析 filename*=UTF-8''xxx 格式
            const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/i);
            if (utf8Match) {
                return decodeURIComponent(utf8Match[1]);
            }

            // 尝试解析 filename="xxx" 格式
            const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (match) {
                return match[1].replace(/['"]/g, '');
            }

            return null;
        },

        /**
         * 下载 Blob 文件
         * @param {Blob} blob - 文件内容
         * @param {string} filename - 文件名
         */
        downloadBlob(blob, filename) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        },

        /**
         * 初始化 tab 溢出检测：用 ResizeObserver 监听 tab-nav 容器，
         * 当完整文字导致溢出时自动切换为短文字模式
         */
        _initTabOverflowDetection() {
            const tabNav = this.$el?.querySelector('.tab-nav');
            if (!tabNav) return;

            const check = () => {
                // 先临时切换到完整文字模式测量
                const wasCompact = this.tabsCompact;
                if (wasCompact) {
                    this.tabsCompact = false;
                    // 等 DOM 更新后再测量
                    this.$nextTick(() => {
                        this.tabsCompact = tabNav.scrollWidth > tabNav.clientWidth + 2;
                    });
                    return;
                }
                this.tabsCompact = tabNav.scrollWidth > tabNav.clientWidth + 2;
            };

            check();

            this._tabResizeObserver = new ResizeObserver(() => check());
            this._tabResizeObserver.observe(tabNav);
        },
    };
}
