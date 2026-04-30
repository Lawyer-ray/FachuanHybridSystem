/**
 * 案件案号解析脚本 - 裁判文书解析 & 执行事项解析
 *
 * 功能：
 * 1. 解析裁判文书：提取案号、文书名称、执行依据主文
 * 2. 解析执行事项：从执行依据主文提取执行参数
 * 3. 临时文件上传（新建行尚未保存时）
 * 4. 打开案件文件夹
 * 5. filing_number 条件显示（is_filed 联动）
 * 6. 保存并复制按钮
 */
;(function() {
    'use strict';

    // ============================================================
    // 工具函数
    // ============================================================

    /**
     * 显示 Toast 通知
     * @param {string} message - 消息内容
     * @param {string} [type='success'] - 消息类型: success / error
     */
    function showToast(message, type) {
        type = type || 'success';
        var container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        var toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.textContent = message;
        container.appendChild(toast);
        toast.offsetHeight; // 触发重绘
        toast.classList.add('show');
        setTimeout(function() {
            toast.classList.remove('show');
            setTimeout(function() {
                container.removeChild(toast);
            }, 300);
        }, 3000);
    }

    /**
     * 从 cookie 获取 CSRF Token
     * @returns {string|null}
     */
    function getCSRFToken() {
        var name = 'csrftoken';
        var cookieValue = null;
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
        return cookieValue;
    }

    // ============================================================
    // DOM 查询辅助
    // ============================================================

    /**
     * 获取案号内联表单组
     * @returns {Element|null}
     */
    function getCaseNumberInlineGroup() {
        return (
            document.querySelector('#case_numbers-group') ||
            document.querySelector(".inline-group[id$='case_numbers-group']")
        );
    }

    /**
     * 获取所有案号行（兼容 tabular 和 stacked）
     * @param {Element} inline - 内联表单组
     * @returns {Element[]}
     */
    function getCaseNumberRows(inline) {
        if (!inline) return [];
        var result = [];
        var tabularRows = inline.querySelectorAll('tbody tr');
        if (tabularRows.length > 0) {
            for (var i = 0; i < tabularRows.length; i++) {
                var tr = tabularRows[i];
                if (tr.classList.contains('empty-form')) continue;
                result.push(tr);
            }
            return result;
        }

        var stackedRows = inline.querySelectorAll('.inline-related');
        for (var j = 0; j < stackedRows.length; j++) {
            var block = stackedRows[j];
            if (block.classList.contains('empty-form') || block.classList.contains('djn-empty-form')) continue;
            if (!block.querySelector('.field-number') && !block.querySelector('.field-document_file')) continue;
            result.push(block);
        }
        return result;
    }

    // ============================================================
    // 执行阶段联动
    // ============================================================

    /**
     * 判断当前阶段是否为"执行"
     * @returns {boolean}
     */
    function isExecutionStageSelected() {
        var stageSelect = document.getElementById('id_current_stage');
        if (!stageSelect) return false;
        return (stageSelect.value || '').trim() === 'enforcement';
    }

    /**
     * 根据当前阶段显示/隐藏执行参数区域
     */
    function toggleExecutionParameterSections() {
        var inline = getCaseNumberInlineGroup();
        if (!inline) return;

        var show = isExecutionStageSelected();
        var fieldsets = inline.querySelectorAll('.case-number-execution-fieldset');
        for (var i = 0; i < fieldsets.length; i++) {
            fieldsets[i].classList.toggle('is-hidden-by-stage', !show);
        }

        var rows = getCaseNumberRows(inline);
        for (var j = 0; j < rows.length; j++) {
            var row = rows[j];
            var parseExecutionBtn = row.querySelector('.parse-execution-btn');
            var llmToggle = row.querySelector('.parse-execution-llm-toggle');
            if (!parseExecutionBtn) continue;

            var deleteInput = row.querySelector('input[id$="-id"]');
            var caseNumberId = deleteInput ? deleteInput.value : '';

            if (!show) {
                parseExecutionBtn.disabled = true;
                if (llmToggle) {
                    llmToggle.disabled = true;
                }
                parseExecutionBtn.dataset.stageHidden = 'true';
                continue;
            }

            if (parseExecutionBtn.dataset.stageHidden === 'true') {
                parseExecutionBtn.disabled = !caseNumberId;
                if (llmToggle) {
                    llmToggle.disabled = !caseNumberId;
                }
                delete parseExecutionBtn.dataset.stageHidden;
            }
        }
    }

    /**
     * 绑定 current_stage 下拉框的 change 事件
     */
    function bindCurrentStageWatcher() {
        var stageSelect = document.getElementById('id_current_stage');
        if (!stageSelect || stageSelect.dataset.executionWatcherBound === 'true') {
            return;
        }
        stageSelect.dataset.executionWatcherBound = 'true';
        stageSelect.addEventListener('change', function() {
            toggleExecutionParameterSections();
        });
    }

    // ============================================================
    // 临时文件上传
    // ============================================================

    /** 存储每行的临时文件路径 */
    var tempFilePaths = {};

    /**
     * 处理文件上传
     * @param {HTMLInputElement} fileInput - 文件输入框
     * @param {Element} row - 当前行元素
     */
    function handleFileUpload(fileInput, row) {
        var file = fileInput.files[0];
        if (!file) return;

        var tempId = row.dataset.tempId;
        var parseBtn = row.querySelector('.parse-document-btn');

        // 验证文件类型
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('仅支持PDF格式文件');
            fileInput.value = '';
            return;
        }

        // 禁用解析按钮
        if (parseBtn) {
            parseBtn.disabled = true;
            parseBtn.textContent = '上传中...';
        }

        // 上传文件到临时目录
        var formData = new FormData();
        formData.append('file', file);

        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/v1/cases/upload-temp-document', true);
        xhr.setRequestHeader('X-CSRFToken', getCSRFToken());
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

        xhr.onload = function() {
            if (parseBtn) {
                parseBtn.disabled = false;
                parseBtn.textContent = '解析裁判文书';
            }

            if (xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    if (data.success) {
                        tempFilePaths[tempId] = data.temp_file_path;
                        if (parseBtn) {
                            parseBtn.disabled = false;
                            parseBtn.textContent = '解析裁判文书';
                            parseBtn.dataset.tempFilePath = data.temp_file_path;
                        }
                    } else {
                        showToast('上传失败: ' + data.error, 'error');
                    }
                } catch (e) {
                    showToast('上传失败: 响应解析错误', 'error');
                }
            } else {
                showToast('上传失败: HTTP ' + xhr.status, 'error');
            }
        };

        xhr.onerror = function() {
            if (parseBtn) {
                parseBtn.disabled = false;
                parseBtn.textContent = '解析裁判文书';
            }
            showToast('上传失败: 网络错误', 'error');
        };

        xhr.send(formData);
    }

    // ============================================================
    // 拖拽上传
    // ============================================================

    /**
     * 为案号行的 document_file 字段添加拖拽上传区域
     * @param {Element} row - 案号行元素
     */
    function addDropzoneToRow(row) {
        var documentFileCell = row.querySelector('.field-document_file');
        if (!documentFileCell) return;

        // 已添加过则跳过
        if (documentFileCell.querySelector('.cn-dropzone')) return;

        var fileInput = documentFileCell.querySelector('input[type="file"]');
        if (!fileInput) return;

        // 移除旧的上传 UI（flex-container 包含原生 file input、currently 链接、clear 复选框）
        // 先提取已上传文件信息，再将 file input 移出保留在 DOM 中供表单提交
        var flexContainer = fileInput.closest('.flex-container');
        var currentFileHtml = '';
        if (flexContainer) {
            var currentlyEl = flexContainer.querySelector('.currently');
            if (currentlyEl) {
                currentFileHtml = currentlyEl.innerHTML;
            }
            fileInput.style.display = 'none';
            // file input 的祖先中，documentFileCell 的直接子元素（可能是中间 wrapper）
            var wrapper = flexContainer;
            while (wrapper.parentElement && wrapper.parentElement !== documentFileCell) {
                wrapper = wrapper.parentElement;
            }
            documentFileCell.appendChild(fileInput);
            wrapper.remove();
        } else {
            fileInput.style.display = 'none';
        }

        // 创建拖拽上传区域
        var dropzone = document.createElement('div');
        dropzone.className = 'cn-dropzone';
        dropzone.innerHTML =
            '<div class="cn-dropzone-inner">' +
                '<svg class="cn-dropzone-icon" width="24" height="24" viewBox="0 0 24 24" fill="none">' +
                    '<path d="M12 4v16m-8-8h16" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
                '</svg>' +
                '<span class="cn-dropzone-text">点击或拖拽上传PDF</span>' +
            '</div>';

        // 显示当前已上传文件信息
        if (currentFileHtml) {
            var fileHint = document.createElement('div');
            fileHint.className = 'cn-dropzone-current';
            fileHint.innerHTML = currentFileHtml;
            dropzone.appendChild(fileHint);
            // 更新主文字为已上传状态
            var textEl = dropzone.querySelector('.cn-dropzone-text');
            var linkEl = fileHint.querySelector('a');
            if (textEl && linkEl) {
                textEl.textContent = linkEl.textContent;
                textEl.classList.add('cn-dropzone-text-uploaded');
            }
        }

        // 将拖拽区域追加到 documentFileCell 末尾
        documentFileCell.appendChild(dropzone);

        // 点击触发文件选择
        dropzone.addEventListener('click', function(e) {
            if (e.target.closest('a')) return; // 已上传文件链接不触发
            fileInput.click();
        });

        // 拖拽事件
        dropzone.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('cn-dropzone-active');
        });

        dropzone.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('cn-dropzone-active');
        });

        dropzone.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('cn-dropzone-active');

            var files = e.dataTransfer.files;
            if (files.length === 0) return;

            var file = files[0];
            if (!file.name.toLowerCase().endsWith('.pdf')) {
                showToast('仅支持PDF格式文件', 'error');
                return;
            }

            // 通过 DataTransfer 将拖拽文件赋给 file input
            var dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            fileInput.files = dataTransfer.files;

            // 触发已有的上传逻辑
            handleFileUpload(fileInput, row);

            // 更新拖拽区域显示文件名
            updateDropzoneFileName(dropzone, file.name);
        });
    }

    /**
     * 更新拖拽区域显示的文件名
     * @param {Element} dropzone - 拖拽区域元素
     * @param {string} fileName - 文件名
     */
    function updateDropzoneFileName(dropzone, fileName) {
        var textEl = dropzone.querySelector('.cn-dropzone-text');
        if (textEl) {
            textEl.textContent = fileName;
            textEl.classList.add('cn-dropzone-text-uploaded');
        }
    }

    /**
     * 为文件输入框绑定上传监听，并添加拖拽区域
     * @param {Element} inline - 内联表单组
     */
    function addFileUploadListeners(inline) {
        var rows = getCaseNumberRows(inline);
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            if (!row.dataset.tempId) {
                row.dataset.tempId = 'row_' + Math.random().toString(36).substr(2, 9);
            }

            var documentFileCell = row.querySelector('.field-document_file');
            if (!documentFileCell) continue;

            var fileInput = documentFileCell.querySelector('input[type="file"]');
            if (fileInput && !fileInput.dataset.uploadListener) {
                fileInput.dataset.uploadListener = 'true';
                fileInput.onchange = (function(r, fi) {
                    return function(e) {
                        handleFileUpload(e.target, r);
                        // 更新拖拽区域文件名
                        var dz = r.querySelector('.cn-dropzone');
                        if (dz && fi.files.length > 0) {
                            updateDropzoneFileName(dz, fi.files[0].name);
                        }
                    };
                })(row, fileInput);
            }

            // 添加拖拽上传区域
            addDropzoneToRow(row);
        }
    }

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
            var manualTextCell = row.querySelector('.field-execution_manual_text');
            var deleteInput = row.querySelector('input[id$="-id"]');
            var caseNumberId = deleteInput ? deleteInput.value : '';

            var actionBar = row.querySelector('.case-number-action-bar');
            if (!actionBar && documentFileCell) {
                actionBar = document.createElement('div');
                actionBar.className = 'case-number-action-bar';
                documentFileCell.appendChild(actionBar);
            }

            // 打开案件文件夹按钮
            var openFolderBtn = row.querySelector('.open-folder-btn');
            if (!openFolderBtn && actionBar) {
                openFolderBtn = document.createElement('button');
                openFolderBtn.type = 'button';
                openFolderBtn.className = 'open-folder-btn';
                openFolderBtn.title = '在 Finder 中打开案件文件夹';
                openFolderBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>';
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
                actionBar.insertBefore(openFolderBtn, actionBar.firstChild);
            }

            // 解析裁判文书按钮
            var parseBtn = row.querySelector('.parse-document-btn');
            if (!parseBtn && documentFileCell) {
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
                } else if (!actionBar && documentFileCell && parseBtn.parentNode !== documentFileCell) {
                    documentFileCell.appendChild(parseBtn);
                }
            }

            // 解析执行事项控件
            var parseExecutionControls = row.querySelector('.parse-execution-controls');
            if (manualTextCell && !parseExecutionControls) {
                parseExecutionControls = document.createElement('div');
                parseExecutionControls.className = 'parse-execution-controls';

                var parseExecutionBtn = document.createElement('button');
                parseExecutionBtn.type = 'button';
                parseExecutionBtn.className = 'parse-execution-btn';
                parseExecutionBtn.textContent = '解析执行事项';
                parseExecutionBtn.title = '解析申请执行事项';

                var llmLabel = document.createElement('label');
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
                llmText.textContent = 'Ollama兜底';
                llmLabel.appendChild(llmToggle);
                llmLabel.appendChild(llmTrack);
                llmLabel.appendChild(llmText);
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
                    llmToggle.disabled = true;
                }

                parseExecutionControls.appendChild(parseExecutionBtn);
                parseExecutionControls.appendChild(llmLabel);
            }

            if (parseExecutionControls) {
                if (actionBar && parseExecutionControls.parentNode !== actionBar) {
                    actionBar.appendChild(parseExecutionControls);
                } else if (!actionBar && manualTextCell && parseExecutionControls.parentNode !== manualTextCell) {
                    manualTextCell.appendChild(parseExecutionControls);
                }
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

    // 暴露公共接口（供模板中调用需要 Django 模板变量的初始化）
    window.CaseNumberParse = {
        initSaveAndDuplicateButton: initSaveAndDuplicateButton,
        showToast: showToast
    };

})();
