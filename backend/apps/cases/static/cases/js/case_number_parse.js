/**
 * 案件案号解析 — 主入口（解析按钮、执行事项、初始化）
 *
 * 提供：
 * 1. parseDocument 解析裁判文书
 * 2. parseExecutionRequest 解析执行事项
 * 3. addParseButtonToRows 按钮创建与绑定
 * 4. 初始化 + MutationObserver
 * 5. window.CaseNumberParse 公共接口
 *
 * 依赖：case_number_parse_utils.js → case_number_parse_upload.js → 本文件
 */
;(function() {
    'use strict';

    var C = window.CaseNumberParse;
    if (!C) {
        console.error('[case_number_parse] case_number_parse_utils.js 未加载');
        return;
    }

    var showToast              = C.showToast;
    var getCSRFToken            = C.getCSRFToken;
    var getCaseNumberInlineGroup = C.getCaseNumberInlineGroup;
    var getCaseNumberRows      = C.getCaseNumberRows;
    var toggleExecutionParameterSections = C.toggleExecutionParameterSections;
    var bindCurrentStageWatcher = C.bindCurrentStageWatcher;
    var addFileUploadListeners = C.addFileUploadListeners;
    var tempFilePaths          = C.tempFilePaths || {};

    // ============================================================
    // 解析裁判文书
    // ============================================================

    /**
     * 解析裁判文书，提取案号、文书名称、执行依据主文
     * @param {string} caseNumberId - 案号 ID（空字符串表示新建行）
     * @param {HTMLButtonElement} button - 解析按钮
     * @param {string} tempFilePath - 临时文件路径
     */
    function parseDocument(caseNumberId, button, tempFilePath) {
        button.disabled = true;
        button.textContent = '解析中...';

        // 优先使用按钮上缓存的临时文件路径
        if (!tempFilePath && button.dataset.tempFilePath) {
            tempFilePath = button.dataset.tempFilePath;
        }

        var url;
        var body = {};

        if (caseNumberId) {
            url = '/admin/cases/case/casenumber/' + caseNumberId + '/parse-document/';
        } else {
            url = '/admin/cases/case/casenumber/parse-document/';
        }

        if (tempFilePath) {
            body = { temp_file_path: tempFilePath };
        }

        var xhr = new XMLHttpRequest();
        xhr.open('POST', url, true);
        xhr.setRequestHeader('X-CSRFToken', getCSRFToken());
        xhr.setRequestHeader('Content-Type', 'application/json');

        xhr.onload = function() {
            if (xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    if (data.success) {
                        var inline = getCaseNumberInlineGroup();
                        var rows = getCaseNumberRows(inline);
                        for (var i = 0; i < rows.length; i++) {
                            var r = rows[i];
                            var deleteInput = r.querySelector('input[id$="-id"]');
                            var rowCaseNumberId = deleteInput ? deleteInput.value : '';
                            var rowTempId = r.dataset.tempId;

                            if ((caseNumberId && rowCaseNumberId == caseNumberId) ||
                                (tempFilePath && tempFilePaths[rowTempId] === tempFilePath)) {
                                // 填充案号
                                var numberInput = r.querySelector('input[name$="-number"]');
                                if (numberInput && data.number) {
                                    numberInput.value = data.number;
                                }
                                // 填充文书名称
                                var documentNameInput = r.querySelector('input[name$="-document_name"]');
                                if (documentNameInput && data.document_name) {
                                    documentNameInput.value = data.document_name;
                                }
                                // 填充执行依据主文
                                var contentTextarea = r.querySelector('textarea[name$="-document_content"]');
                                if (contentTextarea && data.content) {
                                    contentTextarea.value = data.content;
                                }
                            }
                        }
                        showToast('解析成功！案号、文书名称、执行依据主文已填充。', 'success');
                    } else {
                        showToast('解析失败: ' + data.error, 'error');
                    }
                } catch (e) {
                    showToast('解析失败: ' + e, 'error');
                }
            } else {
                showToast('解析失败: HTTP ' + xhr.status, 'error');
            }
            button.disabled = false;
            button.textContent = '解析裁判文书';
        };

        xhr.onerror = function() {
            showToast('解析失败: 网络错误', 'error');
            button.disabled = false;
            button.textContent = '解析裁判文书';
        };

        xhr.send(JSON.stringify(body));
    }

    // ============================================================
    // 解析执行事项
    // ============================================================

    /**
     * 读取执行事项设置
     * @param {Element} row - 当前行元素
     * @returns {Object}
     */
    function readExecutionSettings(row) {
        var cutoffInput = row.querySelector('input[name$="-execution_cutoff_date"]');
        var paidInput = row.querySelector('input[name$="-execution_paid_amount"]');
        var deductionInput = row.querySelector('input[name$="-execution_use_deduction_order"][type="checkbox"]');
        var yearDaysSelect = row.querySelector('select[name$="-execution_year_days"]');
        var dateInclusionSelect = row.querySelector('select[name$="-execution_date_inclusion"]');
        var llmFallbackToggle = row.querySelector('.parse-execution-llm-toggle');

        return {
            cutoff_date: cutoffInput ? cutoffInput.value.trim() : '',
            paid_amount: paidInput ? paidInput.value.trim() : '',
            use_deduction_order: deductionInput ? deductionInput.checked : false,
            year_days: yearDaysSelect ? yearDaysSelect.value : '',
            date_inclusion: dateInclusionSelect ? dateInclusionSelect.value : '',
            enable_llm_fallback: llmFallbackToggle ? llmFallbackToggle.checked : true
        };
    }

    /**
     * 判断行是否已有执行数据
     * @param {Element} row - 当前行元素
     * @returns {boolean}
     */
    function hasExistingExecutionData(row) {
        var settings = readExecutionSettings(row);
        var manualTextArea = row.querySelector('textarea[name$="-execution_manual_text"]');
        var manualText = manualTextArea ? manualTextArea.value.trim() : '';
        var paid = settings.paid_amount ? parseFloat(settings.paid_amount) : 0;
        return Boolean(
            manualText ||
            settings.cutoff_date ||
            settings.use_deduction_order ||
            (!isNaN(paid) && paid > 0)
        );
    }

    /**
     * 应用执行事项预览数据到表单
     * @param {Element} row - 当前行元素
     * @param {Object} data - 解析结果
     * @param {boolean} overwrite - 是否覆盖已有数据
     */
    function applyExecutionPreview(row, data, overwrite) {
        var settings = data.structured_params || {};
        var manualTextArea = row.querySelector('textarea[name$="-execution_manual_text"]');
        var cutoffInput = row.querySelector('input[name$="-execution_cutoff_date"]');
        var deductionInput = row.querySelector('input[name$="-execution_use_deduction_order"][type="checkbox"]');

        if (manualTextArea && (overwrite || !manualTextArea.value.trim())) {
            manualTextArea.value = data.preview_text || '';
        }
        if (cutoffInput && settings.cutoff_date && (overwrite || !cutoffInput.value.trim())) {
            cutoffInput.value = settings.cutoff_date;
        }
        if (deductionInput && settings.deduction_order && (overwrite || !deductionInput.checked)) {
            deductionInput.checked = settings.deduction_order.length > 0;
        }
    }

    /**
     * 解析执行事项请求
     * @param {string} caseNumberId - 案号 ID
     * @param {Element} row - 当前行元素
     * @param {HTMLButtonElement} button - 解析按钮
     * @param {Object} [options] - 选项
     */
    function parseExecutionRequest(caseNumberId, row, button, options) {
        if (!caseNumberId) {
            return;
        }

        options = options || {};
        var silent = Boolean(options.silent);
        var askOverwrite = options.askOverwrite !== false;
        var hasButton = Boolean(button);

        var overwrite = options.overwrite;
        if (typeof overwrite !== 'boolean') {
            overwrite = true;
        }
        if (askOverwrite && hasExistingExecutionData(row)) {
            overwrite = window.confirm('已存在执行事项参数或文本，是否覆盖？\n点击"取消"将保留已有内容，仅填充空值字段。');
        }

        var body = readExecutionSettings(row);
        body.overwrite = overwrite;

        if (hasButton) {
            button.disabled = true;
            button.textContent = '解析中...';
        }

        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/admin/cases/case/casenumber/' + caseNumberId + '/parse-execution-request/', true);
        xhr.setRequestHeader('X-CSRFToken', getCSRFToken());
        xhr.setRequestHeader('Content-Type', 'application/json');

        xhr.onload = function() {
            if (xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    if (data.success) {
                        applyExecutionPreview(row, data, overwrite);
                        if (!silent) {
                            showToast('申请执行事项解析成功，预览已更新。', 'success');
                        }
                        if (Array.isArray(data.warnings) && data.warnings.length > 0) {
                            showToast(data.warnings.join('；'), 'error');
                        }
                    } else {
                        showToast('解析失败: ' + data.error, 'error');
                    }
                } catch (e) {
                    showToast('解析失败: 响应解析错误', 'error');
                }
            } else {
                showToast('解析失败: HTTP ' + xhr.status, 'error');
            }
            if (hasButton) {
                button.disabled = false;
                button.textContent = '解析执行事项';
            }
        };

        xhr.onerror = function() {
            showToast('解析失败: 网络错误', 'error');
            if (hasButton) {
                button.disabled = false;
                button.textContent = '解析执行事项';
            }
        };

        xhr.send(JSON.stringify(body));
    }

    // ============================================================
    // 按钮创建与绑定
    // ============================================================

    /**
     * 为所有案号行添加解析按钮
     * @param {Element} inline - 内联表单组
     */
    function addParseButtonToRows(inline) {
        var rows = getCaseNumberRows(inline);
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            var documentFileCell = row.querySelector('.field-document_file');
            var documentFileFormRow = row.querySelector('.form-row.field-document_file');
            var manualTextCell = row.querySelector('.field-execution_manual_text');
            var deleteInput = row.querySelector('input[id$="-id"]');
            var caseNumberId = deleteInput ? deleteInput.value : '';

            // 操作栏挂在 form-row 级别，与文件上传区左右分栏
            var actionBar = row.querySelector('.case-number-action-bar');
            if (!actionBar && documentFileFormRow) {
                actionBar = document.createElement('div');
                actionBar.className = 'case-number-action-bar';
                documentFileFormRow.appendChild(actionBar);
            }

            // 打开案件文件夹按钮
            var openFolderBtn = row.querySelector('.open-folder-btn');
            if (!openFolderBtn && actionBar) {
                openFolderBtn = document.createElement('button');
                openFolderBtn.type = 'button';
                openFolderBtn.className = 'open-folder-btn';
                    openFolderBtn.title = '在 Finder 中打开案件文件夹';
                    openFolderBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg> 打开文件夹';
                openFolderBtn.onclick = function() {
                    var caseId = (window.location.pathname.match(/\/cases\/case\/(\d+)\//) || [])[1];
                    if (!caseId) { alert('无法获取案件ID'); return; }
                    openFolderBtn.disabled = true;
                    fetch('/admin/cases/case/' + caseId + '/open-folder/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() }
                    })
                    .then(function(resp) { return resp.json(); })
                    .then(function(data) {
                        openFolderBtn.disabled = false;
                        if (!data.success) { alert(data.error || '打开文件夹失败'); }
                    })
                    .catch(function(err) { openFolderBtn.disabled = false; alert('请求失败: ' + (err.message || '未知错误')); });
                };
                if (!window.__hasFolderBinding) {
                    openFolderBtn.disabled = true;
                    openFolderBtn.title = '未绑定文件夹，请先在下方绑定';
                }
                actionBar.insertBefore(openFolderBtn, actionBar.firstChild);
            }

            // 解析裁判文书按钮
            var parseBtn = row.querySelector('.parse-document-btn');
            if (!parseBtn) {
                parseBtn = document.createElement('button');
                parseBtn.type = 'button';
                parseBtn.className = 'parse-document-btn';
                parseBtn.textContent = '解析裁判文书';
                parseBtn.title = '解析裁判文书，提取执行依据主文';
                parseBtn.disabled = !caseNumberId;
            }

            if (parseBtn) {
                if (caseNumberId) {
                    parseBtn.dataset.casenumberId = caseNumberId;
                    parseBtn.dataset.isNewRow = '';
                    parseBtn.onclick = (function(id, btn) {
                        return function() { parseDocument(id, btn, ''); };
                    })(caseNumberId, parseBtn);
                } else {
                    parseBtn.dataset.isNewRow = 'true';
                    parseBtn.onclick = (function(btn, r) {
                        return function() {
                            var tempPath = tempFilePaths[r.dataset.tempId] || '';
                            parseDocument('', btn, tempPath);
                        };
                    })(parseBtn, row);
                }
                if (actionBar && parseBtn.parentNode !== actionBar) {
                    actionBar.appendChild(parseBtn);
                }
            }

            // 解析执行事项按钮 - 在操作栏始终可见
            var parseExecutionBtn = row.querySelector('.parse-execution-btn');
            if (!parseExecutionBtn) {
                parseExecutionBtn = document.createElement('button');
                parseExecutionBtn.type = 'button';
                parseExecutionBtn.className = 'parse-execution-btn';
                parseExecutionBtn.textContent = '解析执行事项';
                parseExecutionBtn.title = '解析申请执行事项';
            }
            if (caseNumberId) {
                parseExecutionBtn.dataset.casenumberId = caseNumberId;
                parseExecutionBtn.onclick = (function(id, r, btn) {
                    return function() {
                        parseExecutionRequest(id, r, btn, { askOverwrite: true });
                    };
                })(caseNumberId, row, parseExecutionBtn);
            } else {
                parseExecutionBtn.disabled = true;
                parseExecutionBtn.title = '请先保存案件后再解析执行事项';
            }
            if (actionBar && parseExecutionBtn.parentNode !== actionBar) {
                actionBar.appendChild(parseExecutionBtn);
            }
            // Ollama 兜底开关 - 跟在解析执行事项按钮后面
            var llmLabel = row.querySelector('.parse-execution-llm-label');
            if (!llmLabel) {
                llmLabel = document.createElement('label');
                llmLabel.className = 'parse-execution-llm-label';
                var llmToggle = document.createElement('input');
                llmToggle.type = 'checkbox';
                llmToggle.className = 'parse-execution-llm-toggle';
                llmToggle.checked = true;
                llmToggle.title = '规则无法确定时，使用本地Qwen(Ollama)充当兜底';
                var llmTrack = document.createElement('span');
                llmTrack.className = 'parse-execution-switch-track';
                var llmText = document.createElement('span');
                llmText.className = 'parse-execution-llm-text';
                llmText.textContent = 'Ollama';
                llmLabel.appendChild(llmToggle);
                llmLabel.appendChild(llmTrack);
                llmLabel.appendChild(llmText);
                if (!caseNumberId) { llmToggle.disabled = true; }
            }
            if (actionBar && llmLabel.parentNode !== actionBar) {
                actionBar.appendChild(llmLabel);
            }

            // 设置 placeholder
            var documentContentCell = row.querySelector('.field-document_content');
            if (documentContentCell) {
                var documentContentArea = documentContentCell.querySelector('textarea');
                if (documentContentArea) {
                    documentContentArea.placeholder = '执行依据主文';
                }
            }

            if (manualTextCell) {
                var manualTextArea = manualTextCell.querySelector('textarea');
                if (manualTextArea) {
                    manualTextArea.placeholder = '申请执行事项（手工最终文本）';
                }
            }
        }
    }

    // ============================================================
    // 初始化
    // ============================================================

    /**
     * 初始化所有解析按钮和监听器
     */
    function addParseButtons() {
        bindCurrentStageWatcher();
        var inline = getCaseNumberInlineGroup();
        if (!inline) {
            setTimeout(addParseButtons, 500);
            return;
        }
        addParseButtonToRows(inline);
        addFileUploadListeners(inline);
        toggleExecutionParameterSections();
    }

    /**
     * 初始化 filing_number 条件显示
     */
    function initFilingNumberToggle() {
        var filedCheckbox = document.getElementById('id_is_filed');
        var filingNumberDiv = document.querySelector('.field-filing_number');
        if (!filedCheckbox || !filingNumberDiv) return;

        function toggleFilingNumber() {
            if (filedCheckbox.checked) {
                filingNumberDiv.classList.remove('is-hidden-by-filing');
            } else {
                filingNumberDiv.classList.add('is-hidden-by-filing');
            }
        }

        toggleFilingNumber();
        filedCheckbox.addEventListener('change', toggleFilingNumber);
    }

    /**
     * 初始化"保存并复制"按钮
     * @param {string} [buttonLabel] - 按钮文字
     */
    function initSaveAndDuplicateButton(buttonLabel) {
        var submitRow = document.querySelector('.submit-row');
        if (!submitRow) return;

        var duplicateBtn = document.createElement('input');
        duplicateBtn.type = 'submit';
        duplicateBtn.value = buttonLabel || '保存并复制';
        duplicateBtn.name = '_save_and_duplicate';
        duplicateBtn.className = '';
        var deleteBox = submitRow.querySelector('.deletelink-box');
        if (deleteBox) {
            submitRow.insertBefore(duplicateBtn, deleteBox);
        } else {
            submitRow.appendChild(duplicateBtn);
        }
    }

    // ============================================================
    // 页面加载入口
    // ============================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            addParseButtons();
            initFilingNumberToggle();
        });
    } else {
        addParseButtons();
        initFilingNumberToggle();
    }

    // 监听内联表单的动态添加
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length > 0) {
                addParseButtons();
            }
        });
    });

    var caseNumberInline = getCaseNumberInlineGroup();
    if (caseNumberInline) {
        observer.observe(caseNumberInline, { childList: true, subtree: true });
    }

    // ============================================================
    // 暴露公共接口（供模板中调用需要 Django 模板变量的初始化）
    // ============================================================

    C.initSaveAndDuplicateButton = initSaveAndDuplicateButton;
    C.parseDocument              = parseDocument;
    C.parseExecutionRequest      = parseExecutionRequest;

})();
