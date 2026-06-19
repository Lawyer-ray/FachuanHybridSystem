/**
 * ID验证管理器
 *
 * 提供实时ID重复检测功能，包括：
 * - 结构字段变化时自动验证ID唯一性
 * - 表单提交时显示验证状态
 * - 重复ID报告查看
 */
(function() {
    'use strict';

    // ID验证管理器类
    class IDValidationManager {
        constructor() {
            this.debounceTimer = null;
            this.debounceDelay = 500;
            this.validateUrl = '/admin/documents/foldertemplate/validate-structure/';
            this.duplicateReportUrl = '/admin/documents/foldertemplate/duplicate-report/';
            this.init();
        }

        init() {
            // 等待DOM加载完成
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => this.setupValidation());
            } else {
                this.setupValidation();
            }
        }

        setupValidation() {
            const structureField = document.querySelector('#id_structure');
            if (!structureField) return;

            this.createValidationUI(structureField);
            this.bindEvents(structureField);
        }

        createValidationUI(structureField) {
            // 创建验证状态显示区域
            const validationDiv = document.createElement('div');
            validationDiv.id = 'structure-validation';
            validationDiv.className = 'validation-status';
            validationDiv.style.marginTop = '10px';
            validationDiv.innerHTML = `
                <div class="validation-message"></div>
                <div class="validation-loading" style="display: none;">
                    <span>🔄 正在验证ID唯一性...</span>
                </div>
            `;

            // 创建重复报告按钮
            const reportBtn = document.createElement('button');
            reportBtn.type = 'button';
            reportBtn.className = 'duplicate-report-btn';
            reportBtn.style.cssText = 'margin-top: 10px; padding: 5px 10px; background: var(--fc-admin-blue); color: var(--fc-text-on-primary); border: none; border-radius: 3px; cursor: pointer;';
            reportBtn.textContent = '📊 查看重复ID报告';

            // 插入到结构字段后面
            const fieldContainer = structureField.closest('.form-row') || structureField.parentNode;
            fieldContainer.appendChild(validationDiv);
            fieldContainer.appendChild(reportBtn);

            // 绑定报告按钮事件
            reportBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.showDuplicateReport();
            });
        }

        bindEvents(structureField) {
            // 监听结构字段变化
            structureField.addEventListener('input', () => {
                this.handleStructureChange(structureField);
            });

            // 监听表单提交
            const form = structureField.closest('form');
            if (form) {
                form.addEventListener('submit', (e) => {
                    this.handleFormSubmit(e);
                });
            }
        }

        handleStructureChange(structureField) {
            const structureText = structureField.value.trim();

            if (!structureText) {
                this.clearValidationStatus();
                return;
            }

            try {
                const structure = JSON.parse(structureText);
                const templateId = this.getTemplateId();

                this.showValidationLoading();
                this.debounceValidate(structure, templateId);

            } catch (error) {
                this.showValidationResult({
                    isValid: false,
                    errors: ['JSON格式错误: ' + error.message]
                });
            }
        }

        debounceValidate(structure, templateId) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(() => {
                this.validateStructure(structure, templateId)
                    .then(result => this.showValidationResult(result))
                    .catch(error => {
                        console.error('验证失败:', error);
                        this.showValidationResult({
                            isValid: false,
                            errors: [error.message || '验证请求失败']
                        });
                    });
            }, this.debounceDelay);
        }

        validateStructure(structure, templateId = null) {
            return new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open('POST', this.validateUrl, true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-CSRFToken', this.getCSRFToken());

                xhr.onload = function() {
                    if (xhr.status === 200) {
                        try {
                            const response = JSON.parse(xhr.responseText);
                            if (response.success) {
                                resolve({
                                    isValid: response.is_valid,
                                    errors: response.errors || []
                                });
                            } else {
                                reject(new Error(response.message || '验证失败'));
                            }
                        } catch (e) {
                            reject(new Error('响应解析失败'));
                        }
                    } else {
                        reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                    }
                };

                xhr.onerror = function() {
                    reject(new Error('网络请求失败'));
                };

                xhr.send(JSON.stringify({
                    structure: structure,
                    template_id: templateId
                }));
            });
        }

        getTemplateId() {
            // 从URL获取模板ID
            const urlMatch = window.location.pathname.match(/\/(\d+)\/change\//);
            return urlMatch ? parseInt(urlMatch[1]) : null;
        }

        getCSRFToken() {
            if (window.FachuanCSRF && window.FachuanCSRF.getToken) return window.FachuanCSRF.getToken() || '';
            const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
            return tokenInput ? tokenInput.value : '';
        }

        showValidationLoading() {
            const validationDiv = document.querySelector('#structure-validation');
            if (validationDiv) {
                validationDiv.querySelector('.validation-loading').style.display = 'block';
                validationDiv.querySelector('.validation-message').style.display = 'none';
            }
        }

        showValidationResult(result) {
            const validationDiv = document.querySelector('#structure-validation');
            if (!validationDiv) return;

            const messageDiv = validationDiv.querySelector('.validation-message');
            const loadingDiv = validationDiv.querySelector('.validation-loading');

            loadingDiv.style.display = 'none';
            messageDiv.style.display = 'block';

            if (result.isValid) {
                validationDiv.className = 'validation-status valid';
                messageDiv.innerHTML = '<span style="color: var(--fc-success-text);">✅ 文件夹结构ID验证通过</span>';
            } else {
                validationDiv.className = 'validation-status invalid';
                const errorHtml = result.errors.map(error =>
                    `<div style="color: var(--fc-error-text); margin: 2px 0;">❌ ${this.escapeHtml(error)}</div>`
                ).join('');
                messageDiv.innerHTML = errorHtml;
            }
        }

        clearValidationStatus() {
            const validationDiv = document.querySelector('#structure-validation');
            if (validationDiv) {
                validationDiv.className = 'validation-status';
                validationDiv.querySelector('.validation-message').style.display = 'none';
                validationDiv.querySelector('.validation-loading').style.display = 'none';
            }
        }

        handleFormSubmit(e) {
            // 不再阻止提交，让后端的 FolderTemplateForm.clean_structure() 自动修复重复ID
            // 后端会自动修复重复ID并显示成功消息
            const validationDiv = document.querySelector('#structure-validation');
            if (validationDiv && validationDiv.classList.contains('invalid')) {
                // 显示提示信息，告知用户后端会自动修复
                const messageDiv = validationDiv.querySelector('.validation-message');
                if (messageDiv) {
                    messageDiv.innerHTML = '<span style="color: var(--fc-warning-text);">⏳ 正在提交，后端将自动修复重复ID...</span>';
                }
            }
        }

        showDuplicateReport() {
            const xhr = new XMLHttpRequest();
            xhr.open('GET', this.duplicateReportUrl, true);
            xhr.setRequestHeader('X-CSRFToken', this.getCSRFToken());

            xhr.onload = () => {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            this.displayDuplicateReport(response.report);
                        } else {
                            alert('获取报告失败: ' + response.error);
                        }
                    } catch (e) {
                        alert('响应解析失败');
                    }
                } else {
                    alert(`网络错误: HTTP ${xhr.status}`);
                }
            };

            xhr.onerror = () => {
                alert('网络请求失败');
            };

            xhr.send();
        }

        displayDuplicateReport(report) {
            let html = `
                <div class="duplicate-report" style="padding: 20px; max-height: 400px; overflow-y: auto;">
                    <h3 style="margin-top: 0;">📊 重复ID报告</h3>
                    <div style="background: var(--fc-bg-muted); padding: 10px; border-radius: 5px; margin: 10px 0;">
                        <p><strong>总模板数:</strong> ${report.total_templates}</p>
                        <p><strong>唯一ID数:</strong> ${report.total_unique_ids}</p>
                        <p><strong>重复ID数:</strong> ${report.duplicate_count}</p>
                    </div>
            `;

            if (report.duplicate_count > 0) {
                html += '<h4 style="color: var(--fc-error-text);">🚨 重复详情:</h4><ul style="max-height: 200px; overflow-y: auto;">';
                for (const [id, templates] of Object.entries(report.duplicates)) {
                    html += `<li style="margin: 5px 0;"><strong>${this.escapeHtml(id)}</strong>: ${templates.map(t => this.escapeHtml(t)).join(', ')}</li>`;
                }
                html += '</ul>';
            } else {
                html += '<p style="color: var(--fc-success-text); font-weight: bold;">✅ 未发现重复ID</p>';
            }

            html += '</div>';

            // 创建模态框
            this.showModal('重复ID报告', html);
        }

        showModal(title, content) {
            // 创建遮罩层
            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.5); z-index: 10000; display: flex;
                align-items: center; justify-content: center;
            `;

            // 创建模态框
            const modal = document.createElement('div');
            modal.style.cssText = `
                background: var(--fc-bg-card); border-radius: 8px; max-width: 600px; width: 90%;
                max-height: 80vh; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            `;

            modal.innerHTML = `
                <div style="padding: 15px; border-bottom: 1px solid var(--fc-border); display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0;">${this.escapeHtml(title)}</h3>
                    <button class="close-modal" style="background: none; border: none; font-size: 24px; cursor: pointer; color: var(--fc-text-muted);">&times;</button>
                </div>
                <div style="overflow-y: auto; max-height: calc(80vh - 80px);">
                    ${content}
                </div>
                <div style="padding: 15px; border-top: 1px solid var(--fc-border); text-align: right;">
                    <button class="close-modal" style="padding: 8px 16px; background: var(--fc-text-muted); color: var(--fc-text-on-primary); border: none; border-radius: 4px; cursor: pointer;">关闭</button>
                </div>
            `;

            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            // 绑定关闭事件
            const closeButtons = modal.querySelectorAll('.close-modal');
            closeButtons.forEach(btn => {
                btn.addEventListener('click', () => {
                    document.body.removeChild(overlay);
                });
            });

            // 点击遮罩层关闭
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    document.body.removeChild(overlay);
                }
            });
        }

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    }

    // 初始化ID验证管理器
    new IDValidationManager();

})();
