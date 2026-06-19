/**
 * 案件案号解析 — 文件上传与拖拽
 *
 * 提供：
 * 1. handleFileUpload 临时文件上传
 * 2. addDropzoneToRow / updateDropzoneFileName 拖拽上传 UI
 * 3. addFileUploadListeners 批量绑定上传监听
 *
 * 依赖：case_number_parse_utils.js（必须先加载）
 */
;(function() {
    'use strict';

    var C = window.CaseNumberParse;
    if (!C) {
        console.error('[case_number_parse] case_number_parse_utils.js 未加载');
        return;
    }

    var showToast        = C.showToast;
    var getCSRFToken      = C.getCSRFToken;
    var getCaseNumberRows = C.getCaseNumberRows;

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
            if (e.target.closest('a')) return;
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
    // 暴露到共享命名空间
    // ============================================================

    C.tempFilePaths           = tempFilePaths;
    C.handleFileUpload        = handleFileUpload;
    C.addDropzoneToRow        = addDropzoneToRow;
    C.updateDropzoneFileName  = updateDropzoneFileName;
    C.addFileUploadListeners  = addFileUploadListeners;

})();
