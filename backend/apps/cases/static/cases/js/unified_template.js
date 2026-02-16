/**
 * 统一模板生成 Alpine.js 组件
 *
 * 在独立 Tab 中展示，使用 function_code 识别特殊模板
 *
 * Requirements: 2.2, 6.1
 */
function unifiedTemplateApp(config) {
    return {
        // 配置
        caseId: config.caseId,
        apiBasePath: config.apiBasePath || '/api/v1/cases',
        templatesElementId: config.templatesElementId || '',
        legalEntitiesJson: typeof config.legalEntitiesJson === 'string' ? config.legalEntitiesJson : '[]',
        ourPartiesJson: typeof config.ourPartiesJson === 'string' ? config.ourPartiesJson : '[]',

        // 状态
        templates: [],
        isLoading: false,
        generatingTemplateId: null,
        message: '',
        messageType: 'success',

        // 法人选择对话框状态
        isLegalEntityDialogOpen: false,
        legalEntities: [],
        selectedLegalEntityIds: [],
        pendingTemplate: null,

        // 授权委托书对话框状态
        isPoaDialogOpen: false,
        ourParties: [],
        selectedOurPartyIds: [],
        poaMode: '',

        /**
         * 初始化组件
         */
        init() {
            // 从 script 标签读取模板数据
            if (this.templatesElementId) {
                const el = document.getElementById(this.templatesElementId);
                if (el) {
                    try {
                        this.templates = JSON.parse(el.textContent || '[]');
                    } catch (e) {
                        console.error('解析模板数据失败:', e);
                        this.templates = [];
                    }
                }
            }
            this.legalEntities = this._parseJson(this.legalEntitiesJson);
            this.ourParties = this._parseJson(this.ourPartiesJson);

            // 绑定键盘事件
            if (!this._boundKeyDownHandler) {
                this._boundKeyDownHandler = this.handleKeyDown.bind(this);
            }
            this.$watch('isLegalEntityDialogOpen', () => this._syncKeyDownListener());
            this.$watch('isPoaDialogOpen', () => this._syncKeyDownListener());
            this._syncKeyDownListener();
        },

        /**
         * 同步键盘事件监听器
         */
        _syncKeyDownListener() {
            const shouldBind = (this.isLegalEntityDialogOpen || this.isPoaDialogOpen) && !this.generatingTemplateId;
            if (shouldBind) {
                document.addEventListener('keydown', this._boundKeyDownHandler);
            } else {
                document.removeEventListener('keydown', this._boundKeyDownHandler);
            }
        },

        /**
         * 处理键盘事件
         */
        handleKeyDown(e) {
            if (e.key === 'Escape' && !this.generatingTemplateId) {
                if (this.isLegalEntityDialogOpen) {
                    this.closeLegalEntityDialog();
                }
                if (this.isPoaDialogOpen) {
                    this.closePoaDialog();
                }
            }
        },

        /**
         * 解析 JSON 字符串
         */
        _parseJson(jsonStr) {
            if (!jsonStr) return [];
            try {
                const parsed = JSON.parse(jsonStr);
                return Array.isArray(parsed) ? parsed : [];
            } catch {
                return [];
            }
        },

        /**
         * 判断是否有法人当事人
         */
        get hasLegalEntities() {
            return Array.isArray(this.legalEntities) && this.legalEntities.length > 0;
        },

        /**
         * 判断是否有我方当事人
         */
        get hasOurParties() {
            return Array.isArray(this.ourParties) && this.ourParties.length > 0;
        },

        /**
         * 显示消息
         */
        showMessage(msg, type = 'success') {
            this.message = msg;
            this.messageType = type;
            setTimeout(() => {
                this.message = '';
            }, 3000);
        },

        /**
         * 获取 CSRF Token
         */
        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        // ==================== 特殊模板判断（使用 function_code）====================

        /**
         * 判断是否为法定代表人身份证明书模板
         * Requirements: 2.2 - 使用 function_code 而非模板名称
         */
        isLegalRepCertTemplate(template) {
            return template.function_code === 'legal_rep_certificate';
        },

        /**
         * 判断是否为授权委托书模板
         * Requirements: 2.2 - 使用 function_code 而非模板名称
         */
        isPowerOfAttorneyTemplate(template) {
            return template.function_code === 'power_of_attorney';
        },

        /**
         * 判断是否为所函模板
         * Requirements: 2.2 - 使用 function_code 而非模板名称
         */
        isAuthorityLetterTemplate(template) {
            return template.function_code === 'authority_letter';
        },

        // ==================== 模板点击处理 ====================

        /**
         * 处理模板卡片点击
         * 根据 function_code 分发处理
         * Requirements: 6.1
         */
        async handleTemplateClick(template) {
            if (this.generatingTemplateId) {
                return;  // 防止重复点击
            }

            if (this.isLegalRepCertTemplate(template)) {
                this.handleLegalRepCertClick(template);
            } else if (this.isPowerOfAttorneyTemplate(template)) {
                this.handlePowerOfAttorneyClick(template);
            } else {
                // 普通模板或所函，直接生成
                await this.generateByFunctionCode(template);
            }
        },

        /**
         * 处理法定代表人身份证明书点击
         * Requirements: 2.4
         */
        handleLegalRepCertClick(template) {
            if (!this.hasLegalEntities) {
                this.showMessage('我方当事人无法人，无法生成身份证明书', 'error');
                return;
            }

            // 只有一个法人时直接生成
            if (this.legalEntities.length === 1) {
                this.generateByFunctionCode(template, {
                    client_id: this.legalEntities[0].id
                });
                return;
            }

            // 多个法人时弹出选择对话框
            this.pendingTemplate = template;
            this.selectedLegalEntityIds = [];
            this.isLegalEntityDialogOpen = true;
        },

        /**
         * 处理授权委托书点击
         * Requirements: 2.3
         */
        handlePowerOfAttorneyClick(template) {
            if (!this.hasOurParties) {
                this.showMessage('没有我方当事人，无法生成授权委托书', 'error');
                return;
            }

            // 只有一个我方当事人时直接生成
            if (this.ourParties.length === 1) {
                this.generateByFunctionCode(template, {
                    client_id: this.ourParties[0].id
                });
                return;
            }

            // 多个我方当事人时弹出选择对话框
            this.pendingTemplate = template;
            this.selectedOurPartyIds = [];
            this.poaMode = 'individual';
            this.isPoaDialogOpen = true;
        },

        // ==================== 法人选择对话框 ====================

        /**
         * 关闭法人选择对话框
         */
        closeLegalEntityDialog() {
            if (this.generatingTemplateId) return;
            this.isLegalEntityDialogOpen = false;
            this.selectedLegalEntityIds = [];
            this.pendingTemplate = null;
        },

        /**
         * 全选/取消全选法人
         */
        toggleAllLegalEntities(e) {
            if (!e?.target) return;
            if (e.target.checked) {
                this.selectedLegalEntityIds = this.legalEntities.map(x => x.id);
            } else {
                this.selectedLegalEntityIds = [];
            }
        },

        /**
         * 判断是否全选法人
         */
        isAllLegalEntitiesSelected() {
            return this.hasLegalEntities && this.selectedLegalEntityIds.length === this.legalEntities.length;
        },

        /**
         * 确认生成法定代表人身份证明书
         */
        async confirmLegalRepCert() {
            if (!this.selectedLegalEntityIds.length) {
                this.showMessage('请选择法人', 'error');
                return;
            }

            const template = this.pendingTemplate;

            // 逐个生成
            for (const clientId of this.selectedLegalEntityIds) {
                await this.generateByFunctionCode(template, { client_id: clientId });
            }

            this.closeLegalEntityDialog();
        },

        // ==================== 授权委托书对话框 ====================

        /**
         * 关闭授权委托书对话框
         */
        closePoaDialog() {
            if (this.generatingTemplateId) return;
            this.isPoaDialogOpen = false;
            this.selectedOurPartyIds = [];
            this.poaMode = '';
            this.pendingTemplate = null;
        },

        /**
         * 选择授权模式
         */
        selectPoaMode(mode) {
            if (this.generatingTemplateId) return;
            this.poaMode = mode;
            if (mode === 'combined') {
                this.selectedOurPartyIds = [];
            }
        },

        /**
         * 全选/取消全选我方当事人
         */
        toggleAllOurParties(e) {
            if (!e?.target) return;
            if (e.target.checked) {
                this.selectedOurPartyIds = this.ourParties.map(x => x.id);
            } else {
                this.selectedOurPartyIds = [];
            }
        },

        /**
         * 判断是否全选我方当事人
         */
        isAllOurPartiesSelected() {
            return this.hasOurParties && this.selectedOurPartyIds.length === this.ourParties.length;
        },

        /**
         * 确认生成授权委托书
         */
        async confirmPowerOfAttorney() {
            if (!this.poaMode) return;

            const template = this.pendingTemplate;

            if (this.poaMode === 'combined') {
                // 合并授权
                await this.generateByFunctionCode(template, {
                    client_ids: this.ourParties.map(x => x.id),
                    mode: 'combined'
                });
                this.closePoaDialog();
                return;
            }

            // 单独授权
            if (!this.selectedOurPartyIds.length) {
                this.showMessage('请选择我方当事人', 'error');
                return;
            }

            for (const clientId of this.selectedOurPartyIds) {
                await this.generateByFunctionCode(template, {
                    client_id: clientId,
                    mode: 'individual'
                });
            }

            this.closePoaDialog();
        },

        // ==================== 对话框通用处理 ====================

        /**
         * 处理对话框遮罩点击
         */
        handleDialogOverlayClick(e) {
            if (e.target === e.currentTarget && !this.generatingTemplateId) {
                this.closeLegalEntityDialog();
                this.closePoaDialog();
            }
        },

        // ==================== 文档生成 ====================

        /**
         * 生成文档（使用 function_code 或 template_id）
         * 调用统一 API: /api/v1/cases/{case_id}/unified-generate
         * Requirements: 1.5, 1.6
         */
        async generateByFunctionCode(template, options = {}) {
            if (this.generatingTemplateId) {
                return;  // 防止重复点击
            }

            this.generatingTemplateId = template.template_id;

            try {
                const body = {
                    template_id: template.template_id,
                    function_code: template.function_code,
                    ...options
                };

                const response = await fetch(
                    `${this.apiBasePath}/${this.caseId}/unified-generate`,
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCsrfToken(),
                        },
                        body: JSON.stringify(body),
                    }
                );

                if (!response.ok) {
                    // 处理错误响应
                    let errorMsg = '生成失败';
                    try {
                        const error = await response.json();
                        errorMsg = error.message || error.detail || error.error || errorMsg;
                    } catch (e) {
                        if (response.status === 404) {
                            errorMsg = '模板或案件不存在';
                        }
                    }
                    throw new Error(errorMsg);
                }

                // 获取文件名
                const contentDisposition = response.headers.get('Content-Disposition');
                let filename = `${template.name || '文档'}.docx`;
                if (contentDisposition) {
                    // 优先解析 RFC 5987 编码的文件名 (filename*=UTF-8''xxx)
                    const rfc5987Match = contentDisposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i);
                    if (rfc5987Match) {
                        filename = decodeURIComponent(rfc5987Match[1]);
                    } else {
                        // 回退到普通 filename="xxx" 格式
                        const plainMatch = contentDisposition.match(/filename="?([^";\n]+)"?/i);
                        if (plainMatch) {
                            filename = plainMatch[1].trim();
                        }
                    }
                }

                // 创建 Blob 并下载
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                this.showMessage('文档生成成功');
            } catch (error) {
                console.error('生成模板失败:', error);
                this.showMessage(error.message || '网络错误，请重试', 'error');
            } finally {
                this.generatingTemplateId = null;
            }
        },
    };
}

// 注册到全局
window.unifiedTemplateApp = unifiedTemplateApp;
