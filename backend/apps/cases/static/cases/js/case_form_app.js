/**
 * 案件表单 Alpine.js 组件
 *
 * 功能：
 * 1. 合同当事人动态过滤
 * 2. 自动填充案件当事人
 * 3. 案件类型字段显示控制
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3
 *
 * @deprecated 替代原有的 admin_case_form.js
 */
function caseFormApp() {
    return {
        // ========== 状态 ==========
        contractId: null,           // 当前选中的合同 ID
        contractParties: [],        // 合同当事人列表
        allClientOptions: [],       // 所有客户选项（用于恢复）
        contractPartiesCache: {},   // 合同当事人缓存
        isLoading: false,           // 加载状态
        isAutoFilling: false,       // 自动填充进行中
        caseType: '',               // 案件类型
        previousContractId: null,   // 上一次选中的合同 ID

        // ========== 初始化 ==========
        /**
         * 组件初始化方法
         * Requirements: 8.3
         */
        init() {
            console.log('[caseFormApp] 初始化...');

            // 保存所有客户选项
            this.saveAllClientOptions();

            // 初始化合同监听
            this.initContractWatcher();

            // 初始化案件类型监听
            this.initCaseTypeWatcher();

            // 监听 inline 行添加事件
            this.initInlineAddedListener();

            console.log('[caseFormApp] 初始化完成');
        },

        // ========== 工具方法 ==========
        /**
         * 通过 ID 获取元素
         */
        byId(id) {
            return document.getElementById(id);
        },

        /**
         * 获取字段 div 元素
         */
        fieldDivs(name) {
            return document.querySelectorAll('div.field-' + name);
        },

        /**
         * 获取所有 CaseParty inline 的 client 选择框
         * 排除模板行（__prefix__）
         */
        getClientSelects() {
            // 优先使用带有特定 CSS 类的选择框
            let selects = document.querySelectorAll(
                'select.contract-party-client-select, ' +
                'select[data-contract-party-filter="true"]'
            );

            // 如果没有找到，使用兼容选择器
            if (selects.length === 0) {
                selects = document.querySelectorAll(
                    'select[name$="-client"], ' +
                    '#caseparty_set-group select[id$="-client"]'
                );
            }

            // 过滤掉模板行
            return Array.from(selects).filter(select =>
                select.name && !select.name.includes('__prefix__')
            );
        },

        // ========== 合同当事人过滤方法 ==========
        /**
         * 保存所有客户选项（首次加载时）
         * Requirements: 1.1
         */
        saveAllClientOptions() {
            if (this.allClientOptions.length > 0) return;

            const selects = this.getClientSelects();
            if (selects.length === 0) return;

            const firstSelect = selects[0];
            this.allClientOptions = Array.from(firstSelect.options).map(opt => ({
                value: opt.value,
                text: opt.text
            }));

            console.log('[caseFormApp] 保存客户选项，数量:', this.allClientOptions.length);
        },

        /**
         * 获取合同当事人
         * Requirements: 1.1, 1.2
         * @param {string} contractId - 合同 ID
         * @returns {Promise<Array>} 当事人列表
         */
        async fetchContractParties(contractId) {
            console.log('[caseFormApp] 获取合同当事人, contractId:', contractId);

            // 检查缓存
            if (this.contractPartiesCache[contractId]) {
                console.log('[caseFormApp] 使用缓存数据');
                return this.contractPartiesCache[contractId];
            }

            this.isLoading = true;
            this.setLoadingState(true);

            try {
                const url = `/api/v1/contracts/contracts/${contractId}/all-parties`;
                const response = await fetch(url);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const parties = await response.json();
                console.log('[caseFormApp] API 返回当事人数量:', parties.length);

                // 缓存结果
                this.contractPartiesCache[contractId] = parties;
                this.contractParties = parties;

                return parties;
            } catch (error) {
                console.error('[caseFormApp] 获取合同当事人失败:', error);
                this.restoreAllClientOptions();
                return [];
            } finally {
                this.isLoading = false;
                this.setLoadingState(false);
            }
        },

        /**
         * 更新选择框选项
         * Requirements: 1.1
         * @param {Array} parties - 当事人列表
         */
        updateClientOptions(parties) {
            console.log('[caseFormApp] 更新选项，当事人数量:', parties.length);

            // 构建当事人 ID 到信息的映射
            const partyMap = {};
            parties.forEach(party => {
                partyMap[String(party.id)] = party;
            });

            const selects = this.getClientSelects();

            selects.forEach(select => {
                const currentValue = select.value;

                // 清空现有选项（保留空选项）
                while (select.options.length > 1) {
                    select.remove(1);
                }

                // 添加新选项
                parties.forEach(party => {
                    const opt = document.createElement('option');
                    opt.value = String(party.id);
                    const sourceLabel = party.source === 'contract' ? '[合同]' : '[补充协议]';
                    opt.text = `${party.name} ${sourceLabel}`;
                    select.appendChild(opt);
                });

                // 恢复之前选中的值
                if (currentValue) {
                    if (partyMap[currentValue]) {
                        select.value = currentValue;
                    } else {
                        // 值不在列表中，添加临时选项
                        const opt = document.createElement('option');
                        opt.value = currentValue;
                        opt.text = `当事人 #${currentValue}`;
                        select.appendChild(opt);
                        select.value = currentValue;
                    }
                }
            });
        },

        /**
         * 恢复所有客户选项
         * Requirements: 1.3
         */
        restoreAllClientOptions() {
            if (this.allClientOptions.length === 0) return;

            const selects = this.getClientSelects();

            selects.forEach(select => {
                const currentValue = select.value;
                select.innerHTML = '';

                this.allClientOptions.forEach(opt => {
                    const option = document.createElement('option');
                    option.value = opt.value;
                    option.text = opt.text;
                    select.appendChild(option);
                });

                if (currentValue) {
                    select.value = currentValue;
                }
            });
        },

        /**
         * 设置加载状态
         * @param {boolean} loading - 是否加载中
         */
        setLoadingState(loading) {
            const selects = this.getClientSelects();
            const inlineGroup = document.querySelector('.contract-party-inline, #caseparty_set-group');

            if (inlineGroup) {
                inlineGroup.classList.toggle('contract-party-loading-state', loading);
            }

            selects.forEach(select => {
                select.disabled = loading;

                const wrapper = select.closest('td') || select.parentElement;
                let loadingIndicator = wrapper.querySelector('.contract-party-loading');

                if (loading) {
                    if (!loadingIndicator) {
                        loadingIndicator = document.createElement('span');
                        loadingIndicator.className = 'contract-party-loading';
                        loadingIndicator.style.cssText = 'margin-left: 8px; color: #666; font-size: 12px;';
                        loadingIndicator.textContent = '加载中...';
                        wrapper.appendChild(loadingIndicator);
                    }
                } else {
                    if (loadingIndicator) {
                        loadingIndicator.remove();
                    }
                }
            });
        },

        // ========== 自动填充方法 ==========
        /**
         * 自动填充合同当事人到案件当事人 inline
         * Requirements: 1.2, 1.3, 1.5
         * @param {Array} parties - 当事人列表
         */
        autoFillCaseParties(parties) {
            console.log('[caseFormApp] 开始自动填充，当事人数量:', parties?.length || 0);

            if (!parties || parties.length === 0) {
                console.log('[caseFormApp] 没有当事人，退出');
                return;
            }

            this.isAutoFilling = true;

            // 基于 client ID 去重
            const seenIds = {};
            const uniqueParties = parties.filter(party => {
                const idStr = String(party.id);
                if (seenIds[idStr]) return false;
                seenIds[idStr] = true;
                return true;
            });

            console.log('[caseFormApp] 去重后当事人数量:', uniqueParties.length);

            // 获取已存在的当事人 ID
            const existingClientIds = {};
            this.getClientSelects().forEach(select => {
                if (select.value) {
                    existingClientIds[String(select.value)] = true;
                }
            });

            // 过滤出需要添加的当事人
            const partiesToAdd = uniqueParties.filter(party =>
                !existingClientIds[String(party.id)]
            );

            console.log('[caseFormApp] 需要添加的当事人数量:', partiesToAdd.length);

            if (partiesToAdd.length === 0) {
                this.isAutoFilling = false;
                return;
            }

            // 查找添加按钮
            const addButton = this.findAddButton();
            if (!addButton) {
                console.error('[caseFormApp] 找不到添加按钮');
                this.isAutoFilling = false;
                return;
            }

            // 记录已填充的选择框
            const filledSelectNames = {};
            let currentIndex = 0;

            const fillSelect = (select, party) => {
                const partyIdStr = String(party.id);

                // 检查选项是否存在
                let optionExists = Array.from(select.options).some(opt => opt.value === partyIdStr);

                // 如果选项不存在，添加它
                if (!optionExists) {
                    const opt = document.createElement('option');
                    opt.value = partyIdStr;
                    const sourceLabel = party.source === 'contract' ? '[合同]' : '[补充协议]';
                    opt.text = `${party.name} ${sourceLabel}`;
                    select.appendChild(opt);
                }

                select.value = partyIdStr;
                filledSelectNames[select.name] = true;
                console.log('[caseFormApp] 已填充:', party.name);
                return true;
            };

            const findEmptySelect = () => {
                return this.getClientSelects().find(select =>
                    !filledSelectNames[select.name] && (!select.value || select.value === '')
                );
            };

            const processNextParty = () => {
                if (currentIndex >= partiesToAdd.length) {
                    console.log('[caseFormApp] 全部当事人添加完成');
                    this.isAutoFilling = false;
                    return;
                }

                const party = partiesToAdd[currentIndex];
                const emptySelect = findEmptySelect();

                if (emptySelect) {
                    fillSelect(emptySelect, party);
                    currentIndex++;
                    setTimeout(processNextParty, 100);
                } else {
                    const selectCountBefore = this.getClientSelects().length;
                    addButton.click();

                    setTimeout(() => {
                        const selectCountAfter = this.getClientSelects().length;

                        if (selectCountAfter > selectCountBefore) {
                            const newEmptySelect = findEmptySelect();
                            if (newEmptySelect) {
                                fillSelect(newEmptySelect, party);
                            }
                        }
                        currentIndex++;
                        setTimeout(processNextParty, 100);
                    }, 300);
                }
            };

            processNextParty();
        },

        /**
         * 查找添加按钮
         */
        findAddButton() {
            let addButton = document.querySelector(
                '.contract-party-inline .add-row a, ' +
                '.contract-party-inline a.add-row, ' +
                '#caseparty_set-group .add-row a, ' +
                '#caseparty_set-group a.add-row, ' +
                '[data-inline-type="tabular"] .add-row a'
            );

            if (!addButton) {
                const firstSelect = this.getClientSelects()[0];
                if (firstSelect) {
                    const inlineContainer = firstSelect.closest('.inline-group, .djn-group, fieldset');
                    if (inlineContainer) {
                        addButton = inlineContainer.querySelector('.add-row a, a.add-row');
                    }
                }
            }

            return addButton;
        },

        /**
         * 清空所有案件当事人
         * Requirements: 1.3
         */
        clearAllCaseParties() {
            console.log('[caseFormApp] 开始清空当事人...');

            const allSelects = document.querySelectorAll('select[name^="parties-"][name$="-client"]');
            const realSelects = Array.from(allSelects).filter(select =>
                !select.name.includes('__prefix__')
            );

            const rowsToDelete = [];
            realSelects.forEach(select => {
                if (select.value) {
                    const row = select.closest('tr, .dynamic-caseparty_set, .djn-item');
                    if (row) {
                        rowsToDelete.push({ row, selectName: select.name });
                    }
                }
            });

            // 从后往前删除
            for (let i = rowsToDelete.length - 1; i >= 0; i--) {
                const { row, selectName } = rowsToDelete[i];

                const deleteBtn = row.querySelector('.inline-deletelink, .delete-handler, a.delete, .djn-remove-handler');
                if (deleteBtn) {
                    deleteBtn.click();
                } else {
                    const deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
                    if (deleteCheckbox) {
                        deleteCheckbox.checked = true;
                        deleteCheckbox.dispatchEvent(new Event('change', { bubbles: true }));
                    } else {
                        const select = row.querySelector('select[name$="-client"]');
                        if (select) {
                            select.value = '';
                        }
                    }
                }
            }

            console.log('[caseFormApp] 清空完成');
        },

        // ========== 案件类型字段显示控制 ==========
        /**
         * 切换字段显示/隐藏
         * Requirements: 1.4
         */
        toggleFieldVisibility() {
            const sel = this.byId('id_case_type');
            if (!sel) return;

            const v = (sel.value || '').toLowerCase().trim();
            const allowed = new Set(['civil', 'criminal', 'administrative', 'labor', 'intl']);
            const show = allowed.has(v);

            // 显示相关字段
            this.fieldDivs('current_stage').forEach(div => { div.style.display = ''; });
            this.fieldDivs('cause_of_action').forEach(div => { div.style.display = ''; });

            // 设置默认值
            document.querySelectorAll('input[name$="cause_of_action"]').forEach(inp => {
                if (!inp.value || inp.value.trim() === '') {
                    inp.value = '合同纠纷';
                }
            });

            // 如果不显示，清空 current_stage
            if (!show) {
                document.querySelectorAll('select[name$="current_stage"]').forEach(cur => {
                    cur.value = '';
                });
            }
        },

        // ========== 监听器初始化 ==========
        /**
         * 初始化合同字段监听
         * Requirements: 1.1, 1.2, 1.3
         */
        initContractWatcher() {
            const contractSelect = this.byId('id_contract');
            if (!contractSelect) return;

            // 记录初始值
            this.previousContractId = contractSelect.value || '';
            this.contractId = contractSelect.value || null;

            // 监听变化
            contractSelect.addEventListener('change', () => this.handleContractChange());

            // 初始化时如果已有合同，只更新选项
            if (contractSelect.value) {
                this.fetchContractPartiesAndFill(contractSelect.value, false);

                const inlineGroup = document.querySelector('.contract-party-inline, #caseparty_set-group');
                if (inlineGroup) {
                    inlineGroup.classList.add('contract-party-filter-active');
                }

                // 注意：文件夹路径由 folder_binding_app.js 处理，这里不再重复请求
                // this.updateContractFolderPath(contractSelect.value);
            }
        },

        /**
         * 初始化案件类型监听
         * Requirements: 1.4
         */
        initCaseTypeWatcher() {
            const sel = this.byId('id_case_type');
            if (!sel) return;

            sel.addEventListener('change', () => this.toggleFieldVisibility());
            this.toggleFieldVisibility();
        },

        /**
         * 初始化 inline 行添加监听
         * Requirements: 1.5
         */
        initInlineAddedListener() {
            document.body.addEventListener('formset:added', (e) => {
                if (e.detail && e.detail[0]) {
                    const row = e.detail[0];
                    if (row.classList && row.classList.contains('dynamic-caseparty_set')) {
                        setTimeout(() => this.handleInlineAdded(), 100);
                    }
                }
            });
        },

        /**
         * 处理合同字段变化
         * Requirements: 1.1, 1.2, 1.3
         */
        async handleContractChange() {
            const contractSelect = this.byId('id_contract');
            if (!contractSelect) return;

            const contractId = contractSelect.value;

            // 如果值没有变化，跳过
            if (contractId === this.previousContractId) {
                return;
            }

            console.log('[caseFormApp] 合同变化:', this.previousContractId, '->', contractId);

            // 复制合同名称到案件名称
            this.copyContractNameToCaseName(contractSelect);

            // 注意：文件夹路径由 folder_binding_app.js 处理，这里不再重复请求
            // this.updateContractFolderPath(contractId);

            // 更新过滤状态
            const inlineGroup = document.querySelector('.contract-party-inline, #caseparty_set-group');
            if (inlineGroup) {
                inlineGroup.classList.toggle('contract-party-filter-active', !!contractId);
            }

            // 如果切换了合同，先清空当事人
            const isContractChanged = this.previousContractId && contractId && contractId !== this.previousContractId;
            if (isContractChanged) {
                this.clearAllCaseParties();
            }

            this.previousContractId = contractId;
            this.contractId = contractId;

            if (contractId) {
                if (isContractChanged) {
                    setTimeout(() => {
                        this.fetchContractPartiesAndFill(contractId, true);
                    }, 500);
                } else {
                    const shouldAutoFill = !this.previousContractId;
                    this.fetchContractPartiesAndFill(contractId, shouldAutoFill);
                }
            } else {
                this.restoreAllClientOptions();
            }
        },

        /**
         * 获取合同当事人并可选自动填充
         * @param {string} contractId - 合同 ID
         * @param {boolean} shouldAutoFill - 是否自动填充
         */
        async fetchContractPartiesAndFill(contractId, shouldAutoFill) {
            const parties = await this.fetchContractParties(contractId);

            if (shouldAutoFill && parties.length > 0) {
                this.autoFillCaseParties(parties);
                setTimeout(() => {
                    this.updateClientOptions(parties);
                }, 5000);
            } else {
                this.updateClientOptions(parties);
            }
        },

        /**
         * 复制合同名称到案件名称
         */
        copyContractNameToCaseName(contractSelect) {
            const caseNameInput = this.byId('id_name');
            if (!caseNameInput) return;

            const selectedOption = contractSelect.options[contractSelect.selectedIndex];
            if (!selectedOption || !selectedOption.value) return;

            const contractName = selectedOption.text;

            if (!caseNameInput.value || caseNameInput.value.trim() === '') {
                caseNameInput.value = contractName;
            }
        },

        /**
         * 更新合同文件夹路径显示
         */
        async updateContractFolderPath(contractId) {
            const folderPathField = document.querySelector('.field-contract_folder_path_display');
            if (!folderPathField) return;

            const displayElement = folderPathField.querySelector('.readonly') ||
                                   folderPathField.querySelector('div:not(.help)') ||
                                   folderPathField.querySelector('p');

            if (!displayElement) return;

            if (!contractId) {
                displayElement.textContent = '未关联合同';
                return;
            }

            displayElement.textContent = '加载中...';

            try {
                const url = `/api/v1/contracts/${contractId}/folder-binding/`;
                const response = await fetch(url);

                if (response.status === 404) {
                    displayElement.textContent = '未绑定文件夹';
                    return;
                }

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                displayElement.textContent = data?.folder_path || '未绑定文件夹';
            } catch (error) {
                console.error('[caseFormApp] 获取文件夹路径失败:', error);
                displayElement.textContent = '获取失败';
            }
        },

        /**
         * 处理新增 inline 行
         * Requirements: 1.5
         */
        handleInlineAdded() {
            if (this.isAutoFilling) {
                return;
            }

            const contractSelect = this.byId('id_contract');
            if (!contractSelect || !contractSelect.value) return;

            const contractId = contractSelect.value;
            if (this.contractPartiesCache[contractId]) {
                this.updateClientOptions(this.contractPartiesCache[contractId]);
            }
        }
    };
}
