/**
 * 案件模板绑定管理 Alpine.js 组件
 *
 * 管理案件与文书模板的绑定关系，支持：
 * - 查看已绑定模板（按分类分组）
 * - 解绑模板
 * - 添加新模板绑定
 * - 生成并下载模板文档（含特殊模板处理）
 */
function templateBindingApp(config) {
    return {
        // 配置
        caseId: config.caseId,
        apiBasePath: config.apiBasePath || '/api/v1/cases',
        legalEntitiesJson: typeof config.legalEntitiesJson === 'string' ? config.legalEntitiesJson : '[]',
        ourPartiesJson: typeof config.ourPartiesJson === 'string' ? config.ourPartiesJson : '[]',

        // 状态
        categories: [],
        totalCount: 0,
        isLoading: false,
        message: '',
        messageType: 'success',
        generatingTemplateId: null,  // 当前正在生成的模板ID

        // 添加模板对话框
        isAddDialogOpen: false,
        availableTemplates: [],
        selectedTemplateIds: [],
        isLoadingAvailable: false,

        // 法人选择对话框状态
        isLegalEntityDialogOpen: false,
        legalEntities: [],
        selectedLegalEntityIds: [],
        pendingLegalRepTemplateId: null,
        pendingLegalRepTemplateName: null,

        // 授权委托书对话框状态
        isPoaDialogOpen: false,
        ourParties: [],
        selectedOurPartyIds: [],
        poaMode: '',
        pendingPoaTemplateId: null,
        pendingPoaTemplateName: null,

        init() {
            // 初始化绑定数据
            const boundTemplates = config.boundTemplates || { categories: [], total_count: 0 };
            this.categories = boundTemplates.categories || [];
            this.totalCount = boundTemplates.total_count || 0;

            // 解析法人和我方当事人数据
            this.legalEntities = this._parseJson(this.legalEntitiesJson);
            this.ourParties = this._parseJson(this.ourPartiesJson);
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
         * 解绑模板
         */
        async unbindTemplate(bindingId) {
            if (!confirm('确定要解绑此模板吗？')) {
                return;
            }

            this.isLoading = true;
            try {
                const response = await fetch(
                    `${this.apiBasePath}/${this.caseId}/template-bindings/${bindingId}`,
                    {
                        method: 'DELETE',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCsrfToken(),
                        },
                    }
                );

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || '解绑失败');
                }

                // 从本地状态中移除
                this.removeBindingFromState(bindingId);
                this.showMessage('模板已解绑');
            } catch (error) {
                console.error('解绑模板失败:', error);
                this.showMessage(error.message || '解绑失败', 'error');
            } finally {
                this.isLoading = false;
            }
        },

        /**
         * 从本地状态中移除绑定
         */
        removeBindingFromState(bindingId) {
            for (let i = 0; i < this.categories.length; i++) {
                const category = this.categories[i];
                const index = category.templates.findIndex(t => t.binding_id === bindingId);
                if (index !== -1) {
                    category.templates.splice(index, 1);
                    this.totalCount--;

                    // 如果分类为空，移除分类
                    if (category.templates.length === 0) {
                        this.categories.splice(i, 1);
                    }
                    break;
                }
            }
        },

        /**
         * 打开添加模板对话框
         */
        async openAddDialog() {
            this.isAddDialogOpen = true;
            this.selectedTemplateIds = [];
            await this.loadAvailableTemplates();
        },

        /**
         * 关闭添加模板对话框
         */
        closeAddDialog() {
            this.isAddDialogOpen = false;
            this.availableTemplates = [];
            this.selectedTemplateIds = [];
        },

        /**
         * 加载可用模板列表
         */
        async loadAvailableTemplates() {
            this.isLoadingAvailable = true;
            try {
                const response = await fetch(
                    `${this.apiBasePath}/${this.caseId}/available-templates`,
                    {
                        headers: {
                            'Content-Type': 'application/json',
                        },
                    }
                );

                if (!response.ok) {
                    throw new Error('加载模板列表失败');
                }

                this.availableTemplates = await response.json();
            } catch (error) {
                console.error('加载可用模板失败:', error);
                this.showMessage('加载模板列表失败', 'error');
            } finally {
                this.isLoadingAvailable = false;
            }
        },

        /**
         * 绑定选中的模板
         */
        async bindSelectedTemplates() {
            if (this.selectedTemplateIds.length === 0) {
                return;
            }

            this.isLoading = true;
            let successCount = 0;
            let errorCount = 0;

            try {
                for (const templateId of this.selectedTemplateIds) {
                    try {
                        const response = await fetch(
                            `${this.apiBasePath}/${this.caseId}/template-bindings`,
                            {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': this.getCsrfToken(),
                                },
                                body: JSON.stringify({ template_id: templateId }),
                            }
                        );

                        if (response.ok) {
                            const binding = await response.json();
                            this.addBindingToState(binding);
                            successCount++;
                        } else {
                            errorCount++;
                        }
                    } catch (e) {
                        errorCount++;
                    }
                }

                if (successCount > 0) {
                    this.showMessage(`成功添加 ${successCount} 个模板`);
                }
                if (errorCount > 0) {
                    this.showMessage(`${errorCount} 个模板添加失败`, 'error');
                }

                this.closeAddDialog();
            } finally {
                this.isLoading = false;
            }
        },

        /**
         * 添加绑定到本地状态
         */
        addBindingToState(binding) {
            // 查找模板信息
            const template = this.availableTemplates.find(t => t.template_id === binding.template_id);
            if (!template) return;

            const categoryKey = template.case_sub_type || 'other_materials';
            const categoryDisplay = template.case_sub_type_display || '其他材料';

            // 查找或创建分类
            let category = this.categories.find(c => c.category === categoryKey);
            if (!category) {
                category = {
                    category: categoryKey,
                    category_display: categoryDisplay,
                    templates: [],
                };
                this.categories.push(category);
            }

            // 添加模板
            category.templates.push({
                binding_id: binding.binding_id,
                template_id: binding.template_id,
                name: binding.name,
                description: template.description || '',
                binding_source: binding.binding_source,
                binding_source_display: binding.binding_source_display,
                created_at: binding.created_at,
            });

            this.totalCount++;
        },

        /**
         * 获取 CSRF Token
         */
        getCsrfToken() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        /**
         * 判断是否为法定代表人身份证明书模板
         */
        isLegalRepCertTemplate(templateName) {
            return templateName === '法定代表人身份证明书';
        },

        /**
         * 判断是否为授权委托书模板
         */
        isPowerOfAttorneyTemplate(templateName) {
            return templateName === '授权委托书';
        },

        /**
         * 处理模板卡片点击
         * 根据模板类型分发处理
         */
        async handleTemplateClick(templateId, templateName) {
            if (this.generatingTemplateId) {
                return;  // 防止重复点击
            }

            if (this.isLegalRepCertTemplate(templateName)) {
                await this.handleLegalRepCertClick(templateId, templateName);
            } else if (this.isPowerOfAttorneyTemplate(templateName)) {
                await this.handlePowerOfAttorneyClick(templateId, templateName);
            } else {
                await this.generateTemplate(templateId, templateName);
            }
        },

        /**
         * 处理法定代表人身份证明书点击
         */
        async handleLegalRepCertClick(templateId, templateName) {
            if (!this.hasLegalEntities) {
                this.showMessage('我方当事人无法人，无法生成身份证明书', 'error');
                return;
            }

            // 只有一个法人时直接生成
            if (this.legalEntities.length === 1) {
                await this.generateTemplate(templateId, templateName, {
                    client_id: this.legalEntities[0].id
                });
                return;
            }

            // 多个法人时弹出选择对话框
            this.pendingLegalRepTemplateId = templateId;
            this.pendingLegalRepTemplateName = templateName;
            this.selectedLegalEntityIds = [];
            this.isLegalEntityDialogOpen = true;
        },

        /**
         * 处理授权委托书点击
         */
        async handlePowerOfAttorneyClick(templateId, templateName) {
            if (!this.hasOurParties) {
                this.showMessage('没有我方当事人，无法生成授权委托书', 'error');
                return;
            }

            // 只有一个我方当事人时直接生成
            if (this.ourParties.length === 1) {
                await this.generateTemplate(templateId, templateName, {
                    client_id: this.ourParties[0].id
                });
                return;
            }

            // 多个我方当事人时弹出选择对话框
            this.pendingPoaTemplateId = templateId;
            this.pendingPoaTemplateName = templateName;
            this.selectedOurPartyIds = [];
            this.poaMode = 'individual';
            this.isPoaDialogOpen = true;
        },

        /**
         * 关闭法人选择对话框
         */
        closeLegalEntityDialog() {
            if (this.generatingTemplateId) return;
            this.isLegalEntityDialogOpen = false;
            this.selectedLegalEntityIds = [];
            this.pendingLegalRepTemplateId = null;
            this.pendingLegalRepTemplateName = null;
        },

        /**
         * 关闭授权委托书对话框
         */
        closePoaDialog() {
            if (this.generatingTemplateId) return;
            this.isPoaDialogOpen = false;
            this.selectedOurPartyIds = [];
            this.poaMode = '';
            this.pendingPoaTemplateId = null;
            this.pendingPoaTemplateName = null;
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
         * 确认生成法定代表人身份证明书
         */
        async confirmLegalRepCert() {
            if (!this.selectedLegalEntityIds.length) {
                this.showMessage('请选择法人', 'error');
                return;
            }

            // 逐个生成
            for (const clientId of this.selectedLegalEntityIds) {
                await this.generateTemplate(
                    this.pendingLegalRepTemplateId,
                    this.pendingLegalRepTemplateName,
                    { client_id: clientId }
                );
            }

            this.closeLegalEntityDialog();
        },

        /**
         * 确认生成授权委托书
         */
        async confirmPowerOfAttorney() {
            if (!this.poaMode) return;

            if (this.poaMode === 'combined') {
                // 合并授权
                await this.generateTemplate(
                    this.pendingPoaTemplateId,
                    this.pendingPoaTemplateName,
                    {
                        client_ids: this.ourParties.map(x => x.id),
                        mode: 'combined'
                    }
                );
                this.closePoaDialog();
                return;
            }

            // 单独授权
            if (!this.selectedOurPartyIds.length) {
                this.showMessage('请选择我方当事人', 'error');
                return;
            }

            for (const clientId of this.selectedOurPartyIds) {
                await this.generateTemplate(
                    this.pendingPoaTemplateId,
                    this.pendingPoaTemplateName,
                    { client_id: clientId, mode: 'individual' }
                );
            }

            this.closePoaDialog();
        },

        /**
         * 处理对话框遮罩点击
         */
        handleDialogOverlayClick(e) {
            if (e.target === e.currentTarget && !this.generatingTemplateId) {
                this.closeLegalEntityDialog();
                this.closePoaDialog();
            }
        },

        /**
         * 生成并下载模板文档
         *
         * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
         */
        async generateTemplate(templateId, templateName, options = {}) {
            if (this.generatingTemplateId) {
                return;  // 防止重复点击
            }

            this.generatingTemplateId = templateId;

            try {
                const body = { template_id: templateId, ...options };

                const response = await fetch(
                    `${this.apiBasePath}/${this.caseId}/generate-template`,
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
                        errorMsg = error.message || error.error || errorMsg;
                    } catch (e) {
                        if (response.status === 404) {
                            errorMsg = '模板或案件不存在';
                        }
                    }
                    throw new Error(errorMsg);
                }

                // 获取文件名
                const contentDisposition = response.headers.get('Content-Disposition');
                let filename = `${templateName}.docx`;
                if (contentDisposition) {
                    // 解析 RFC 5987 编码的文件名
                    const match = contentDisposition.match(/filename\*=UTF-8''(.+)/);
                    if (match) {
                        filename = decodeURIComponent(match[1]);
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
window.templateBindingApp = templateBindingApp;
