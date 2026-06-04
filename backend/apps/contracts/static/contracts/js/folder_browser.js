/**
 * 文件夹浏览器组件 - Finder 风格
 * 支持本地文件系统 + 云存储（WebDAV / OneDrive）
 */

document.addEventListener('alpine:init', () => {
    Alpine.data('folderBrowser', (contractId) => ({
        contractId: contractId,
        showBrowser: false,
        loading: false,
        loadingColumn: null,
        columns: [],
        binding: null,
        error: null,
        manualPath: '',
        // Cloud storage state
        storageType: 'local',
        storageAccountId: '',
        cloudAccounts: [],

        async init() {
            await this.loadBinding();
            await this.loadCloudAccounts();
        },

        get filteredAccounts() {
            return this.cloudAccounts.filter(a => a.storage_type === this.storageType);
        },

        storageTypeLabel(type) {
            const labels = { webdav: 'WebDAV', onedrive: 'OneDrive', s3: 'S3', google_drive: 'Google Drive', dropbox: 'Dropbox' };
            return labels[type] || type;
        },

        onStorageTypeChange() {
            this.storageAccountId = '';
        },

        async loadCloudAccounts() {
            try {
                const response = await fetch('/api/v1/contracts/cloud-storage-accounts', {
                    headers: { 'X-CSRFToken': this.getCsrfToken() },
                    credentials: 'same-origin'
                });
                if (response.ok) {
                    this.cloudAccounts = await response.json();
                }
            } catch (e) {
                console.error('加载云存储账号失败:', e);
            }
        },

        async loadBinding() {
            if (!this.contractId) return;
            try {
                const response = await fetch(`/api/v1/contracts/${this.contractId}/folder-binding`, {
                    headers: { 'X-CSRFToken': this.getCsrfToken() },
                    credentials: 'same-origin'
                });
                if (response.ok) {
                    const data = await response.json();
                    if (data) {
                        this.binding = data;
                    }
                } else if (response.status === 404) {
                    this.binding = null;
                }
            } catch (error) {
                console.error('加载绑定失败:', error);
            }
        },

        async openBrowser() {
            if (this.storageType !== 'local' && !this.storageAccountId) {
                this.error = '请先选择云存储账号';
                return;
            }
            this.showBrowser = true;
            this.error = null;
            this.columns = [];
            this.manualPath = '';
            await this.loadRoots();
        },

        closeBrowser() {
            this.showBrowser = false;
            this.columns = [];
            this.error = null;
            this.manualPath = '';
        },

        _browseUrl(path) {
            const sp = new URLSearchParams();
            if (path) sp.set('path', path);
            if (this.storageType !== 'local') {
                sp.set('storage_type', this.storageType);
                sp.set('storage_account_id', this.storageAccountId);
            }
            return `/api/v1/contracts/folder-browse?${sp.toString()}`;
        },

        async loadRoots() {
            this.loading = true;
            this.error = null;
            try {
                const response = await fetch(this._browseUrl(null), {
                    headers: { 'X-CSRFToken': this.getCsrfToken() },
                    credentials: 'same-origin'
                });
                if (!response.ok) throw new Error('加载根目录失败');
                const data = await response.json();
                if (!data.browsable) {
                    this.error = data.message || '无法访问根目录';
                    return;
                }
                this.columns = [{ path: null, entries: data.entries || [], selectedIndex: -1 }];
            } catch (error) {
                console.error('加载根目录失败:', error);
                this.error = '加载根目录失败';
            } finally {
                this.loading = false;
            }
        },

        async selectFolder(columnIndex, entryIndex, entry) {
            if (this.loadingColumn) return;
            if (this.columns[columnIndex].selectedIndex === entryIndex) return;

            this.columns[columnIndex].selectedIndex = entryIndex;
            const newLength = columnIndex + 1;
            if (this.columns.length > newLength) {
                this.columns.splice(newLength);
            }
            this.loadingColumn = entry.path;
            await this.loadSubfolders(entry.path);

            this.$nextTick(() => {
                const container = this.$el.querySelector('.finder-columns');
                if (container) container.scrollLeft = container.scrollWidth;
            });
        },

        async loadSubfolders(path) {
            this.loadingColumn = path;
            this.error = null;
            try {
                const response = await fetch(this._browseUrl(path), {
                    headers: { 'X-CSRFToken': this.getCsrfToken() },
                    credentials: 'same-origin'
                });
                if (!response.ok) throw new Error('加载文件夹失败');
                const data = await response.json();
                if (!data.browsable) {
                    this.error = data.message || '无法访问此路径';
                    return;
                }
                if (data.entries && data.entries.length > 0) {
                    this.columns.push({ path: path, entries: data.entries, selectedIndex: -1 });
                }
                this.manualPath = path;
            } catch (error) {
                console.error('加载文件夹失败:', error);
                this.error = '加载文件夹失败';
            } finally {
                this.loadingColumn = null;
            }
        },

        async bindManualPath() {
            if (!this.manualPath || !this.manualPath.trim()) {
                this.error = '请输入文件夹路径';
                return;
            }
            await this.selectFolderPath(this.manualPath.trim());
        },

        async selectFolderPath(path) {
            this.loading = true;
            this.error = null;
            try {
                const body = { folder_path: path };
                if (this.storageType !== 'local') {
                    body.storage_type = this.storageType;
                    body.storage_account_id = Number(this.storageAccountId);
                }
                const response = await fetch(`/api/v1/contracts/${this.contractId}/folder-binding`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    credentials: 'same-origin',
                    body: JSON.stringify(body)
                });
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.message || '绑定失败');
                }
                this.binding = await response.json();
                this.closeBrowser();
                this.showMessage('文件夹绑定成功', 'success');
            } catch (error) {
                console.error('绑定文件夹失败:', error);
                this.error = error.message || '绑定失败';
            } finally {
                this.loading = false;
            }
        },

        getCurrentPath() {
            for (let i = this.columns.length - 1; i >= 0; i--) {
                const col = this.columns[i];
                if (col.selectedIndex >= 0 && col.entries[col.selectedIndex]) {
                    return col.entries[col.selectedIndex].path;
                }
            }
            return null;
        },

        async bindCurrentPath() {
            const path = this.getCurrentPath();
            if (!path) {
                this.error = '请选择一个文件夹';
                return;
            }
            await this.selectFolderPath(path);
        },

        async unbindFolder() {
            if (!confirm('确定要解除文件夹绑定吗？')) return;
            this.loading = true;
            try {
                const response = await fetch(`/api/v1/contracts/${this.contractId}/folder-binding`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': this.getCsrfToken() },
                    credentials: 'same-origin'
                });
                if (!response.ok) throw new Error('解除绑定失败');
                this.binding = null;
                this.showMessage('已解除文件夹绑定', 'success');
            } catch (error) {
                console.error('解除绑定失败:', error);
                this.showMessage('解除绑定失败', 'error');
            } finally {
                this.loading = false;
            }
        },

        getCsrfToken() {
            return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        },

        showMessage(message, type) {
            const messagesDiv = document.querySelector('.messagelist');
            if (messagesDiv) {
                const messageItem = document.createElement('li');
                messageItem.className = type === 'success' ? 'success' : 'error';
                messageItem.textContent = message;
                messagesDiv.appendChild(messageItem);
                setTimeout(() => messageItem.remove(), 3000);
            }
        }
    }));
});
