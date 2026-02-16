/**
 * @deprecated 此文件已废弃，请使用 folder_binding_app.js (Alpine.js 组件) 替代
 * 新组件位置: backend/apps/cases/static/cases/js/folder_binding_app.js
 * 迁移日期: 2026-01-08
 * 保留此文件仅供参考和回滚使用
 *
 * 案件文件夹绑定功能 JavaScript
 * 与合同模块保持一致的设计风格
 *
 * 功能包括：
 * - 绑定状态显示和更新
 * - 绑定对话框显示逻辑
 * - API 调用逻辑
 * - 按钮状态切换逻辑
 */

(function() {
    'use strict';

    // 文件夹绑定管理器
    var FolderBindingManager = {
        // DOM 元素
        elements: {
            bindingStatusText: null,
            bindFolderBtn: null,
            changeFolderBtn: null,
            unbindFolderBtn: null,
            folderDialog: null,
            folderDialogTitle: null,
            folderPathInput: null,
            folderPathError: null,
            cancelFolderDialog: null,
            confirmFolderBinding: null,
            overlay: null
        },

        // 状态
        currentBinding: null,
        isUpdatingBinding: false,

        // 初始化
        init: function() {
            this.initElements();
            this.bindEvents();
            this.loadBindingStatus();
        },

        // 初始化DOM元素
        initElements: function() {
            this.elements.bindingStatusText = document.getElementById('binding_status_text');
            this.elements.bindFolderBtn = document.getElementById('bind_folder_btn');
            this.elements.changeFolderBtn = document.getElementById('change_folder_btn');
            this.elements.unbindFolderBtn = document.getElementById('unbind_folder_btn');
            this.elements.folderDialog = document.getElementById('folder_binding_dialog');
            this.elements.folderDialogTitle = document.getElementById('folder_dialog_title');
            this.elements.folderPathInput = document.getElementById('folder_path_input');
            this.elements.folderPathError = document.getElementById('folder_path_error');
            this.elements.cancelFolderDialog = document.getElementById('cancel_folder_dialog');
            this.elements.confirmFolderBinding = document.getElementById('confirm_folder_binding');
            this.elements.overlay = document.getElementById('dialog_overlay');
        },

        // 绑定事件
        bindEvents: function() {
            var self = this;

            if (this.elements.bindFolderBtn) {
                this.elements.bindFolderBtn.addEventListener('click', function() {
                    self.showFolderBindingDialog(false);
                });
            }

            if (this.elements.changeFolderBtn) {
                this.elements.changeFolderBtn.addEventListener('click', function() {
                    self.showFolderBindingDialog(true);
                });
            }

            if (this.elements.unbindFolderBtn) {
                this.elements.unbindFolderBtn.addEventListener('click', function() {
                    self.removeBinding();
                });
            }

            if (this.elements.cancelFolderDialog) {
                this.elements.cancelFolderDialog.addEventListener('click', function() {
                    self.hideFolderBindingDialog();
                });
            }

            if (this.elements.confirmFolderBinding) {
                this.elements.confirmFolderBinding.addEventListener('click', function() {
                    self.handleConfirmBinding();
                });
            }

            // 支持回车键确认
            if (this.elements.folderPathInput) {
                this.elements.folderPathInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        self.handleConfirmBinding();
                    }
                });
            }

            // 点击遮罩层关闭对话框
            if (this.elements.overlay) {
                this.elements.overlay.addEventListener('click', function(e) {
                    if (e.target === self.elements.overlay) {
                        self.hideFolderBindingDialog();
                    }
                });
            }

            // 快捷路径按钮
            var quickPathBtns = document.querySelectorAll('.quick-path-btn');
            quickPathBtns.forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var path = this.getAttribute('data-path');
                    if (self.elements.folderPathInput) {
                        self.elements.folderPathInput.value = path;
                        self.elements.folderPathInput.focus();
                    }
                });
            });

            // 清空按钮
            var clearBtn = document.getElementById('clear_path_btn');
            if (clearBtn) {
                clearBtn.addEventListener('click', function() {
                    if (self.elements.folderPathInput) {
                        self.elements.folderPathInput.value = '';
                        self.elements.folderPathInput.focus();
                    }
                });
            }
        },

        // 获取案件ID
        getCaseId: function() {
            var match = window.location.pathname.match(/\/admin\/cases\/case\/(\d+)\/change\//);
            return match ? match[1] : null;
        },

        // 加载绑定状态
        loadBindingStatus: function() {
            var self = this;
            var caseId = this.getCaseId();

            if (!caseId) {
                console.error('无法获取案件ID');
                return;
            }

            if (!this.elements.bindingStatusText) {
                console.error('绑定状态显示元素不存在');
                return;
            }

            fetch('/api/v1/cases/' + caseId + '/folder-binding')
                .then(function(response) {
                    if (response.ok) {
                        return response.json();
                    } else if (response.status === 404) {
                        return null;
                    } else {
                        throw new Error('获取绑定状态失败');
                    }
                })
                .then(function(data) {
                    self.currentBinding = data;
                    self.updateBindingUI();
                })
                .catch(function(error) {
                    console.error('加载绑定状态失败:', error);
                    self.elements.bindingStatusText.textContent = '未绑定';
                    self.elements.bindingStatusText.style.color = '#666';
                    self.showBindingButtons(false);
                });
        },

        // 更新绑定UI
        updateBindingUI: function() {
            if (!this.elements.bindingStatusText) return;

            if (this.currentBinding) {
                var displayPath = this.currentBinding.folder_path_display || this.currentBinding.folder_path;
                var bindingTime = new Date(this.currentBinding.created_at).toLocaleString('zh-CN');

                this.elements.bindingStatusText.innerHTML =
                    '已绑定：<strong>' + this.escapeHtml(displayPath) + '</strong><br>' +
                    '<small style="color: #999;">绑定时间：' + bindingTime + '</small>';
                this.elements.bindingStatusText.style.color = '#2e7d32';
                this.showBindingButtons(true);
            } else {
                this.elements.bindingStatusText.textContent = '未绑定';
                this.elements.bindingStatusText.style.color = '#666';
                this.showBindingButtons(false);
            }
        },

        // 显示/隐藏绑定按钮
        showBindingButtons: function(isBound) {
            if (isBound) {
                if (this.elements.bindFolderBtn) this.elements.bindFolderBtn.style.display = 'none';
                if (this.elements.changeFolderBtn) this.elements.changeFolderBtn.style.display = 'inline-block';
                if (this.elements.unbindFolderBtn) this.elements.unbindFolderBtn.style.display = 'inline-block';
            } else {
                if (this.elements.bindFolderBtn) this.elements.bindFolderBtn.style.display = 'inline-block';
                if (this.elements.changeFolderBtn) this.elements.changeFolderBtn.style.display = 'none';
                if (this.elements.unbindFolderBtn) this.elements.unbindFolderBtn.style.display = 'none';
            }
        },

        // 显示文件夹绑定对话框
        showFolderBindingDialog: function(isUpdate) {
            if (!this.elements.folderDialog || !this.elements.overlay) return;

            this.isUpdatingBinding = isUpdate;

            if (this.elements.folderDialogTitle) {
                this.elements.folderDialogTitle.textContent = isUpdate ? '更换文件夹' : '绑定文件夹';
            }

            if (this.elements.folderPathInput) {
                this.elements.folderPathInput.value = isUpdate && this.currentBinding ? this.currentBinding.folder_path : '';
            }

            if (this.elements.folderPathError) {
                this.elements.folderPathError.style.display = 'none';
            }

            this.elements.overlay.style.display = 'block';
            this.elements.folderDialog.style.display = 'block';

            if (this.elements.folderPathInput) {
                this.elements.folderPathInput.focus();
            }
        },

        // 隐藏文件夹绑定对话框
        hideFolderBindingDialog: function() {
            if (!this.elements.folderDialog || !this.elements.overlay) return;

            this.elements.overlay.style.display = 'none';
            this.elements.folderDialog.style.display = 'none';

            if (this.elements.folderPathInput) {
                this.elements.folderPathInput.value = '';
            }

            if (this.elements.folderPathError) {
                this.elements.folderPathError.style.display = 'none';
            }
        },

        // 处理确认绑定
        handleConfirmBinding: function() {
            if (!this.elements.folderPathInput) return;

            var folderPath = this.elements.folderPathInput.value.trim();
            var error = this.validateFolderPath(folderPath);

            if (error) {
                this.showPathError(error);
                return;
            }

            this.hidePathError();
            this.createOrUpdateBinding(folderPath);
        },

        // 验证文件夹路径
        validateFolderPath: function(path) {
            if (!path || !path.trim()) {
                return '请输入文件夹路径';
            }

            path = path.trim();

            // 基本格式验证
            var patterns = [
                /^\/[^<>:"|?*]*$/,  // macOS/Linux 路径
                /^[A-Za-z]:\\[^<>:"|?*]*$/,  // Windows 路径
                /^\\\\[^\\]+\\[^<>:"|?*]*$/,  // UNC 路径
                /^smb:\/\/[^\/]+\/[^<>:"|?*]*$/  // SMB 路径
            ];

            var isValid = patterns.some(function(pattern) {
                return pattern.test(path);
            });

            if (!isValid) {
                return '请输入有效的文件夹路径格式';
            }

            return null;
        },

        // 显示路径错误
        showPathError: function(message) {
            if (this.elements.folderPathError) {
                this.elements.folderPathError.textContent = message;
                this.elements.folderPathError.style.display = 'block';
            }
        },

        // 隐藏路径错误
        hidePathError: function() {
            if (this.elements.folderPathError) {
                this.elements.folderPathError.style.display = 'none';
            }
        },

        // 创建或更新绑定
        createOrUpdateBinding: function(folderPath) {
            var self = this;
            var caseId = this.getCaseId();

            if (!caseId) {
                this.showPathError('无法获取案件ID');
                return;
            }

            var url = '/api/v1/cases/' + caseId + '/folder-binding';

            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    folder_path: folderPath
                })
            })
            .then(function(response) {
                if (response.ok) {
                    return response.json();
                } else {
                    return response.json().then(function(data) {
                        throw new Error(data.message || '操作失败');
                    });
                }
            })
            .then(function(data) {
                self.currentBinding = data;
                self.updateBindingUI();
                self.hideFolderBindingDialog();

                var message = self.isUpdatingBinding ? '文件夹更换成功' : '文件夹绑定成功';
                self.showSuccessMessage(message);
            })
            .catch(function(error) {
                console.error('绑定操作失败:', error);
                self.showPathError(error.message);
            });
        },

        // 解除绑定
        removeBinding: function() {
            if (!confirm('确定要解除文件夹绑定吗？')) {
                return;
            }

            var self = this;
            var caseId = this.getCaseId();

            if (!caseId) {
                alert('无法获取案件ID');
                return;
            }

            fetch('/api/v1/cases/' + caseId + '/folder-binding', {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': this.getCsrfToken()
                }
            })
            .then(function(response) {
                if (response.ok) {
                    self.currentBinding = null;
                    self.updateBindingUI();
                    self.showSuccessMessage('文件夹绑定已解除');
                } else {
                    throw new Error('解除绑定失败');
                }
            })
            .catch(function(error) {
                console.error('解除绑定失败:', error);
                alert('解除绑定失败：' + error.message);
            });
        },

        // 获取CSRF Token
        getCsrfToken: function() {
            return (window.FachuanCSRF && window.FachuanCSRF.getToken && window.FachuanCSRF.getToken()) || '';
        },

        // 显示成功消息
        showSuccessMessage: function(message) {
            var messageDiv = document.createElement('div');
            messageDiv.textContent = message;
            messageDiv.className = 'folder-binding-success-message';

            document.body.appendChild(messageDiv);

            setTimeout(function() {
                if (messageDiv.parentNode) {
                    messageDiv.parentNode.removeChild(messageDiv);
                }
            }, 3000);
        },

        // HTML转义
        escapeHtml: function(text) {
            var div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    };

    // 当DOM加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            FolderBindingManager.init();
        });
    } else {
        FolderBindingManager.init();
    }

    // 导出到全局作用域（用于调试）
    window.FolderBindingManager = FolderBindingManager;

})();
