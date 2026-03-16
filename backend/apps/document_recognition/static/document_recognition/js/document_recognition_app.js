/**
 * 法院文书智能识别 Alpine.js 组件
 * 功能：文件拖拽上传、文档识别、结果展示、案件绑定
 * 替代原有的 document_recognition.js
 * Requirements: 4.1, 8.1, 8.2, 8.3
 */

function documentRecognitionApp() {
    return {
        // ========== 状态 ==========
        state: 'idle',              // 当前状态: 'idle' | 'loading' | 'result' | 'error'
        isDragOver: false,          // 拖拽状态
        isUploading: false,         // 上传状态
        uploadProgress: 0,          // 上传进度 (0-100)
        loadingText: '正在上传文件...', // 加载提示文本

        // 识别结果
        result: null,               // 完整识别结果
        taskId: null,               // 任务 ID

        // 案件选择
        selectedCaseData: null,     // 选中的案件数据
        allCasesLoaded: false,      // 是否已加载全部案件
        caseSearchQuery: '',        // 案件搜索关键词
        caseList: [],               // 案件列表
        showCaseDropdown: false,    // 是否显示案件下拉列表
        isSearchingCases: false,    // 是否正在搜索案件
        isBindingCase: false,       // 是否正在绑定案件

        // 编辑状态
        editingField: null,         // 当前编辑的字段: 'caseNumber' | 'keyTime' | null
        editCaseNumber: '',         // 编辑中的案号
        editKeyTime: '',            // 编辑中的关键时间
        showRawText: false,         // 是否显示原始文本

        // 错误信息
        errorMessage: '',           // 错误信息

        // 允许的文件类型
        allowedExtensions: ['.pdf', '.jpg', '.jpeg', '.png'],

        // 文书类型映射
        docTypeLabels: {
            'summons': '传票',
            'execution_ruling': '执行裁定书',
            'unknown': '未知'
        },
        docTypeClasses: {
            'summons': 'tag-blue',
            'execution_ruling': 'tag-purple',
            'unknown': 'tag-gray'
        },

        // 提取方式映射
        extractionMethodLabels: {
            'regex': '正则表达式',
            'ollama': 'AI模型',
            'ocr': 'OCR识别',
            'pdf_direct': 'PDF直接提取',
            'text_extraction': '文本提取'
        },

        // ========== 初始化 ==========
        init() {
            console.log('文档识别 Alpine 组件已初始化');

            // 监听点击事件，关闭下拉列表
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.search-box')) {
                    this.showCaseDropdown = false;
                }
            });
        },

        // ========== 拖拽事件处理 ==========

        /**
         * 拖拽进入/悬停处理
         */
        handleDragOver(e) {
            e.preventDefault();
            e.stopPropagation();
            e.dataTransfer.dropEffect = 'copy';
            this.isDragOver = true;
        },

        /**
         * 拖拽离开处理
         */
        handleDragLeave(e) {
            e.preventDefault();
            e.stopPropagation();
            // 只有当鼠标真正离开上传区域时才移除样式
            const uploadZone = e.currentTarget;
            if (!uploadZone.contains(e.relatedTarget)) {
                this.isDragOver = false;
            }
        },

        /**
         * 文件拖放处理
         */
        handleDrop(e) {
            e.preventDefault();
            e.stopPropagation();
            this.isDragOver = false;

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.uploadFile(files[0]);
            }
        },

        /**
         * 文件选择处理
         */
        handleFileSelect(e) {
            if (e.target.files.length > 0) {
                this.uploadFile(e.target.files[0]);
            }
        },

        // ========== 文件上传 ==========

        /**
         * 上传文件并开始识别
         * @param {File} file - 要上传的文件
         */
        async uploadFile(file) {
            // 验证文件类型
            const fileExt = '.' + file.name.split('.').pop().toLowerCase();
            if (!this.allowedExtensions.includes(fileExt)) {
                this.showError(`不支持的文件格式: ${fileExt}，请上传 PDF 或图片文件`);
                return;
            }

            // 验证文件大小 (最大 20MB)
            const maxSize = 20 * 1024 * 1024;
            if (file.size > maxSize) {
                this.showError('文件过大，请上传小于 20MB 的文件');
                return;
            }

            // 显示加载状态
            this.showState('loading');
            this.isUploading = true;
            this.uploadProgress = 0;
            this.loadingText = '正在上传文件...';

            // 构建表单数据
            const formData = new FormData();
            formData.append('file', file);

            try {
                // 使用 XMLHttpRequest 以支持上传进度
                const response = await this.uploadWithProgress(formData);
                const data = JSON.parse(response);

                // 开始轮询任务状态
                this.isUploading = false;
                this.uploadProgress = 100;
                this.loadingText = '正在识别文书...';
                await this.pollTaskStatus(data.task_id);

            } catch (error) {
                console.error('上传错误:', error);
                this.showError(error.message || '上传失败，请重试');
            }
        },

        /**
         * 带进度的文件上传
         * @param {FormData} formData - 表单数据
         * @returns {Promise<string>} 响应文本
         */
        uploadWithProgress(formData) {
            return new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();

                // 上传进度事件
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        this.uploadProgress = Math.round((e.loaded / e.total) * 100);
                        this.loadingText = `正在上传文件... ${this.uploadProgress}%`;
                    }
                });

                // 完成事件
                xhr.addEventListener('load', () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve(xhr.responseText);
                    } else {
                        try {
                            const data = JSON.parse(xhr.responseText);
                            reject(new Error(data.detail || '上传失败'));
                        } catch {
                            reject(new Error('上传失败'));
                        }
                    }
                });

                // 错误事件
                xhr.addEventListener('error', () => {
                    reject(new Error('网络错误，请检查网络连接'));
                });

                // 超时事件
                xhr.addEventListener('timeout', () => {
                    reject(new Error('上传超时，请重试'));
                });

                // 配置请求
                xhr.open('POST', '/api/v1/document-recognition/court-document/recognize');
                xhr.setRequestHeader('X-CSRFToken', this.getCsrfToken());
                xhr.timeout = 60000; // 60秒超时
                xhr.send(formData);
            });
        },

        /**
         * 轮询任务状态
         * @param {string} taskId - 任务 ID
         */
        async pollTaskStatus(taskId) {
            this.taskId = taskId;
            let attempts = 0;
            const maxAttempts = 60;

            const poll = async () => {
                attempts++;

                try {
                    const response = await fetch(`/api/v1/document-recognition/court-document/task/${taskId}`);
                    const data = await response.json();

                    if (!response.ok) {
                        throw new Error(data.detail || '获取状态失败');
                    }

                    if (data.status === 'success' || data.status === 'failed') {
                        if (data.status === 'success') {
                            this.result = data;
                            this.showResult();
                        } else {
                            this.showError(data.error_message || '识别失败');
                        }
                    } else if (attempts >= maxAttempts) {
                        this.showError('识别超时');
                    } else {
                        // 更新加载提示
                        const statusTexts = {
                            'pending': '任务排队中...',
                            'processing': '正在识别...',
                            'extracting': '正在提取信息...',
                            'binding': '正在绑定...'
                        };
                        this.loadingText = statusTexts[data.status] || '正在处理...';

                        // 继续轮询
                        setTimeout(poll, 3000);
                    }
                } catch (error) {
                    if (attempts >= maxAttempts) {
                        this.showError(error.message);
                    } else {
                        setTimeout(poll, 3000);
                    }
                }
            };

            await poll();
        },

        // ========== 状态管理 ==========

        /**
         * 切换显示状态
         * @param {string} newState - 新状态
         */
        showState(newState) {
            this.state = newState;
        },

        /**
         * 显示错误状态
         * @param {string} message - 错误信息
         */
        showError(message) {
            this.errorMessage = message;
            this.isUploading = false;
            this.uploadProgress = 0;
            this.showState('error');
        },

        /**
         * 重试上传（从错误状态恢复）
         */
        retry() {
            this.errorMessage = '';
            this.showState('idle');
        },

        /**
         * 显示识别结果
         */
        showResult() {
            const rec = this.result.recognition || {};

            // 初始化编辑字段
            this.editCaseNumber = rec.case_number || '';
            if (rec.key_time) {
                this.editKeyTime = this.isoToLocal(rec.key_time);
            }

            // 初始化案件搜索
            if (!this.result.binding || !this.result.binding.success) {
                if (rec.case_number) {
                    this.caseSearchQuery = rec.case_number;
                    this.searchCases();
                }
            }

            this.showState('result');
        },

        /**
         * 重置页面到初始状态
         */
        resetPage() {
            this.result = null;
            this.taskId = null;
            this.selectedCaseData = null;
            this.allCasesLoaded = false;
            this.caseSearchQuery = '';
            this.caseList = [];
            this.showCaseDropdown = false;
            this.editingField = null;
            this.editCaseNumber = '';
            this.editKeyTime = '';
            this.showRawText = false;
            this.errorMessage = '';
            this.isUploading = false;
            this.uploadProgress = 0;
            this.showState('idle');
        },

        // ========== 结果显示辅助方法 ==========

        /**
         * 获取文书类型标签
         * @returns {string} 文书类型中文标签
         */
        getDocTypeLabel() {
            const type = this.result?.recognition?.document_type;
            return this.docTypeLabels[type] || '未知';
        },

        /**
         * 获取文书类型样式类
         * @returns {string} CSS 类名
         */
        getDocTypeClass() {
            const type = this.result?.recognition?.document_type;
            return this.docTypeClasses[type] || 'tag-gray';
        },

        /**
         * 获取案号显示文本
         * @returns {string} 案号
         */
        getCaseNumber() {
            return this.result?.recognition?.case_number || '未识别';
        },

        /**
         * 获取关键时间显示文本
         * @returns {string} 格式化后的时间
         */
        getKeyTime() {
            const keyTime = this.result?.recognition?.key_time;
            if (!keyTime) return '未识别';
            return new Date(keyTime).toLocaleString('zh-CN');
        },

        /**
         * 获取置信度百分比
         * @returns {number} 置信度百分比
         */
        getConfidencePercent() {
            const confidence = this.result?.recognition?.confidence || 0;
            return Math.round(confidence * 100);
        },

        /**
         * 获取置信度样式类
         * @returns {string} CSS 类名
         */
        getConfidenceClass() {
            const confidence = this.result?.recognition?.confidence || 0;
            if (confidence >= 0.8) return 'high';
            if (confidence >= 0.5) return 'medium';
            return 'low';
        },

        /**
         * 获取置信度标签样式类
         * @returns {string} CSS 类名
         */
        getConfidenceTagClass() {
            const confidence = this.result?.recognition?.confidence || 0;
            if (confidence >= 0.8) return 'tag-green';
            if (confidence >= 0.5) return 'tag-yellow';
            return 'tag-red';
        },

        /**
         * 获取提取方式标签
         * @returns {string} 提取方式中文标签
         */
        getExtractionMethod() {
            const method = this.result?.recognition?.extraction_method;
            return this.extractionMethodLabels[method] || '未知';
        },

        /**
         * 获取原始文本
         * @returns {string} 原始文本
         */
        getRawText() {
            return this.result?.recognition?.raw_text || '无原始文本';
        },

        /**
         * 是否已绑定案件
         * @returns {boolean}
         */
        isBound() {
            return this.result?.binding?.success === true;
        },

        /**
         * 获取绑定状态标签
         * @returns {Object} { text, class }
         */
        getBindingStatus() {
            if (this.result?.binding?.success) {
                return { text: '已绑定', class: 'tag-green' };
            }
            if (this.result?.binding?.error) {
                return { text: this.result.binding.error, class: 'tag-red' };
            }
            return { text: '待绑定', class: 'tag-yellow' };
        },

        /**
         * 获取绑定的案件名称
         * @returns {string}
         */
        getBoundCaseName() {
            return this.result?.binding?.case_name || '-';
        },

        /**
         * 获取绑定的案件 ID
         * @returns {string}
         */
        getBoundCaseId() {
            return this.result?.binding?.case_id || '-';
        },

        /**
         * 获取绑定的日志 ID
         * @returns {string}
         */
        getBoundLogId() {
            return this.result?.binding?.case_log_id || '-';
        },

        /**
         * 获取案件详情链接
         * @returns {string}
         */
        getViewCaseLink() {
            const caseId = this.result?.binding?.case_id;
            return caseId ? `/admin/cases/case/${caseId}/change/` : '#';
        },

        /**
         * 获取任务详情链接
         * @returns {string}
         */
        getTaskDetailLink() {
            return this.taskId ? `/admin/document_recognition/documentrecognitiontask/${this.taskId}/change/` : '#';
        },

        /**
         * 是否显示案件选择器
         * @returns {boolean}
         */
        showCaseSelector() {
            return !this.isBound();
        },

        // ========== 编辑功能 ==========

        /**
         * 切换编辑状态
         * @param {string} field - 字段名 ('caseNumber' | 'keyTime')
         */
        toggleEdit(field) {
            if (this.editingField === field) {
                this.editingField = null;
            } else {
                this.editingField = field;
            }
        },

        /**
         * 取消编辑
         * @param {string} field - 字段名
         */
        cancelEdit(field) {
            this.editingField = null;
            // 恢复原值
            if (field === 'caseNumber') {
                this.editCaseNumber = this.result?.recognition?.case_number || '';
            } else if (field === 'keyTime') {
                const keyTime = this.result?.recognition?.key_time;
                this.editKeyTime = keyTime ? this.isoToLocal(keyTime) : '';
            }
        },

        /**
         * 保存编辑
         * @param {string} field - 字段名
         */
        async saveEdit(field) {
            if (!this.taskId) return;

            const payload = {};
            if (field === 'caseNumber') {
                payload.case_number = this.editCaseNumber;
            } else if (field === 'keyTime') {
                if (this.editKeyTime) {
                    payload.key_time = new Date(this.editKeyTime).toISOString();
                }
            }

            try {
                const response = await fetch(`/api/v1/document-recognition/court-document/task/${this.taskId}/update-info`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || '保存失败');
                }

                // 更新本地数据
                if (field === 'caseNumber') {
                    this.result.recognition.case_number = payload.case_number;
                } else if (field === 'keyTime' && payload.key_time) {
                    this.result.recognition.key_time = payload.key_time;
                }

                this.editingField = null;

            } catch (error) {
                alert('保存失败: ' + error.message);
            }
        },

        // ========== 案件搜索和绑定 ==========

        /**
         * 搜索案件（防抖）
         */
        searchCasesDebounced() {
            clearTimeout(this._searchTimeout);
            this.allCasesLoaded = false;
            this._searchTimeout = setTimeout(() => {
                this.searchCases();
            }, 300);
        },

        /**
         * 搜索案件
         */
        async searchCases() {
            const query = this.caseSearchQuery;

            if (!query || query.length < 2) {
                this.caseList = [];
                this.showCaseDropdown = true;
                return;
            }

            this.isSearchingCases = true;
            this.showCaseDropdown = true;

            try {
                // 使用文书识别专用的案件搜索 API
                const response = await fetch(`/api/v1/document-recognition/court-document/search-cases?q=${encodeURIComponent(query)}&limit=10`);

                if (!response.ok) {
                    throw new Error('搜索失败');
                }

                this.caseList = await response.json();

            } catch (error) {
                console.error('搜索案件失败:', error);
                this.caseList = [];
            } finally {
                this.isSearchingCases = false;
            }
        },

        /**
         * 切换下拉列表显示
         */
        toggleDropdown() {
            if (this.showCaseDropdown && this.allCasesLoaded) {
                this.showCaseDropdown = false;
            } else {
                this.loadAllCases();
            }
        },

        /**
         * 加载全部在办案件
         */
        async loadAllCases() {
            this.isSearchingCases = true;
            this.showCaseDropdown = true;

            try {
                // 使用文书识别专用的案件搜索 API（空查询返回最近案件）
                const response = await fetch('/api/v1/document-recognition/court-document/search-cases?q=&limit=20');

                if (!response.ok) {
                    throw new Error('加载失败');
                }

                this.caseList = await response.json();
                this.allCasesLoaded = true;

            } catch (error) {
                console.error('加载案件失败:', error);
                this.caseList = [];
            } finally {
                this.isSearchingCases = false;
            }
        },

        /**
         * 获取案件的案号显示
         * @param {Object} caseItem - 案件对象
         * @returns {string} 案号
         */
        getCaseItemNumber(caseItem) {
            // search-cases API 返回的 case_numbers 是字符串数组
            if (caseItem.case_numbers && caseItem.case_numbers.length > 0) {
                return caseItem.case_numbers[0];
            }
            if (caseItem.case_number) {
                return caseItem.case_number;
            }
            return '案件' + caseItem.id;
        },

        /**
         * 选择案件
         * @param {Object} caseItem - 案件对象
         */
        selectCase(caseItem) {
            this.selectedCaseData = {
                id: caseItem.id,
                name: caseItem.name,
                case_number: this.getCaseItemNumber(caseItem),
                current_stage: caseItem.current_stage
            };
            this.caseSearchQuery = this.selectedCaseData.case_number || this.selectedCaseData.name;
            this.showCaseDropdown = false;
        },

        /**
         * 绑定案件
         */
        async bindCase() {
            if (!this.selectedCaseData || !this.taskId) return;

            this.isBindingCase = true;

            try {
                const response = await fetch(`/api/v1/document-recognition/court-document/task/${this.taskId}/bind`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({ case_id: this.selectedCaseData.id })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || '绑定失败');
                }

                // 更新绑定状态
                this.result.binding = {
                    success: data.success,
                    case_id: data.case_id,
                    case_name: data.case_name,
                    case_log_id: data.case_log_id
                };

            } catch (error) {
                this.result.binding = { error: error.message };
            } finally {
                this.isBindingCase = false;
            }
        },

        // ========== 工具方法 ==========

        /**
         * 获取 CSRF Token
         * @returns {string} CSRF Token
         */
        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        /**
         * ISO 时间转本地时间格式（用于 datetime-local input）
         * @param {string} isoString - ISO 时间字符串
         * @returns {string} 本地时间格式
         */
        isoToLocal(isoString) {
            if (!isoString) return '';
            const d = new Date(isoString);
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            const hours = String(d.getHours()).padStart(2, '0');
            const minutes = String(d.getMinutes()).padStart(2, '0');
            return `${year}-${month}-${day}T${hours}:${minutes}`;
        },

        /**
         * 处理搜索框获得焦点
         */
        handleSearchFocus() {
            if (this.caseList.length > 0) {
                this.showCaseDropdown = true;
            }
        }
    };
}
