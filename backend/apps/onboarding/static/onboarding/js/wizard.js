/**
 * 立案引导向导 Alpine.js 状态管理器
 *
 * 功能：
 * - 管理多步骤向导的状态和导航
 * - 处理当事人搜索、选择和创建
 * - 管理合同和案件数据
 * - 实现 sessionStorage 持久化
 * - 处理 API 调用和错误处理
 */

function wizardApp() {
    return {
        // ========== 核心状态 ==========

        // 当前步骤 (1-4)
        currentStep: 1,
        totalSteps: 4,

        debug: false,
        apiBase: '/api/v1',
        logger: null,

        // 步骤数据
        selectedClients: [],      // 选中的当事人列表 [{client: {...}, role: 'PRINCIPAL'}]
        _selectedClientRefs: null,
        _opposingPartyIds: null,
        newClient: {},            // 新建当事人表单数据
        contract: {},             // 合同数据
        caseInfo: {},             // 案件数据 (注意: 不能用 case，是 JS 保留字)

        // UI 状态
        loading: false,           // 全局加载状态
        loadingMessage: '',       // 加载提示消息
        errors: {},               // 表单验证错误
        searchQuery: '',          // 当事人搜索关键词
        searchResults: [],        // 搜索结果
        searchLoading: false,     // 搜索加载状态
        showNewClientForm: false, // 是否显示新建当事人表单

        // 当事人列表相关
        allClients: [],           // 所有当事人列表
        clientsLoading: false,    // 当事人列表加载状态
        clientTypeFilter: '',     // 当事人类型筛选
        ourClientFilter: '',      // 我方/对方筛选 (true=我方, false=对方, ''=全部)
        viewMode: 'list',         // 视图模式: 'list' 或 'card'
        clientsPage: 1,           // 当事人列表当前页码
        clientsPerPage: 8,        // 每页显示数量
        toast: {                  // Toast 通知状态
            show: false,
            message: '',
            type: 'success' // success, error, warning, info
        },

        // 合同步骤相关状态
        lawyers: [],              // 律师列表
        lawyersLoaded: false,     // 律师列表是否已加载
        lawyersLoading: false,    // 律师列表加载中
        showOpposingPartyForm: false, // 是否显示对方当事人表单
        opposingSearchQuery: '',  // 对方当事人搜索关键词
        opposingSearchResults: [], // 对方当事人搜索结果
        newOpposingParty: {},     // 新建对方当事人表单数据

        // 智能识别相关状态
        showQuickParseInput: true,   // 默认显示快速识别输入框
        showOcrUpload: false,        // 是否显示OCR上传区域
        quickParseText: '',          // 快速识别文本
        quickParsing: false,         // 快速识别中
        ocrDocType: '',              // OCR证件类型
        ocrFile: null,               // OCR上传的文件
        ocrDragOver: false,          // OCR拖拽状态
        ocrProcessing: false,        // OCR处理中
        ocrRecognitionResult: null,  // OCR识别结果
        recognitionMessage: '',      // 识别结果消息
        recognitionSuccess: false,   // 识别是否成功

        // 编辑当事人相关状态
        showEditClientForm: false,   // 是否显示编辑当事人弹窗
        editClient: {},              // 编辑当事人表单数据
        editClientId: null,          // 正在编辑的当事人ID

        // 创建结果状态
        createdContract: null,       // 创建的合同对象
        createdCase: null,           // 创建的案件对象

        // ========== 计算属性 ==========

        /**
         * 判断是否需要案件创建步骤
         * 诉讼类合同需要创建案件，顾问和专项不需要
         */
        get needsCaseStep() {
            const litigationTypes = ['civil', 'criminal', 'administrative'];
            return litigationTypes.includes(this.contract.case_type);
        },

        /**
         * 过滤后的当事人列表（根据搜索和类型筛选）
         */
        get filteredClients() {
            let clients = this.allClients;

            // 搜索过滤
            if (this.searchQuery.trim()) {
                const query = this.searchQuery.trim().toLowerCase();
                clients = clients.filter(c =>
                    c.name?.toLowerCase().includes(query) ||
                    c.phone?.includes(query) ||
                    c.id_number?.toLowerCase().includes(query)
                );
            }

            // 我方/对方过滤
            if (this.ourClientFilter !== '') {
                clients = clients.filter(c => c.is_our_client === this.ourClientFilter);
            }

            // 类型过滤
            if (this.clientTypeFilter) {
                clients = clients.filter(c => c.client_type === this.clientTypeFilter);
            }

            return clients;
        },

        /**
         * 分页后的当事人列表
         */
        get paginatedClients() {
            const start = (this.clientsPage - 1) * this.clientsPerPage;
            const end = start + this.clientsPerPage;
            return this.filteredClients.slice(start, end);
        },

        /**
         * 当事人列表总页数
         */
        get clientsTotalPages() {
            return Math.ceil(this.filteredClients.length / this.clientsPerPage);
        },

        /**
         * 实际总步骤数（根据合同类型动态计算）
         */
        get actualTotalSteps() {
            return this.needsCaseStep ? 4 : 3;
        },

        /**
         * 当前步骤是否可以继续下一步
         */
        get canProceedToNext() {
            switch (this.currentStep) {
                case 1: // 当事人步骤
                    return this.selectedClients.length > 0;
                case 2: // 合同步骤
                    return this.canProceedFromContract;
                case 3: // 案件步骤（如果需要）
                    return !this.needsCaseStep || this.canProceedFromCase;
                default:
                    return true;
            }
        },

        /**
         * 合同步骤是否可以继续
         */
        get canProceedFromContract() {
            // 基本必填字段
            if (!this.contract.name || !this.contract.case_type || !this.contract.fee_mode) {
                return false;
            }

            // 主办律师必填
            if (!this.contract.primary_lawyer) {
                return false;
            }

            // 收费模式相关验证 - 必须是正数
            if (this.contract.fee_mode === 'FIXED') {
                const amount = parseFloat(this.contract.fixed_amount);
                if (!amount || amount <= 0) return false;
            }
            if (this.contract.fee_mode === 'SEMI_RISK') {
                const amount = parseFloat(this.contract.fixed_amount);
                const rate = parseFloat(this.contract.risk_rate);
                if (!amount || amount <= 0 || !rate || rate <= 0) return false;
            }
            if (this.contract.fee_mode === 'FULL_RISK') {
                const rate = parseFloat(this.contract.risk_rate);
                if (!rate || rate <= 0) return false;
            }

            return true;
        },

        /**
         * 案件步骤是否可以继续
         */
        get canProceedFromCase() {
            // 案件名称和案由必填
            if (!this.caseInfo.name?.trim() || !this.caseInfo.cause_of_action?.trim()) {
                return false;
            }
            return true;
        },

        /**
         * 可选的协办律师列表（排除主办律师）
         */
        get availableAssistantLawyers() {
            return this.lawyers.filter(lawyer =>
                lawyer.id !== parseInt(this.contract.primary_lawyer) &&
                !this.contract.assistant_lawyers.includes(lawyer.id)
            );
        },

        /**
         * 是否显示上一步按钮
         */
        get canGoBack() {
            return this.currentStep > 1;
        },

        // ========== 初始化 ==========

        setupOnboardingData() {
            if (!window.onboardingData) {
                const el = document.getElementById('onboarding-data');
                if (el && el.textContent) {
                    try {
                        window.onboardingData = JSON.parse(el.textContent);
                    } catch (e) {
                        window.onboardingData = {};
                    }
                } else {
                    window.onboardingData = {};
                }
            }

            const apiBase = window.onboardingData.apiBase;
            this.apiBase = typeof apiBase === 'string' && apiBase ? apiBase : '/api/v1';
            this.debug = Boolean(window.onboardingData.debug);
            this.logger = this.createLogger();
        },

        createLogger() {
            return {
                debug: (...args) => {
                    if (this.debug) {
                        console.log(...args);
                    }
                },
                warn: (...args) => {
                    if (this.debug) {
                        console.warn(...args);
                    }
                },
                error: (...args) => {
                    console.error(...args);
                }
            };
        },

        /**
         * Alpine.js 初始化钩子
         */
        init() {
            this.setupOnboardingData();

            // 页面刷新时清空 session，保证每次都是全新页面
            // 使用 performance.navigation 或 PerformanceNavigationTiming 检测刷新
            const isPageReload = (
                (window.performance && window.performance.navigation && window.performance.navigation.type === 1) ||
                (window.performance && window.performance.getEntriesByType &&
                 window.performance.getEntriesByType('navigation').length > 0 &&
                 window.performance.getEntriesByType('navigation')[0].type === 'reload')
            );

            if (isPageReload) {
                this.clearSession();
            }

            // 检查 URL 参数，如果有 reset=1 则清空 session
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('reset') === '1') {
                this.clearSession();
                // 移除 URL 参数
                window.history.replaceState({}, '', window.location.pathname);
            }

            this.loadFromSession();
            this.initializeFormData();
            this.initializeOpposingPartyForm();
            // 加载当事人列表
            this.loadAllClients();
        },

        /**
         * 加载所有当事人列表
         */
        async loadAllClients() {
            if (this.clientsLoading) return;

            try {
                this.clientsLoading = true;

                const response = await this.apiCall('GET', '/api/v1/client/clients?page_size=100');

                if (response.results) {
                    this.allClients = response.results;
                } else if (Array.isArray(response)) {
                    this.allClients = response;
                } else {
                    this.allClients = [];
                }

                this.restoreClientsFromSession();
                this.logger.debug(`加载了 ${this.allClients.length} 个当事人`);

            } catch (error) {
                this.logger.error('加载当事人列表失败');
                this.allClients = [];
            } finally {
                this.clientsLoading = false;
            }
        },

        restoreClientsFromSession() {
            if (!this._selectedClientRefs && !this._opposingPartyIds) {
                return;
            }

            const idToClient = new Map(this.allClients.map(client => [client.id, client]));

            if (this._selectedClientRefs) {
                this.selectedClients = this._selectedClientRefs
                    .map(ref => {
                        const client = idToClient.get(ref.client_id);
                        if (!client) {
                            return null;
                        }
                        return { client, role: ref.role };
                    })
                    .filter(Boolean);
                this._selectedClientRefs = null;
            }

            if (this._opposingPartyIds) {
                this.contract.opposing_parties = this._opposingPartyIds
                    .map(id => {
                        const client = idToClient.get(id);
                        if (!client) {
                            return null;
                        }
                        return {
                            id: client.id,
                            name: client.name,
                            client_type: client.client_type,
                            phone: client.phone,
                            id_number: client.id_number,
                            isNew: false
                        };
                    })
                    .filter(Boolean);
                this._opposingPartyIds = null;
            }
        },

        /**
         * 初始化表单数据
         */
        initializeFormData() {
            // 初始化新建当事人表单
            if (!this.newClient.client_type) {
                this.newClient = {
                    name: '',
                    client_type: 'natural',
                    phone: '',
                    address: '',
                    id_number: '',
                    legal_representative: ''
                };
            }

            // 初始化合同数据
            if (!this.contract.case_type) {
                this.contract = {
                    name: '',
                    case_type: '',
                    fee_mode: 'FIXED',
                    fixed_amount: '',
                    risk_rate: '',
                    specified_date: new Date().toISOString().split('T')[0],
                    primary_lawyer: '',
                    assistant_lawyers: [],
                    opposing_parties: [],
                    representation_stages: []  // 代理阶段
                };
            }

            // 确保 representation_stages 是数组
            if (!Array.isArray(this.contract.representation_stages)) {
                this.contract.representation_stages = [];
            }

            // 确保 assistant_lawyers 和 opposing_parties 是数组
            if (!Array.isArray(this.contract.assistant_lawyers)) {
                this.contract.assistant_lawyers = [];
            }
            if (!Array.isArray(this.contract.opposing_parties)) {
                this.contract.opposing_parties = [];
            }

            // 初始化案件数据
            if (!this.caseInfo.name) {
                this.caseInfo = {
                    name: '',
                    cause_of_action: '',
                    target_amount: '',
                    current_stage: 'PREPARATION',
                    party_roles: {} // 当事人诉讼地位映射
                };
            }
        },

        /**
         * 初始化对方当事人表单
         */
        initializeOpposingPartyForm() {
            this.newOpposingParty = {
                name: '',
                client_type: 'natural',
                phone: '',
                id_number: ''
            };
        },

        // ========== 步骤导航 ==========

        /**
         * 前进到下一步
         */
        async nextStep() {
            if (!this.canProceedToNext) {
                this.showValidationErrors();
                return;
            }

            // 如果从步骤1进入步骤2，自动加载律师列表
            if (this.currentStep === 1) {
                this.loadLawyers();
            }

            // 如果从步骤2进入下一步，先创建合同
            if (this.currentStep === 2 && !this.contract.id) {
                const result = await this.createContract();
                if (!result) {
                    return; // 创建失败，不继续
                }

                // 合同创建成功后，如果需要案件步骤，自动设置案件名称为合同名称
                if (this.needsCaseStep && !this.caseInfo.name) {
                    this.caseInfo.name = this.contract.name;
                }
            }

            // 如果从步骤3进入下一步（完成页面），先创建案件
            if (this.currentStep === 3 && this.needsCaseStep && !this.caseInfo.id) {
                const result = await this.createCase();
                if (!result) {
                    return; // 创建失败，不继续
                }
            }

            // 如果是第2步且不需要案件步骤，直接跳到完成页面
            if (this.currentStep === 2 && !this.needsCaseStep) {
                this.currentStep = 4; // 跳到完成页面
            } else if (this.currentStep < this.actualTotalSteps) {
                this.currentStep++;
            }

            this.saveToSession();
            this.clearErrors();
        },

        /**
         * 返回上一步
         */
        prevStep() {
            if (this.canGoBack) {
                // 如果当前在完成页面且不需要案件步骤，返回到合同步骤
                if (this.currentStep === 4 && !this.needsCaseStep) {
                    this.currentStep = 2;
                } else {
                    this.currentStep--;
                }
                this.saveToSession();
                this.clearErrors();
            }
        },

        /**
         * 跳转到指定步骤
         */
        goToStep(step) {
            if (step >= 1 && step <= this.actualTotalSteps) {
                // 跳过案件步骤的逻辑处理
                if (step === 3 && !this.needsCaseStep) {
                    step = 4; // 跳到完成页面
                }
                this.currentStep = step;
                this.saveToSession();
                this.clearErrors();
            }
        },

        // ========== 当事人管理 ==========

        /**
         * 搜索当事人（本地过滤，不再调用API）
         */
        searchClients() {
            // 搜索现在通过 filteredClients 计算属性实现
            // 这个方法保留用于兼容性，实际过滤在 getter 中完成
            this.logger.debug('搜索关键词:', this.searchQuery);
        },

        /**
         * 清除搜索
         */
        clearSearch() {
            this.searchQuery = '';
            this.clientTypeFilter = '';
            this.ourClientFilter = '';
            this.clientsPage = 1; // 重置页码
        },

        /**
         * 当事人列表翻页
         */
        goToClientsPage(page) {
            if (page >= 1 && page <= this.clientsTotalPages) {
                this.clientsPage = page;
            }
        },

        /**
         * 上一页
         */
        prevClientsPage() {
            if (this.clientsPage > 1) {
                this.clientsPage--;
            }
        },

        /**
         * 下一页
         */
        nextClientsPage() {
            if (this.clientsPage < this.clientsTotalPages) {
                this.clientsPage++;
            }
        },

        /**
         * 清空所有已选择的当事人
         */
        clearAllSelectedClients() {
            if (this.selectedClients.length === 0) {
                return;
            }

            const count = this.selectedClients.length;
            this.selectedClients = [];
            this.saveToSession();
            this.showSuccess(`已清空 ${count} 个当事人`);
        },

        selectClient(client) {
            // 检查是否已选中
            const isSelected = this.selectedClients.some(item => item.client.id === client.id);

            if (isSelected) {
                // 取消选中
                this.selectedClients = this.selectedClients.filter(item => item.client.id !== client.id);
            } else {
                // 添加选中，根据 is_our_client 自动设置身份
                // 我方当事人 (is_our_client === true) → 委托人
                // 对方当事人 (is_our_client === false) → 对方当事人
                const autoRole = (client.is_our_client === true) ? 'PRINCIPAL' : 'OPPOSING';
                this.selectedClients.push({
                    client: client,
                    role: autoRole
                });
            }

            this.saveToSession();
        },

        /**
         * 移除已选择的当事人（按索引）
         */
        removeSelectedClient(index) {
            this.selectedClients.splice(index, 1);
            this.saveToSession();
        },

        /**
         * 检查当事人是否已选中
         */
        isClientSelected(client) {
            return this.selectedClients.some(item => item.client.id === client.id);
        },

        /**
         * 显示/隐藏新建当事人表单
         */
        toggleNewClientForm() {
            this.showNewClientForm = !this.showNewClientForm;
            if (this.showNewClientForm) {
                // 重置表单数据
                this.resetNewClientForm();
                this.clearErrors();
            }
        },

        /**
         * 创建新当事人
         */
        async createClient() {
            try {
                this.startLoading('正在创建当事人');
                this.clearErrors();

                // 前端验证
                if (!this.validateNewClient()) {
                    return;
                }

                // 准备提交数据
                const clientData = {
                    name: this.newClient.name.trim(),
                    client_type: this.newClient.client_type,
                    phone: this.newClient.phone.trim(),
                    address: this.newClient.address?.trim() || '',
                    id_number: this.newClient.id_number?.trim() || '',
                    legal_representative: this.newClient.legal_representative?.trim() || '',
                    is_our_client: this.newClient.is_our_client
                };

                const response = await this.apiCall('POST', '/api/v1/client/clients', clientData);

                // 自动选中新创建的当事人，根据 is_our_client 自动设置身份
                const autoRole = (response.is_our_client === true) ? 'PRINCIPAL' : 'OPPOSING';
                this.selectedClients.push({
                    client: response,
                    role: autoRole
                });

                // 添加到当事人列表
                this.allClients.unshift(response);

                // 隐藏表单并重置数据
                this.showNewClientForm = false;
                this.resetNewClientForm();

                // 清空搜索
                this.clearSearch();

                this.showSuccess(`当事人"${response.name}"创建成功`);
                this.saveToSession();

            } catch (error) {
                this.logger.error('创建当事人失败');
                this.handleApiError(error);
            } finally {
                this.stopLoading();
            }
        },

        /**
         * 重置新建当事人表单
         */
        resetNewClientForm() {
            this.newClient = {
                name: '',
                client_type: 'natural',
                phone: '',
                address: '',
                id_number: '',
                legal_representative: '',
                is_our_client: null  // 不默认选择，让用户自己选
            };
            // 重置智能识别状态
            this.showQuickParseInput = true;  // 默认展开快速识别
            this.showOcrUpload = false;
            this.quickParseText = '';
            this.ocrDocType = '';
            this.ocrFile = null;
            this.ocrRecognitionResult = null;
            this.recognitionMessage = '';
        },

        // ========== 编辑当事人功能 ==========

        /**
         * 打开编辑当事人弹窗
         */
        openEditClientForm(client, event) {
            // 阻止事件冒泡，避免触发选择
            if (event) {
                event.stopPropagation();
            }

            this.editClientId = client.id;
            this.editClient = {
                name: client.name || '',
                client_type: client.client_type || 'natural',
                phone: client.phone || '',
                address: client.address || '',
                id_number: client.id_number || '',
                legal_representative: client.legal_representative || '',
                is_our_client: client.is_our_client
            };
            this.showEditClientForm = true;
            this.clearErrors();
        },

        /**
         * 关闭编辑当事人弹窗
         */
        closeEditClientForm() {
            this.showEditClientForm = false;
            this.editClientId = null;
            this.editClient = {};
            this.clearErrors();
        },

        /**
         * 验证编辑当事人表单
         */
        validateEditClient() {
            const errors = {};
            const fieldsToShake = [];

            // 必填字段验证
            if (!this.validateRequiredField(this.editClient.name)) {
                errors.name = '请输入当事人名称';
                fieldsToShake.push('edit-client-name');
            }

            // 当事人身份必填验证
            if (this.editClient.is_our_client === null || this.editClient.is_our_client === undefined) {
                errors.is_our_client = '请选择当事人身份（我方/对方）';
                fieldsToShake.push('edit-client-identity');
            }

            // 联系电话非必填，但填了要验证格式
            if (this.editClient.phone?.trim() && !this.validatePhoneNumber(this.editClient.phone)) {
                errors.phone = '请输入正确的手机号码（11位手机号）';
                fieldsToShake.push('edit-client-phone');
            }

            // 身份证号/统一社会信用代码验证
            if (this.editClient.id_number?.trim()) {
                if (this.editClient.client_type === 'natural') {
                    const idValidation = this.validateIdNumberWithDetails(this.editClient.id_number);
                    if (!idValidation.valid) {
                        errors.id_number = idValidation.message;
                        fieldsToShake.push('edit-client-id');
                    }
                } else {
                    if (!this.validateCreditCode(this.editClient.id_number)) {
                        errors.id_number = '统一社会信用代码格式不正确（需要18位有效代码）';
                        fieldsToShake.push('edit-client-id');
                    }
                }
            }

            // 法人/非法人组织必须填写法定代表人/负责人
            if ((this.editClient.client_type === 'legal' || this.editClient.client_type === 'non_legal_org')
                && !this.validateRequiredField(this.editClient.legal_representative)) {
                errors.legal_representative = this.editClient.client_type === 'legal' ? '请输入法定代表人姓名' : '请输入负责人姓名';
                fieldsToShake.push('edit-client-legal-rep');
            }

            if (Object.keys(errors).length > 0) {
                this.errors = { ...this.errors, ...errors };
                this.triggerValidationAnimation(fieldsToShake);
                const firstError = Object.values(errors)[0];
                if (firstError) {
                    this.showError(firstError);
                }
                return false;
            }

            return true;
        },

        /**
         * 更新当事人
         */
        async updateClient() {
            try {
                this.startLoading('正在更新当事人');
                this.clearErrors();

                // 前端验证
                if (!this.validateEditClient()) {
                    this.stopLoading();
                    return;
                }

                // 准备提交数据
                const clientData = {
                    name: this.editClient.name.trim(),
                    client_type: this.editClient.client_type,
                    phone: this.editClient.phone?.trim() || '',
                    address: this.editClient.address?.trim() || '',
                    id_number: this.editClient.id_number?.trim() || '',
                    legal_representative: this.editClient.legal_representative?.trim() || '',
                    is_our_client: this.editClient.is_our_client
                };

                const response = await this.apiCall('PUT', `/api/v1/client/clients/${this.editClientId}`, clientData);

                // 更新当事人列表中的数据
                const index = this.allClients.findIndex(c => c.id === this.editClientId);
                if (index !== -1) {
                    this.allClients[index] = response;
                }

                // 更新已选择列表中的数据（保留原有的role）
                const selectedIndex = this.selectedClients.findIndex(item => item.client.id === this.editClientId);
                if (selectedIndex !== -1) {
                    this.selectedClients[selectedIndex].client = response;
                }

                // 关闭弹窗
                this.closeEditClientForm();

                this.showSuccess(`当事人"${response.name}"更新成功`);
                this.saveToSession();

            } catch (error) {
                this.logger.error('更新当事人失败');
                this.handleApiError(error);
            } finally {
                this.stopLoading();
            }
        },

        // ========== 智能识别功能 ==========

        /**
         * 检测快速识别文本格式
         */
        detectQuickParseFormat() {
            const text = this.quickParseText.trim();
            if (!text) return '';

            if ((text.startsWith('{') && text.endsWith('}')) ||
                (text.startsWith('[') && text.endsWith(']'))) {
                try {
                    JSON.parse(text);
                    return '检测到 JSON 格式';
                } catch (e) {
                    return '检测到文本格式';
                }
            }
            return '检测到文本格式';
        },

        /**
         * 解析快速识别文本
         */
        async parseQuickText() {
            const text = this.quickParseText.trim();
            if (!text) return;

            this.quickParsing = true;
            this.recognitionMessage = '';

            try {
                // 检测是否为 JSON 格式
                if ((text.startsWith('{') && text.endsWith('}')) ||
                    (text.startsWith('[') && text.endsWith(']'))) {
                    try {
                        const data = JSON.parse(text);
                        this.fillNewClientFromData(data);
                        this.recognitionSuccess = true;
                        this.recognitionMessage = '✓ JSON 解析成功，表单已自动填充';
                        this.quickParseText = '';
                        return;
                    } catch (e) {
                        // 不是有效 JSON，继续尝试文本解析
                    }
                }

                // 调用后端文本解析 API
                const response = await this.apiCall('POST', '/api/v1/client/clients/parse-text', {
                    text: text,
                    parse_multiple: false
                });

                if (response.success && response.client) {
                    this.fillNewClientFromData(response.client);
                    this.recognitionSuccess = true;

                    if (response.parse_method === 'ollama') {
                        this.recognitionMessage = '✓ AI 智能解析成功，表单已自动填充';
                    } else {
                        this.recognitionMessage = '✓ 文本解析成功，表单已自动填充';
                    }
                    this.quickParseText = '';
                } else {
                    this.recognitionSuccess = false;
                    this.recognitionMessage = '✗ ' + (response.error || '解析失败，请检查文本格式');
                }
            } catch (error) {
                this.logger.error('快速识别失败');
                this.recognitionSuccess = false;
                this.recognitionMessage = '✗ 解析请求失败，请检查网络连接';
            } finally {
                this.quickParsing = false;
            }
        },

        /**
         * 处理 OCR 文件选择
         */
        handleOcrFileSelect(event) {
            const file = event.target.files[0];
            if (file) {
                this.validateAndSetOcrFile(file);
            }
        },

        /**
         * 处理 OCR 文件拖放
         */
        handleOcrFileDrop(event) {
            this.ocrDragOver = false;
            const file = event.dataTransfer.files[0];
            if (file) {
                this.validateAndSetOcrFile(file);
            }
        },

        /**
         * 验证并设置 OCR 文件
         */
        validateAndSetOcrFile(file) {
            const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
            const maxSize = 10 * 1024 * 1024; // 10MB

            if (!allowedTypes.includes(file.type)) {
                this.showError('不支持的文件格式，请上传 JPG、PNG 或 PDF 文件');
                return;
            }

            if (file.size > maxSize) {
                this.showError('文件大小不能超过 10MB');
                return;
            }

            this.ocrFile = file;
            this.ocrRecognitionResult = null;
            this.recognitionMessage = '';
        },

        /**
         * 执行 OCR 识别
         */
        async performOcrRecognition() {
            if (!this.ocrFile || !this.ocrDocType) {
                this.showError('请选择证件类型并上传文件');
                return;
            }

            this.ocrProcessing = true;
            this.recognitionMessage = '';

            try {
                const formData = new FormData();
                formData.append('file', this.ocrFile);
                formData.append('doc_type', this.ocrDocType);

                const result = await this.apiCallForm('POST', '/api/v1/client/identity-doc/recognize', formData);

                if (result.success && result.extracted_data) {
                    this.ocrRecognitionResult = result;
                    this.fillNewClientFromOcrResult(result.extracted_data);
                    this.recognitionSuccess = true;
                    this.recognitionMessage = `✓ OCR 识别成功 (置信度: ${Math.round((result.confidence || 0) * 100)}%)`;
                } else {
                    this.recognitionSuccess = false;
                    this.recognitionMessage = '✗ ' + (result.error || '识别失败');
                }
            } catch (error) {
                this.logger.error('OCR 识别失败');
                this.recognitionSuccess = false;
                this.recognitionMessage = '✗ ' + (error?.data?.error || error?.data?.detail || error.message || '识别请求失败');
            } finally {
                this.ocrProcessing = false;
            }
        },

        /**
         * 从数据填充新建当事人表单
         */
        fillNewClientFromData(data) {
            if (data.client_type) {
                this.newClient.client_type = data.client_type;
            }
            if (data.name) {
                this.newClient.name = data.name;
            }
            if (data.phone) {
                this.newClient.phone = data.phone;
            }
            if (data.address) {
                this.newClient.address = data.address;
            }
            if (data.id_number) {
                this.newClient.id_number = data.id_number;
            }
            if (data.legal_representative) {
                this.newClient.legal_representative = data.legal_representative;
            }
            if (data.is_our_client !== undefined) {
                this.newClient.is_our_client = data.is_our_client;
            }
        },

        /**
         * 从 OCR 结果填充新建当事人表单
         */
        fillNewClientFromOcrResult(extractedData) {
            // 根据证件类型设置当事人类型
            if (this.ocrDocType === 'business_license') {
                this.newClient.client_type = 'legal';
                if (extractedData.company_name) {
                    this.newClient.name = extractedData.company_name;
                }
                if (extractedData.credit_code) {
                    this.newClient.id_number = extractedData.credit_code;
                }
                if (extractedData.legal_representative) {
                    this.newClient.legal_representative = extractedData.legal_representative;
                }
            } else {
                this.newClient.client_type = 'natural';
                if (extractedData.name) {
                    this.newClient.name = extractedData.name;
                }
                const idNumber = extractedData.id_number || extractedData.id_card_number ||
                               extractedData.passport_number || extractedData.permit_number;
                if (idNumber) {
                    this.newClient.id_number = idNumber;
                }
            }

            if (extractedData.address) {
                this.newClient.address = extractedData.address;
            }
        },

        /**
         * 获取证件类型标签
         */
        getDocTypeLabel(docType) {
            const labels = {
                'id_card': '身份证',
                'business_license': '营业执照',
                'passport': '护照',
                'hk_macao_permit': '港澳通行证'
            };
            return labels[docType] || docType;
        },

        /**
         * 创建当事人并绑定身份证件
         */
        async createClientWithIdentityDoc() {
            try {
                this.startLoading('正在创建当事人');
                this.clearErrors();

                // 前端验证
                if (!this.validateNewClient()) {
                    this.stopLoading();
                    return;
                }

                // 准备提交数据
                const clientData = {
                    name: this.newClient.name.trim(),
                    client_type: this.newClient.client_type,
                    phone: this.newClient.phone.trim(),
                    address: this.newClient.address?.trim() || '',
                    id_number: this.newClient.id_number?.trim() || '',
                    legal_representative: this.newClient.legal_representative?.trim() || '',
                    is_our_client: this.newClient.is_our_client
                };

                const response = await this.apiCall('POST', '/api/v1/client/clients', clientData);

                // 如果有 OCR 识别结果，创建证件记录
                if (this.ocrFile && this.ocrRecognitionResult && response.id) {
                    this.updateLoadingMessage('正在绑定证件...');
                    try {
                        await this.createIdentityDocForClient(response.id);
                    } catch (docError) {
                        this.logger.warn('证件绑定失败，但当事人已创建');
                    }
                }

                // 自动选中新创建的当事人，根据 is_our_client 自动设置身份
                const autoRole = (response.is_our_client === true) ? 'PRINCIPAL' : 'OPPOSING';
                this.selectedClients.push({
                    client: response,
                    role: autoRole
                });

                // 添加到当事人列表
                this.allClients.unshift(response);

                // 隐藏表单并重置数据
                this.showNewClientForm = false;
                this.resetNewClientForm();

                // 清空搜索
                this.clearSearch();

                this.showSuccess(`当事人"${response.name}"创建成功`);
                this.saveToSession();

            } catch (error) {
                this.logger.error('创建当事人失败');
                this.handleApiError(error);
            } finally {
                this.stopLoading();
            }
        },

        /**
         * 为当事人创建证件记录
         */
        async createIdentityDocForClient(clientId) {
            const formData = new FormData();
            formData.append('client', clientId);
            formData.append('doc_type', this.ocrDocType);
            formData.append('file', this.ocrFile);

            // 添加识别到的到期日期
            if (this.ocrRecognitionResult?.extracted_data?.expiry_date) {
                formData.append('expiry_date', this.ocrRecognitionResult.extracted_data.expiry_date);
            }

            return await this.apiCallForm('POST', '/api/v1/client/identity-docs/', formData);
        },

        /**
         * 验证新建当事人表单
         */
        validateNewClient() {
            const errors = {};
            const fieldsToShake = [];

            // 必填字段验证 - 使用增强的空白字符检测
            if (!this.validateRequiredField(this.newClient.name)) {
                errors.name = '请输入当事人名称';
                fieldsToShake.push('new-client-name');
            }

            // 当事人身份必填验证
            if (this.newClient.is_our_client === null || this.newClient.is_our_client === undefined) {
                errors.is_our_client = '请选择当事人身份（我方/对方）';
                fieldsToShake.push('new-client-identity');
            }

            // 联系电话非必填，但填了要验证格式
            if (this.newClient.phone?.trim() && !this.validatePhoneNumber(this.newClient.phone)) {
                errors.phone = '请输入正确的手机号码（11位手机号）';
                fieldsToShake.push('new-client-phone');
            }

            // 身份证号/统一社会信用代码验证
            if (this.newClient.id_number?.trim()) {
                if (this.newClient.client_type === 'natural') {
                    const idValidation = this.validateIdNumberWithDetails(this.newClient.id_number);
                    if (!idValidation.valid) {
                        errors.id_number = idValidation.message;
                        fieldsToShake.push('new-client-id');
                    }
                } else {
                    if (!this.validateCreditCode(this.newClient.id_number)) {
                        errors.id_number = '统一社会信用代码格式不正确（需要18位有效代码）';
                        fieldsToShake.push('new-client-id');
                    }
                }
            }

            // 法人/非法人组织必须填写法定代表人/负责人
            if ((this.newClient.client_type === 'legal' || this.newClient.client_type === 'non_legal_org')
                && !this.validateRequiredField(this.newClient.legal_representative)) {
                errors.legal_representative = this.newClient.client_type === 'legal' ? '请输入法定代表人姓名' : '请输入负责人姓名';
                fieldsToShake.push('new-client-legal-rep');
            }

            if (Object.keys(errors).length > 0) {
                this.errors = { ...this.errors, ...errors };
                // 触发验证错误动画
                this.triggerValidationAnimation(fieldsToShake);
                // 显示第一个错误的 toast
                const firstError = Object.values(errors)[0];
                if (firstError) {
                    this.showError(firstError);
                }
                return false;
            }

            return true;
        },

        /**
         * 验证必填字段（检测空值和纯空白字符）
         * @param {string} value - 要验证的值
         * @returns {boolean} - 是否有效
         */
        validateRequiredField(value) {
            if (value === null || value === undefined) {
                return false;
            }
            // 检测是否为空或仅包含空白字符（空格、制表符、换行符等）
            const trimmed = String(value).trim();
            return trimmed.length > 0;
        },

        /**
         * 验证身份证号格式（带详细错误信息）
         * 支持 18 位新身份证号和 15 位旧身份证号
         * @param {string} idNumber - 身份证号
         * @returns {object} - { valid: boolean, message: string }
         */
        validateIdNumberWithDetails(idNumber) {
            if (!idNumber) {
                return { valid: true, message: '' }; // 非必填时空值有效
            }

            const cleanId = idNumber.replace(/\s/g, '').toUpperCase();

            // 检查长度
            if (cleanId.length !== 15 && cleanId.length !== 18) {
                return {
                    valid: false,
                    message: `身份证号长度不正确（当前${cleanId.length}位，需要15位或18位）`
                };
            }

            // 18位身份证号正则
            const regex18 = /^[1-9]\d{5}(18|19|20)\d{2}((0[1-9])|(1[0-2]))(([0-2][1-9])|10|20|30|31)\d{3}[0-9X]$/;
            // 15位身份证号正则（旧格式）
            const regex15 = /^[1-9]\d{5}\d{2}((0[1-9])|(1[0-2]))(([0-2][1-9])|10|20|30|31)\d{3}$/;

            if (cleanId.length === 18) {
                // 基本格式验证
                if (!regex18.test(cleanId)) {
                    // 检查具体哪部分格式错误
                    if (!/^[1-9]\d{5}/.test(cleanId)) {
                        return { valid: false, message: '身份证号地区码格式不正确' };
                    }
                    if (!/^.{6}(18|19|20)\d{2}/.test(cleanId)) {
                        return { valid: false, message: '身份证号出生年份格式不正确' };
                    }
                    if (!/^.{10}((0[1-9])|(1[0-2]))/.test(cleanId)) {
                        return { valid: false, message: '身份证号出生月份格式不正确（01-12）' };
                    }
                    if (!/^.{12}(([0-2][1-9])|10|20|30|31)/.test(cleanId)) {
                        return { valid: false, message: '身份证号出生日期格式不正确（01-31）' };
                    }
                    if (!/[0-9X]$/.test(cleanId)) {
                        return { valid: false, message: '身份证号最后一位只能是数字或X' };
                    }
                    return { valid: false, message: '身份证号格式不正确' };
                }

                // 校验码验证
                if (!this.validateIdChecksum(cleanId)) {
                    return { valid: false, message: '身份证号校验码不正确，请检查是否输入有误' };
                }
            } else if (cleanId.length === 15) {
                if (!regex15.test(cleanId)) {
                    return { valid: false, message: '15位身份证号格式不正确' };
                }
            }

            return { valid: true, message: '' };
        },

        /**
         * 验证手机号格式
         */
        validatePhoneNumber(phone) {
            // 中国大陆手机号正则：1开头，第二位3-9，总共11位
            const phoneRegex = /^1[3-9]\d{9}$/;
            return phoneRegex.test(phone.replace(/\s|-/g, ''));
        },

        /**
         * 验证身份证号格式
         * 支持 18 位新身份证号和 15 位旧身份证号
         */
        validateIdNumber(idNumber) {
            const cleanId = idNumber.replace(/\s/g, '').toUpperCase();

            // 18位身份证号正则
            const regex18 = /^[1-9]\d{5}(18|19|20)\d{2}((0[1-9])|(1[0-2]))(([0-2][1-9])|10|20|30|31)\d{3}[0-9X]$/;
            // 15位身份证号正则（旧格式）
            const regex15 = /^[1-9]\d{5}\d{2}((0[1-9])|(1[0-2]))(([0-2][1-9])|10|20|30|31)\d{3}$/;

            // 基本格式验证
            if (!regex18.test(cleanId) && !regex15.test(cleanId)) {
                return false;
            }

            // 18位身份证号校验码验证
            if (cleanId.length === 18) {
                return this.validateIdChecksum(cleanId);
            }

            return true;
        },

        /**
         * 验证18位身份证号校验码
         */
        validateIdChecksum(idNumber) {
            // 加权因子
            const weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];
            // 校验码对应值
            const checkCodes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2'];

            let sum = 0;
            for (let i = 0; i < 17; i++) {
                sum += parseInt(idNumber.charAt(i)) * weights[i];
            }

            const checkCode = checkCodes[sum % 11];
            return idNumber.charAt(17).toUpperCase() === checkCode;
        },

        /**
         * 验证统一社会信用代码格式
         */
        validateCreditCode(code) {
            // 统一社会信用代码：18位，第一位为数字或大写字母，其余为数字或大写字母
            const creditCodeRegex = /^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$/;
            return creditCodeRegex.test(code.replace(/\s/g, '').toUpperCase());
        },

        // ========== 合同管理 ==========

        /**
         * 合同类型变更处理
         */
        onCaseTypeChange() {
            this.logger.debug('合同类型变更:', this.contract.case_type);
            // 如果切换到不需要阶段的类型，清空已选阶段
            if (!this.needsStageSelection) {
                this.contract.representation_stages = [];
            }
            this.saveToSession();
        },

        /**
         * 判断当前合同类型是否需要选择代理阶段
         * 只有民商事、刑事、行政、劳动仲裁、商事仲裁需要选择阶段
         */
        get needsStageSelection() {
            const applicableTypes = ['civil', 'criminal', 'administrative', 'labor', 'intl'];
            return applicableTypes.includes(this.contract.case_type);
        },

        /**
         * 切换代理阶段选择
         */
        toggleStage(stageValue) {
            const index = this.contract.representation_stages.indexOf(stageValue);
            if (index === -1) {
                this.contract.representation_stages.push(stageValue);
            } else {
                this.contract.representation_stages.splice(index, 1);
            }
            this.saveToSession();
        },

        /**
         * 检查阶段是否已选中
         */
        isStageSelected(stageValue) {
            return this.contract.representation_stages.includes(stageValue);
        },

        /**
         * 收费模式变更处理
         */
        onFeeModeChange() {
            this.logger.debug('收费模式变更:', this.contract.fee_mode);
            // 清除不相关的字段
            if (this.contract.fee_mode === 'FIXED') {
                this.contract.risk_rate = '';
            } else if (this.contract.fee_mode === 'FULL_RISK') {
                this.contract.fixed_amount = '';
            }
            this.saveToSession();
        },

        /**
         * 加载律师列表
         */
        async loadLawyers() {
            if (this.lawyersLoaded || this.lawyersLoading) {
                return;
            }

            try {
                this.lawyersLoading = true;

                const response = await this.apiCall('GET', '/api/v1/organization/lawyers');

                if (Array.isArray(response)) {
                    this.lawyers = response;
                } else if (response.results) {
                    this.lawyers = response.results;
                } else {
                    this.lawyers = [];
                }

                this.lawyersLoaded = true;
                this.logger.debug(`加载了 ${this.lawyers.length} 个律师`);

            } catch (error) {
                this.logger.error('加载律师列表失败');
                this.showError('加载律师列表失败，请重试');
            } finally {
                this.lawyersLoading = false;
            }
        },

        /**
         * 获取律师名称
         */
        getLawyerName(lawyerId) {
            const lawyer = this.lawyers.find(l => l.id === parseInt(lawyerId));
            return lawyer ? (lawyer.real_name || lawyer.username) : '';
        },

        /**
         * 获取当事人身份标签
         */
        getPartyRoleLabel(role) {
            const roles = window.onboardingData?.partyRoles || [];
            const found = roles.find(r => r.value === role);
            return found ? found.label : role;
        },

        /**
         * 添加协办律师
         */
        addAssistantLawyer(lawyerId) {
            if (!lawyerId) return;

            const id = parseInt(lawyerId);
            if (!this.contract.assistant_lawyers.includes(id) && id !== parseInt(this.contract.primary_lawyer)) {
                this.contract.assistant_lawyers.push(id);
                this.saveToSession();
            }
        },

        /**
         * 移除协办律师
         */
        removeAssistantLawyer(lawyerId) {
            this.contract.assistant_lawyers = this.contract.assistant_lawyers.filter(id => id !== lawyerId);
            this.saveToSession();
        },

        /**
         * 显示/隐藏对方当事人表单
         */
        toggleOpposingPartyForm() {
            this.showOpposingPartyForm = !this.showOpposingPartyForm;
            if (this.showOpposingPartyForm) {
                this.initializeOpposingPartyForm();
                this.opposingSearchQuery = '';
                this.opposingSearchResults = [];
            }
        },

        /**
         * 搜索对方当事人
         */
        async searchOpposingParties() {
            if (!this.opposingSearchQuery.trim()) {
                this.opposingSearchResults = [];
                return;
            }

            try {
                const response = await this.apiCall('GET', `/api/v1/client/clients?search=${encodeURIComponent(this.opposingSearchQuery.trim())}`);

                if (response.results) {
                    this.opposingSearchResults = response.results;
                } else if (Array.isArray(response)) {
                    this.opposingSearchResults = response;
                } else {
                    this.opposingSearchResults = [];
                }

                // 过滤掉已添加的对方当事人和已选择的当事人
                const existingIds = [
                    ...this.selectedClients.map(item => item.client.id),
                    ...(this.contract.opposing_parties || []).map(p => p.id)
                ];
                this.opposingSearchResults = this.opposingSearchResults.filter(c => !existingIds.includes(c.id));

            } catch (error) {
                this.logger.error('搜索对方当事人失败');
                this.opposingSearchResults = [];
            }
        },

        /**
         * 从搜索结果添加对方当事人
         */
        addOpposingPartyFromSearch(client) {
            if (!this.contract.opposing_parties) {
                this.contract.opposing_parties = [];
            }

            // 检查是否已添加
            if (this.contract.opposing_parties.some(p => p.id === client.id)) {
                this.showError('该当事人已添加');
                return;
            }

            this.contract.opposing_parties.push({
                id: client.id,
                name: client.name,
                client_type: client.client_type,
                phone: client.phone,
                id_number: client.id_number,
                isNew: false
            });

            // 清空搜索
            this.opposingSearchQuery = '';
            this.opposingSearchResults = [];
            this.showOpposingPartyForm = false;

            this.showSuccess(`已添加对方当事人"${client.name}"`);
            this.saveToSession();
        },

        /**
         * 创建并添加对方当事人
         */
        async createAndAddOpposingParty() {
            if (!this.newOpposingParty.name?.trim()) {
                this.showError('请输入对方当事人名称');
                return;
            }

            try {
                this.startLoading('正在创建对方当事人');

                // 准备数据
                const clientData = {
                    name: this.newOpposingParty.name.trim(),
                    client_type: this.newOpposingParty.client_type || 'natural',
                    phone: this.newOpposingParty.phone?.trim() || '',
                    id_number: this.newOpposingParty.id_number?.trim() || '',
                    is_our_client: false  // 对方当事人不是我方客户
                };

                const response = await this.apiCall('POST', '/api/v1/client/clients', clientData);

                // 添加到对方当事人列表
                if (!this.contract.opposing_parties) {
                    this.contract.opposing_parties = [];
                }

                this.contract.opposing_parties.push({
                    id: response.id,
                    name: response.name,
                    client_type: response.client_type,
                    phone: response.phone,
                    id_number: response.id_number,
                    isNew: true
                });

                // 重置表单
                this.initializeOpposingPartyForm();
                this.showOpposingPartyForm = false;

                this.showSuccess(`对方当事人"${response.name}"创建成功`);
                this.saveToSession();

            } catch (error) {
                this.logger.error('创建对方当事人失败');
                this.handleApiError(error);
            } finally {
                this.stopLoading();
            }
        },

        /**
         * 移除对方当事人
         */
        removeOpposingParty(index) {
            if (this.contract.opposing_parties && this.contract.opposing_parties[index]) {
                const removed = this.contract.opposing_parties.splice(index, 1)[0];
                this.showSuccess(`已移除对方当事人"${removed.name}"`);
                this.saveToSession();
            }
        },

        /**
         * 创建合同
         */
        async createContract() {
            try {
                this.startLoading('正在创建合同');
                this.clearErrors();

                // 验证合同数据
                if (!this.validateContract()) {
                    this.stopLoading();
                    return null;
                }

                // 更新加载消息
                this.updateLoadingMessage('正在准备合同数据');

                // 构建律师 ID 列表（主办律师在前）
                const lawyerIds = [parseInt(this.contract.primary_lawyer)];
                if (this.contract.assistant_lawyers && this.contract.assistant_lawyers.length > 0) {
                    lawyerIds.push(...this.contract.assistant_lawyers);
                }

                // 构建当事人列表（使用用户选择的身份）
                const parties = [
                    // 已选择的当事人（带身份）
                    ...this.selectedClients.map(item => ({
                        client_id: item.client.id,
                        role: item.role
                    })),
                    // 对方当事人（从合同步骤添加的）
                    ...(this.contract.opposing_parties || []).map(party => ({
                        client_id: party.id,
                        role: 'OPPOSING'
                    }))
                ];

                // 构建合同数据
                const contractData = {
                    name: this.contract.name,
                    case_type: this.contract.case_type,
                    fee_mode: this.contract.fee_mode,
                    specified_date: this.contract.specified_date || new Date().toISOString().split('T')[0],
                    lawyer_ids: lawyerIds,
                    parties: parties,
                    status: 'active'  // 默认状态为在办（小写，与后端枚举一致）
                };

                // 添加代理阶段（如果需要）
                if (this.needsStageSelection && this.contract.representation_stages.length > 0) {
                    // 转换 Alpine.js Proxy 数组为普通数组
                    contractData.representation_stages = [...this.contract.representation_stages];
                }

                // 添加收费相关字段（验证已在 validateContract 中完成）
                if (this.contract.fee_mode === 'FIXED' || this.contract.fee_mode === 'SEMI_RISK') {
                    const amount = parseFloat(this.contract.fixed_amount);
                    if (!isNaN(amount) && amount > 0) {
                        contractData.fixed_amount = amount;
                    } else {
                        this.logger.debug('fixed_amount 无效');
                        this.showError('请输入有效的固定金额');
                        return null;
                    }
                }
                if (this.contract.fee_mode === 'SEMI_RISK' || this.contract.fee_mode === 'FULL_RISK') {
                    const rate = parseFloat(this.contract.risk_rate);
                    if (!isNaN(rate) && rate > 0) {
                        contractData.risk_rate = rate;
                    } else {
                        this.logger.debug('risk_rate 无效');
                        this.showError('请输入有效的风险比例');
                        return null;
                    }
                }

                // 更新加载消息
                this.updateLoadingMessage('正在提交合同信息');

                const response = await this.apiCall('POST', '/api/v1/contracts/contracts', contractData);

                // 保存合同ID用于后续案件创建
                this.contract.id = response.id;
                this.createdContract = response;

                this.showSuccessAnimation('合同创建成功');
                this.saveToSession();

                return response;

            } catch (error) {
                this.logger.error('创建合同失败');
                this.handleApiError(error);
                return null;
            } finally {
                this.stopLoading();
            }
        },

        /**
         * 验证合同数据
         */
        validateContract() {
            const errors = {};
            const fieldsToShake = [];

            // 使用增强的必填字段验证
            if (!this.validateRequiredField(this.contract.name)) {
                errors.contract_name = '请输入合同名称';
                fieldsToShake.push('contract-name');
            }

            if (!this.contract.case_type) {
                errors.case_type = '请选择合同类型';
                fieldsToShake.push('contract-case-type');
            }

            if (!this.contract.fee_mode) {
                errors.fee_mode = '请选择收费模式';
                fieldsToShake.push('contract-fee-mode');
            }

            if (!this.contract.primary_lawyer) {
                errors.primary_lawyer = '请选择主办律师';
                fieldsToShake.push('primary-lawyer');
            }

            // 收费模式相关验证 - 必须是正数
            if (this.contract.fee_mode === 'FIXED') {
                const amount = parseFloat(this.contract.fixed_amount);
                if (!amount || amount <= 0) {
                    errors.fixed_amount = '请输入有效的固定金额（必须大于0）';
                    fieldsToShake.push('contract-fixed-amount');
                }
            }
            if (this.contract.fee_mode === 'SEMI_RISK') {
                const amount = parseFloat(this.contract.fixed_amount);
                if (!amount || amount <= 0) {
                    errors.fixed_amount = '请输入有效的前期律师费（必须大于0）';
                    fieldsToShake.push('contract-fixed-amount');
                }
                const rate = parseFloat(this.contract.risk_rate);
                if (!rate || rate <= 0) {
                    errors.risk_rate = '请输入有效的风险比例（必须大于0）';
                    fieldsToShake.push('contract-risk-rate');
                }
            }
            if (this.contract.fee_mode === 'FULL_RISK') {
                const rate = parseFloat(this.contract.risk_rate);
                if (!rate || rate <= 0) {
                    errors.risk_rate = '请输入有效的风险比例（必须大于0）';
                    fieldsToShake.push('contract-risk-rate');
                }
            }

            if (Object.keys(errors).length > 0) {
                this.errors = { ...this.errors, ...errors };
                this.triggerValidationAnimation(fieldsToShake);
                // 显示第一个错误的 toast
                const firstError = Object.values(errors)[0];
                if (firstError) {
                    this.showError(firstError);
                }
                return false;
            }

            return true;
        },

        // ========== 案件管理 ==========

        /**
         * 创建案件
         */
        async createCase() {
            try {
                this.startLoading('正在创建案件');
                this.clearErrors();

                // 验证案件数据
                if (!this.validateCase()) {
                    this.stopLoading();
                    return null;
                }

                // 更新加载消息
                this.updateLoadingMessage('正在准备案件数据');

                // 构建当事人列表（包含诉讼地位）
                const parties = [];

                // 添加已选择的当事人（使用用户选择的身份对应的诉讼地位）
                for (const item of this.selectedClients) {
                    parties.push({
                        client_id: item.client.id,
                        legal_status: this.caseInfo.party_roles[item.client.id] || 'plaintiff'
                    });
                }

                // 添加对方当事人
                if (this.contract.opposing_parties && this.contract.opposing_parties.length > 0) {
                    for (const party of this.contract.opposing_parties) {
                        parties.push({
                            client_id: party.id,
                            legal_status: this.caseInfo.party_roles[party.id] || 'defendant'
                        });
                    }
                }

                // 构建律师指派列表（从合同继承）
                const assignments = [];

                // 添加主办律师
                if (this.contract.primary_lawyer) {
                    assignments.push({
                        lawyer_id: parseInt(this.contract.primary_lawyer)
                    });
                }

                // 添加协办律师
                if (this.contract.assistant_lawyers && this.contract.assistant_lawyers.length > 0) {
                    for (const lawyerId of this.contract.assistant_lawyers) {
                        assignments.push({
                            lawyer_id: parseInt(lawyerId)
                        });
                    }
                }

                // 构建案件数据（符合 CaseCreateFull schema）
                const caseData = {
                    case: {
                        name: this.caseInfo.name.trim(),
                        cause_of_action: this.caseInfo.cause_of_action.trim(),
                        target_amount: this.caseInfo.target_amount ? parseFloat(this.caseInfo.target_amount) : null,
                        current_stage: this.caseInfo.current_stage || null,
                        case_type: this.contract.case_type,  // 从合同继承案件类型
                        status: 'active',
                        is_archived: false
                    },
                    parties: parties,
                    assignments: assignments,  // 律师指派从合同继承
                    logs: [],
                    supervising_authorities: []
                };

                // 更新加载消息
                this.updateLoadingMessage('正在提交案件信息');

                // 调用案件创建 API（正确的端点）
                const response = await this.apiCall('POST', '/api/v1/cases/full', caseData);

                // 保存案件ID（API 返回的是 CaseOut，直接包含 id）
                this.caseInfo.id = response.id;
                this.createdCase = response;

                // 更新加载消息
                this.updateLoadingMessage('正在关联合同');

                // 关联合同到案件
                if (this.contract.id) {
                    try {
                        await this.apiCall('PUT', `/api/v1/cases/${this.caseInfo.id}`, {
                            contract_id: this.contract.id
                        });
                    } catch (linkError) {
                        this.logger.warn('关联合同失败，但案件已创建');
                    }
                }

                this.showSuccessAnimation('案件创建成功');
                this.saveToSession();

                return response;

            } catch (error) {
                this.logger.error('创建案件失败');
                this.handleApiError(error);
                return null;
            } finally {
                this.stopLoading();
            }
        },

        /**
         * 验证案件数据
         */
        validateCase() {
            const errors = {};
            const fieldsToShake = [];

            // 使用增强的必填字段验证
            if (!this.validateRequiredField(this.caseInfo.name)) {
                errors.case_name = '请输入案件名称';
                fieldsToShake.push('case-name');
            }

            if (!this.validateRequiredField(this.caseInfo.cause_of_action)) {
                errors.cause_of_action = '请输入案由';
                fieldsToShake.push('case-cause-of-action');
            }

            if (Object.keys(errors).length > 0) {
                this.errors = { ...this.errors, ...errors };
                this.triggerValidationAnimation(fieldsToShake);
                // 显示第一个错误的 toast
                const firstError = Object.values(errors)[0];
                if (firstError) {
                    this.showError(firstError);
                }
                return false;
            }

            return true;
        },

        // ========== 数据持久化 ==========

        /**
         * 保存数据到 sessionStorage
         */
        saveToSession() {
            try {
                const selectedClientRefs = this.selectedClients
                    .map(item => ({ client_id: item.client?.id, role: item.role }))
                    .filter(item => item.client_id);

                const opposingPartyIds = (this.contract.opposing_parties || [])
                    .map(party => party?.id)
                    .filter(Boolean);

                const data = {
                    currentStep: this.currentStep,
                    selectedClientRefs,
                    contract: {
                        id: this.contract.id || null,
                        name: this.contract.name || '',
                        case_type: this.contract.case_type || '',
                        fee_mode: this.contract.fee_mode || '',
                        fixed_amount: this.contract.fixed_amount || '',
                        risk_rate: this.contract.risk_rate || '',
                        specified_date: this.contract.specified_date || '',
                        primary_lawyer: this.contract.primary_lawyer || '',
                        assistant_lawyers: Array.isArray(this.contract.assistant_lawyers) ? this.contract.assistant_lawyers : [],
                        representation_stages: Array.isArray(this.contract.representation_stages) ? this.contract.representation_stages : [],
                        opposing_party_ids: opposingPartyIds
                    },
                    caseInfo: {
                        id: this.caseInfo.id || null,
                        name: this.caseInfo.name || '',
                        cause_of_action: this.caseInfo.cause_of_action || '',
                        target_amount: this.caseInfo.target_amount || '',
                        current_stage: this.caseInfo.current_stage || '',
                        party_roles: this.caseInfo.party_roles || {}
                    },
                    showNewClientForm: this.showNewClientForm,
                    timestamp: Date.now()
                };

                sessionStorage.setItem('onboarding_wizard_data', JSON.stringify(data));
            } catch (error) {
                this.logger.warn('保存会话数据失败');
            }
        },

        /**
         * 从 sessionStorage 加载数据
         */
        loadFromSession() {
            try {
                const saved = sessionStorage.getItem('onboarding_wizard_data');
                if (saved) {
                    const data = JSON.parse(saved);

                    // 检查数据是否过期（24小时）
                    if (Date.now() - data.timestamp < 24 * 60 * 60 * 1000) {
                        this.currentStep = data.currentStep || 1;
                        this._selectedClientRefs = data.selectedClientRefs || null;
                        this.contract = data.contract || {};
                        this._opposingPartyIds = this.contract.opposing_party_ids || null;
                        this.contract.opposing_parties = [];
                        this.caseInfo = data.caseInfo || {};
                        this.showNewClientForm = data.showNewClientForm || false;

                        this.logger.debug('已恢复会话数据');
                    } else {
                        // 数据过期，清除
                        this.clearSession();
                    }
                }
            } catch (error) {
                this.logger.warn('加载会话数据失败');
                this.clearSession();
            }
        },

        /**
         * 清除会话数据
         */
        clearSession() {
            sessionStorage.removeItem('onboarding_wizard_data');
        },

        // ========== API 调用 ==========

        /**
         * 统一 API 调用方法
         * 自动处理 CSRF token 和错误响应
         *
         * @param {string} method - HTTP 方法 (GET, POST, PUT, DELETE)
         * @param {string} url - API 端点 URL
         * @param {object|null} data - 请求数据（POST/PUT 时使用）
         * @returns {Promise<object>} - API 响应数据
         * @throws {object} - 包含 status 和 data 的错误对象
         */
        async apiCall(method, url, data = null) {
            const requestUrl = this.normalizeApiUrl(url);
            const options = {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                credentials: 'same-origin' // 确保发送 cookies
            };

            // 对于非 GET 请求，添加 CSRF token
            if (method !== 'GET') {
                const csrfToken = this.getCSRFToken();
                if (csrfToken) {
                    options.headers['X-CSRFToken'] = csrfToken;
                } else {
                    this.logger.warn('CSRF token 未找到，请求可能会失败');
                }
            }

            if (data) {
                options.body = JSON.stringify(data);
            }

            try {
                const response = await fetch(requestUrl, options);

                if (!response.ok) {
                    // 尝试解析错误响应
                    let errorData = {};
                    const contentType = response.headers.get('content-type');

                    if (contentType && contentType.includes('application/json')) {
                        try {
                            errorData = await response.json();
                        } catch (parseError) {
                            this.logger.warn('无法解析错误响应 JSON');
                            errorData = { detail: '服务器返回了无效的响应' };
                        }
                    } else {
                        // 非 JSON 响应（可能是 HTML 错误页面）
                        const textContent = await response.text().catch(() => '');
                        errorData = {
                            detail: this.extractErrorFromHtml(textContent) || `HTTP ${response.status} 错误`
                        };
                    }

                    throw {
                        status: response.status,
                        statusText: response.statusText,
                        data: errorData,
                        url: requestUrl
                    };
                }

                // 处理空响应
                const contentType = response.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    return {};
                }

                return await response.json();

            } catch (error) {
                // 网络错误或其他异常
                if (!error.status) {
                    this.logger.error('网络请求失败');
                    throw {
                        status: 0,
                        statusText: 'Network Error',
                        data: { detail: '网络连接失败，请检查网络后重试' },
                        url: requestUrl,
                        originalError: error
                    };
                }
                throw error;
            }
        },

        async apiCallForm(method, url, formData) {
            const requestUrl = this.normalizeApiUrl(url);
            const options = {
                method,
                headers: {
                    'Accept': 'application/json'
                },
                credentials: 'same-origin',
                body: formData
            };

            if (method !== 'GET') {
                const csrfToken = this.getCSRFToken();
                if (csrfToken) {
                    options.headers['X-CSRFToken'] = csrfToken;
                }
            }

            try {
                const response = await fetch(requestUrl, options);

                if (!response.ok) {
                    let errorData = {};
                    const contentType = response.headers.get('content-type');
                    if (contentType && contentType.includes('application/json')) {
                        try {
                            errorData = await response.json();
                        } catch (parseError) {
                            errorData = { detail: '服务器返回了无效的响应' };
                        }
                    } else {
                        const textContent = await response.text().catch(() => '');
                        errorData = {
                            detail: this.extractErrorFromHtml(textContent) || `HTTP ${response.status} 错误`
                        };
                    }

                    throw {
                        status: response.status,
                        statusText: response.statusText,
                        data: errorData,
                        url: requestUrl
                    };
                }

                const contentType = response.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    return {};
                }
                return await response.json();
            } catch (error) {
                if (!error.status) {
                    this.logger.error('网络请求失败');
                    throw {
                        status: 0,
                        statusText: 'Network Error',
                        data: { detail: '网络连接失败，请检查网络后重试' },
                        url: requestUrl,
                        originalError: error
                    };
                }
                throw error;
            }
        },

        normalizeApiUrl(url) {
            if (typeof url !== 'string') {
                return url;
            }
            const defaultPrefix = '/api/v1';
            if (!this.apiBase) {
                return url;
            }
            const base = this.apiBase.endsWith('/') ? this.apiBase.slice(0, -1) : this.apiBase;
            if (url.startsWith(defaultPrefix)) {
                return base + url.slice(defaultPrefix.length);
            }
            return url;
        },

        /**
         * 从 HTML 错误页面提取错误信息
         * @param {string} html - HTML 内容
         * @returns {string|null} - 提取的错误信息
         */
        extractErrorFromHtml(html) {
            if (!html) return null;

            // 尝试从常见的错误页面结构中提取信息
            const patterns = [
                /<title>([^<]+)<\/title>/i,
                /<h1[^>]*>([^<]+)<\/h1>/i,
                /<p class="error[^"]*">([^<]+)<\/p>/i
            ];

            for (const pattern of patterns) {
                const match = html.match(pattern);
                if (match && match[1]) {
                    const text = match[1].trim();
                    // 过滤掉无意义的标题
                    if (text && !text.includes('<!DOCTYPE') && text.length < 200) {
                        return text;
                    }
                }
            }

            return null;
        },

        /**
         * 获取 CSRF Token
         * 优先从 cookie 获取，其次从 meta 标签获取
         *
         * @returns {string} - CSRF token 或空字符串
         */
        getCSRFToken() {
            // 方法1: 从 cookie 获取 (Django 默认方式)
            const cookieToken = this.getCSRFTokenFromCookie();
            if (cookieToken) {
                return cookieToken;
            }

            // 方法2: 从 meta 标签获取 (备用方式)
            const metaToken = this.getCSRFTokenFromMeta();
            if (metaToken) {
                return metaToken;
            }

            // 方法3: 从隐藏表单字段获取 (最后备用)
            const formToken = this.getCSRFTokenFromForm();
            if (formToken) {
                return formToken;
            }

            this.logger.warn('无法获取 CSRF token');
            return '';
        },

        /**
         * 从 cookie 获取 CSRF token
         * @returns {string|null}
         */
        getCSRFTokenFromCookie() {
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'csrftoken') {
                    return decodeURIComponent(value);
                }
            }
            return null;
        },

        /**
         * 从 meta 标签获取 CSRF token
         * @returns {string|null}
         */
        getCSRFTokenFromMeta() {
            const metaTag = document.querySelector('meta[name="csrf-token"]');
            return metaTag ? metaTag.getAttribute('content') : null;
        },

        /**
         * 从隐藏表单字段获取 CSRF token
         * @returns {string|null}
         */
        getCSRFTokenFromForm() {
            const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
            return input ? input.value : null;
        },

        // ========== 错误处理 ==========

        /**
         * 统一处理 API 错误
         * 根据不同的 HTTP 状态码采取相应的处理措施
         *
         * @param {object} error - 错误对象，包含 status 和 data 属性
         *
         * 处理策略:
         * - 0: 网络错误
         * - 401: 未授权，重定向到登录页
         * - 400: 验证错误，映射到表单字段
         * - 403: 权限不足
         * - 404: 资源不存在
         * - 409: 冲突（如重复数据）
         * - 422: 不可处理的实体
         * - 429: 请求过于频繁
         * - 500+: 服务器错误
         */
        handleApiError(error) {
            this.logger.error('API 错误');

            // 网络错误（无法连接到服务器）
            if (error.status === 0) {
                this.showError('网络连接失败，请检查网络后重试');
                return;
            }

            // 401 未授权 - 重定向到登录页
            if (error.status === 401) {
                this.showError('登录已过期，正在跳转到登录页面...');
                // 延迟跳转，让用户看到提示
                setTimeout(() => {
                    const currentPath = encodeURIComponent(window.location.pathname + window.location.search);
                    window.location.href = '/admin/login/?next=' + currentPath;
                }, 1000);
                return;
            }

            // 400 验证错误 - 映射到表单字段
            if (error.status === 400 && error.data) {
                const mappedErrors = this.mapApiErrors(error.data);
                this.errors = { ...this.errors, ...mappedErrors };

                // 触发错误字段的动画
                const fieldsToShake = Object.keys(mappedErrors)
                    .filter(key => key !== '_global')
                    .map(key => this.getFieldIdFromErrorKey(key))
                    .filter(id => id);

                if (fieldsToShake.length > 0) {
                    this.triggerValidationAnimation(fieldsToShake);
                }

                // 显示第一个错误消息
                const firstError = Object.values(mappedErrors)[0];
                if (firstError) {
                    this.showError(firstError);
                } else {
                    this.showError('提交的数据有误，请检查后重试');
                }
                return;
            }

            // 403 权限不足
            if (error.status === 403) {
                const message = error.data?.detail || '没有权限执行此操作';
                this.showError(message);
                return;
            }

            // 404 资源不存在
            if (error.status === 404) {
                const message = error.data?.detail || '请求的资源不存在';
                this.showError(message);
                return;
            }

            // 409 冲突（如重复数据）
            if (error.status === 409) {
                const message = error.data?.detail || '数据冲突，可能已存在相同的记录';
                this.showError(message);
                return;
            }

            // 422 不可处理的实体
            if (error.status === 422) {
                const message = error.data?.detail || '提交的数据格式不正确';
                this.showError(message);
                return;
            }

            // 429 请求过于频繁
            if (error.status === 429) {
                const retryAfter = error.data?.retry_after || 60;
                this.showError(`请求过于频繁，请 ${retryAfter} 秒后重试`);
                return;
            }

            // 500+ 服务器错误
            if (error.status >= 500) {
                let message = '服务器错误，请稍后重试';

                // 根据具体状态码提供更详细的信息
                if (error.status === 502) {
                    message = '服务器网关错误，请稍后重试';
                } else if (error.status === 503) {
                    message = '服务暂时不可用，请稍后重试';
                } else if (error.status === 504) {
                    message = '服务器响应超时，请稍后重试';
                }

                // 如果有详细错误信息，记录到控制台
                if (error.data?.detail) {
                    this.logger.debug('服务器错误详情已隐藏');
                }

                this.showError(message);
                return;
            }

            // 其他未知错误
            const message = error.data?.detail || '操作失败，请稍后重试';
            this.showError(message);
        },

        /**
         * 映射 API 错误到表单字段
         */
        mapApiErrors(errorData) {
            const errors = {};

            if (typeof errorData === 'string') {
                errors._global = errorData;
                return errors;
            }

            if (errorData.detail) {
                // Django REST Framework 标准错误格式
                if (typeof errorData.detail === 'string') {
                    errors._global = errorData.detail;
                } else if (Array.isArray(errorData.detail)) {
                    errors._global = errorData.detail.join(', ');
                }
                return errors;
            }

            if (errorData.non_field_errors) {
                // 非字段错误
                errors._global = Array.isArray(errorData.non_field_errors)
                    ? errorData.non_field_errors.join(', ')
                    : errorData.non_field_errors;
            }

            // 字段级错误映射
            const fieldMapping = {
                // 当事人字段映射
                'name': 'name',
                'client_type': 'client_type',
                'phone': 'phone',
                'address': 'address',
                'id_number': 'id_number',
                'legal_representative': 'legal_representative',

                // 合同字段映射
                'contract_name': 'contract_name',
                'case_type': 'case_type',
                'fee_mode': 'fee_mode',
                'fixed_amount': 'fixed_amount',
                'risk_rate': 'risk_rate',
                'specified_date': 'specified_date',
                'primary_lawyer': 'primary_lawyer',
                'lawyer_ids': 'primary_lawyer',
                'parties': '_global',

                // 案件字段映射
                'case_name': 'case_name',
                'cause_of_action': 'cause_of_action',
                'target_amount': 'target_amount',
                'current_stage': 'current_stage',

                // 嵌套字段映射
                'case.name': 'case_name',
                'case.cause_of_action': 'cause_of_action',
                'case.target_amount': 'target_amount'
            };

            for (const [field, messages] of Object.entries(errorData)) {
                if (field === 'detail' || field === 'non_field_errors') {
                    continue;
                }

                // 获取映射后的字段名
                const mappedField = fieldMapping[field] || field;

                // 处理错误消息
                let errorMessage;
                if (Array.isArray(messages)) {
                    errorMessage = messages[0];
                } else if (typeof messages === 'object') {
                    // 嵌套对象错误
                    errorMessage = this.flattenNestedErrors(messages);
                } else {
                    errorMessage = messages;
                }

                // 翻译常见错误消息
                errorMessage = this.translateErrorMessage(errorMessage);

                errors[mappedField] = errorMessage;
            }

            return errors;
        },

        /**
         * 扁平化嵌套错误对象
         */
        flattenNestedErrors(nestedErrors) {
            const messages = [];

            for (const [key, value] of Object.entries(nestedErrors)) {
                if (Array.isArray(value)) {
                    messages.push(`${key}: ${value.join(', ')}`);
                } else if (typeof value === 'object') {
                    messages.push(`${key}: ${this.flattenNestedErrors(value)}`);
                } else {
                    messages.push(`${key}: ${value}`);
                }
            }

            return messages.join('; ');
        },

        /**
         * 翻译常见错误消息
         */
        translateErrorMessage(message) {
            const translations = {
                'This field is required.': '此字段为必填项',
                'This field may not be blank.': '此字段不能为空',
                'This field may not be null.': '此字段不能为空',
                'Enter a valid email address.': '请输入有效的邮箱地址',
                'Enter a valid phone number.': '请输入有效的电话号码',
                'Ensure this value is greater than or equal to': '请确保此值大于或等于',
                'Ensure this value is less than or equal to': '请确保此值小于或等于',
                'A valid integer is required.': '请输入有效的整数',
                'A valid number is required.': '请输入有效的数字',
                'Invalid pk': '无效的选项',
                'Object with pk': '所选对象',
                'does not exist.': '不存在',
                'This field must be unique.': '此字段值已存在',
                'client with this id number already exists.': '该证件号已存在',
                'client with this name already exists.': '该名称已存在'
            };

            // 精确匹配
            if (translations[message]) {
                return translations[message];
            }

            // 部分匹配
            for (const [english, chinese] of Object.entries(translations)) {
                if (message.includes(english)) {
                    return message.replace(english, chinese);
                }
            }

            return message;
        },

        /**
         * 根据错误键获取对应的表单字段 ID
         */
        getFieldIdFromErrorKey(errorKey) {
            const fieldIdMapping = {
                // 当事人字段
                'name': 'new-client-name',
                'phone': 'new-client-phone',
                'id_number': 'new-client-id',
                'legal_representative': 'new-client-legal-rep',

                // 合同字段
                'contract_name': 'contract-name',
                'case_type': 'contract-case-type',
                'fee_mode': 'contract-fee-mode',
                'fixed_amount': 'contract-fixed-amount',
                'risk_rate': 'contract-risk-rate',
                'specified_date': 'contract-specified-date',
                'primary_lawyer': 'primary-lawyer',

                // 案件字段
                'case_name': 'case-name',
                'cause_of_action': 'case-cause-of-action',
                'target_amount': 'case-target-amount',
                'current_stage': 'case-current-stage'
            };

            return fieldIdMapping[errorKey] || null;
        },

        /**
         * 显示验证错误
         */
        showValidationErrors() {
            const errors = {};
            const fieldsToShake = [];

            switch (this.currentStep) {
                case 1:
                    if (this.selectedClients.length === 0) {
                        errors._global = '请选择至少一个当事人';
                    }
                    break;
                case 2:
                    // 使用增强的必填字段验证
                    if (!this.validateRequiredField(this.contract.name)) {
                        errors.contract_name = '请输入合同名称';
                        fieldsToShake.push('contract-name');
                    }
                    if (!this.contract.case_type) {
                        errors.case_type = '请选择合同类型';
                        fieldsToShake.push('contract-case-type');
                    }
                    if (!this.contract.fee_mode) {
                        errors.fee_mode = '请选择收费模式';
                        fieldsToShake.push('contract-fee-mode');
                    }
                    if (!this.contract.primary_lawyer) {
                        errors.primary_lawyer = '请选择主办律师';
                        fieldsToShake.push('primary-lawyer');
                    }

                    // 收费模式相关验证
                    if (this.contract.fee_mode === 'FIXED' && !this.contract.fixed_amount) {
                        errors.fixed_amount = '请输入固定金额';
                        fieldsToShake.push('contract-fixed-amount');
                    }
                    if (this.contract.fee_mode === 'SEMI_RISK') {
                        if (!this.contract.fixed_amount) {
                            errors.fixed_amount = '请输入前期律师费';
                            fieldsToShake.push('contract-fixed-amount');
                        }
                        if (!this.contract.risk_rate) {
                            errors.risk_rate = '请输入风险比例';
                            fieldsToShake.push('contract-risk-rate');
                        }
                    }
                    if (this.contract.fee_mode === 'FULL_RISK' && !this.contract.risk_rate) {
                        errors.risk_rate = '请输入风险比例';
                        fieldsToShake.push('contract-risk-rate');
                    }
                    break;
                case 3:
                    if (this.needsCaseStep) {
                        // 使用增强的必填字段验证
                        if (!this.validateRequiredField(this.caseInfo.name)) {
                            errors.case_name = '请输入案件名称';
                            fieldsToShake.push('case-name');
                        }
                        if (!this.validateRequiredField(this.caseInfo.cause_of_action)) {
                            errors.cause_of_action = '请输入案由';
                            fieldsToShake.push('case-cause-of-action');
                        }
                    }
                    break;
            }

            this.errors = errors;

            // 触发验证错误动画
            if (fieldsToShake.length > 0) {
                this.triggerValidationAnimation(fieldsToShake);
            }

            // 显示第一个错误的 toast
            const firstError = Object.values(errors)[0];
            if (firstError) {
                this.showError(firstError);
            }
        },

        /**
         * 触发验证错误动画
         */
        triggerValidationAnimation(fieldIds) {
            fieldIds.forEach(fieldId => {
                const element = document.getElementById(fieldId);
                if (element) {
                    // 添加抖动动画类
                    element.classList.add('validation-shake');

                    // 动画结束后移除类
                    setTimeout(() => {
                        element.classList.remove('validation-shake');
                    }, 500);
                }
            });
        },

        /**
         * 清除错误信息
         */
        clearErrors() {
            this.errors = {};
        },

        /**
         * 显示成功消息
         */
        showSuccess(message) {
            this.showToast(message, 'success');
        },

        /**
         * 显示错误消息
         */
        showError(message) {
            this.showToast(message, 'error');
        },

        /**
         * 显示 Toast 通知
         */
        showToast(message, type = 'success') {
            this.toast = {
                show: true,
                message,
                type
            };

            // 成功类型的 Toast 添加额外的视觉反馈
            if (type === 'success') {
                // 触发页面微震动效果（如果支持）
                if (navigator.vibrate) {
                    navigator.vibrate(50);
                }
            }

            // 3秒后自动隐藏
            setTimeout(() => {
                this.toast.show = false;
            }, 3000);

            this.logger.debug(`${type.toUpperCase()}:`, message);
        },

        // ========== 加载状态管理 ==========

        /**
         * 开始加载状态
         * @param {string} message - 加载提示消息
         */
        startLoading(message = '处理中') {
            this.loading = true;
            this.loadingMessage = message;
            // 禁用页面滚动
            document.body.style.overflow = 'hidden';
        },

        /**
         * 结束加载状态
         */
        stopLoading() {
            this.loading = false;
            this.loadingMessage = '';
            // 恢复页面滚动
            document.body.style.overflow = '';
        },

        /**
         * 更新加载消息
         * @param {string} message - 新的加载提示消息
         */
        updateLoadingMessage(message) {
            if (this.loading) {
                this.loadingMessage = message;
            }
        },

        /**
         * 带加载状态执行异步操作
         * @param {Function} asyncFn - 异步函数
         * @param {string} message - 加载提示消息
         * @returns {Promise<any>} - 异步操作结果
         */
        async withLoading(asyncFn, message = '处理中') {
            try {
                this.startLoading(message);
                return await asyncFn();
            } finally {
                this.stopLoading();
            }
        },

        /**
         * 带进度的加载状态执行异步操作
         * @param {Array<{fn: Function, message: string}>} steps - 步骤数组
         * @returns {Promise<any>} - 最后一步的结果
         */
        async withProgressLoading(steps) {
            let result = null;
            try {
                for (let i = 0; i < steps.length; i++) {
                    const step = steps[i];
                    this.startLoading(step.message || `步骤 ${i + 1}/${steps.length}`);
                    result = await step.fn();
                }
                return result;
            } finally {
                this.stopLoading();
            }
        },

        /**
         * 显示操作成功动画
         * @param {string} message - 成功消息
         */
        showSuccessAnimation(message) {
            this.showSuccess(message);
            // 触发成功动画效果
            const container = document.querySelector('.success-animation-container');
            if (container) {
                container.classList.add('action-success');
                setTimeout(() => {
                    container.classList.remove('action-success');
                }, 400);
            }
        },

        // ========== 工具方法 ==========

        /**
         * 重置向导到初始状态
         */
        resetWizard() {
            this.currentStep = 1;
            this.selectedClients = [];
            this.newClient = {};
            this.contract = {};
            this.caseInfo = {};
            this.showNewClientForm = false;
            this.showOpposingPartyForm = false;
            this.opposingSearchQuery = '';
            this.opposingSearchResults = [];
            this.newOpposingParty = {};
            this.createdContract = null;
            this.createdCase = null;
            this.clearErrors();
            this.clearSession();
            this.initializeFormData();
            this.initializeOpposingPartyForm();
        },

        /**
         * 获取步骤标题
         */
        getStepTitle(step) {
            const titles = {
                1: '选择当事人',
                2: '创建合同',
                3: '创建案件',
                4: '完成'
            };
            return titles[step] || '';
        },

        /**
         * 检查步骤是否完成
         */
        isStepCompleted(step) {
            switch (step) {
                case 1:
                    return this.selectedClients.length > 0;
                case 2:
                    return this.contract.id || (this.contract.name && this.contract.case_type);
                case 3:
                    return !this.needsCaseStep || this.caseInfo.id || (this.caseInfo.name && this.caseInfo.cause_of_action);
                case 4:
                    return this.currentStep === 4;
                default:
                    return false;
            }
        },

        /**
         * 获取合同类型标签
         */
        getCaseTypeLabel(caseType) {
            const types = window.onboardingData?.caseTypes || [];
            const found = types.find(t => t.value === caseType);
            return found ? found.label : caseType;
        },

        /**
         * 获取诉讼地位标签
         */
        getLegalStatusLabel(status) {
            const statuses = window.onboardingData?.legalStatuses || [];
            const found = statuses.find(s => s.value === status);
            return found ? found.label : status;
        },

        /**
         * 获取当事人类型标签
         */
        getClientTypeLabel(clientType) {
            const types = window.onboardingData?.clientTypes || [];
            const found = types.find(t => t.value === clientType);
            return found ? found.label : clientType;
        },

        /**
         * 获取收费模式标签
         */
        getFeeModeLabel(feeMode) {
            const modes = window.onboardingData?.feeModes || [];
            const found = modes.find(m => m.value === feeMode);
            return found ? found.label : feeMode;
        },

        /**
         * 格式化货币金额
         */
        formatCurrency(amount) {
            if (!amount && amount !== 0) return '';
            const num = parseFloat(amount);
            if (isNaN(num)) return amount;
            return '¥' + num.toLocaleString('zh-CN', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
        }
    }
}

// 导出函数供全局使用
window.wizardApp = wizardApp;
