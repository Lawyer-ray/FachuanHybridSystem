(function () {
  'use strict';

  function getCsrfToken() {
    if (window.FachuanCSRF && window.FachuanCSRF.getToken) return window.FachuanCSRF.getToken() || '';
    const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tokenElement && tokenElement.value) return tokenElement.value;
    const cookies = document.cookie ? document.cookie.split(';') : [];
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.startsWith('csrftoken=')) return cookie.substring('csrftoken='.length);
    }
    return '';
  }

  document.addEventListener('alpine:init', function () {
    Alpine.data('contractFolderScanApp', function (config) {
      return {
        contractId: config.contractId,
        hasFolderBinding: config.hasFolderBinding !== false,
        texts: config.texts || {},

        isOpen: false,
        isScanning: false,
        isConfirming: false,
        isLoadingSubfolders: false,

        scanSessionId: '',
        scanStatus: '',
        scanProgress: 0,
        scanCurrentFile: '',
        scanSummary: { total_files: 0, deduped_files: 0, classified_files: 0 },
        scanCandidates: [],
        scanError: '',
        pollTimer: null,

        scanScopeMode: 'all',
        scanRootPath: '',
        scanSubfolderOptions: [],
        scanSubfolder: '',
        subfoldersLoaded: false,

        get selectedCount() {
          return (this.scanCandidates || []).filter((item) => item.selected).length;
        },

        get scanStatusText() {
          if (this.scanError) return this.scanError;
          if (this.scanStatus === 'running') return this.texts.scanningFolder || '正在扫描文件夹';
          if (this.scanStatus === 'classifying') return this.texts.classifying || '正在 AI 分类';
          if (this.scanStatus === 'completed') return this.texts.completed || '扫描完成';
          if (this.scanStatus === 'failed') return this.texts.failed || '扫描失败';
          return '';
        },

        get scanStatusClass() {
          if (this.scanStatus === 'failed') return 'is-error';
          if (this.scanStatus === 'completed') return 'is-success';
          return 'is-pending';
        },

        get hasSubfolderOptions() {
          return Array.isArray(this.scanSubfolderOptions) && this.scanSubfolderOptions.length > 0;
        },

        openModal() {
          if (!this.hasFolderBinding) {
            this.scanError = this.texts.needBindFolder || '请先在“文档与提醒”中绑定文件夹';
            window.dispatchEvent(
              new CustomEvent('contract-folder-scan-needs-binding', { detail: { contractId: this.contractId } })
            );
            return;
          }
          this.isOpen = true;
          this.scanError = '';
          this.loadSubfolders(false);
          if (this.scanSessionId) {
            this.fetchStatus(true);
          }
        },

        closeModal() {
          if (this.isScanning || this.isConfirming) return;
          this.isOpen = false;
        },

        openFolder() {
          var contractId = this.contractId;
          fetch('/admin/contracts/contract/' + contractId + '/open-folder/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
          })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
              if (!data.success) {
                alert(data.error || '打开文件夹失败');
              }
            })
            .catch(function (err) { alert('请求失败: ' + (err.message || '未知错误')); });
        },

        clearPoll() {
          if (!this.pollTimer) return;
          window.clearTimeout(this.pollTimer);
          this.pollTimer = null;
        },

        async loadSubfolders(forceReload) {
          if (!forceReload && this.subfoldersLoaded) return;
          this.isLoadingSubfolders = true;
          try {
            const resp = await fetch(`/api/v1/contracts/${this.contractId}/folder-scan/subfolders`, {
              headers: { 'X-CSRFToken': getCsrfToken() },
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
              throw new Error(data.message || data.detail || this.texts.loadSubfoldersFailed || '加载子文件夹失败');
            }

            this.scanRootPath = (data && data.root_path) || '';
            this.scanSubfolderOptions = Array.isArray(data && data.subfolders) ? data.subfolders : [];
            const validSet = new Set((this.scanSubfolderOptions || []).map((item) => item.relative_path));
            if (!validSet.has(this.scanSubfolder)) {
              this.scanSubfolder = '';
            }
            if (!this.scanSubfolderOptions.length) {
              this.scanScopeMode = 'all';
            }
            this.subfoldersLoaded = true;
          } catch (err) {
            this.scanSubfolderOptions = [];
            this.scanSubfolder = '';
            this.scanScopeMode = 'all';
            this.scanError = (err && err.message) || (this.texts.loadSubfoldersFailed || '加载子文件夹失败');
            this.subfoldersLoaded = false;
          } finally {
            this.isLoadingSubfolders = false;
          }
        },

        buildScanPayload(rescan) {
          const payload = { rescan: Boolean(rescan), scan_subfolder: '' };
          if (this.scanScopeMode !== 'subfolder') return payload;

          if (!this.hasSubfolderOptions) {
            this.scanError = this.texts.noSubfolderOptions || '当前目录下没有可选子文件夹，将扫描全部内容';
            this.scanScopeMode = 'all';
            return payload;
          }

          if (!this.scanSubfolder) {
            this.scanError = this.texts.needSelectSubfolder || '请选择要扫描的子文件夹';
            return null;
          }

          payload.scan_subfolder = this.scanSubfolder;
          return payload;
        },

        async startScan(rescan) {
          if (this.isScanning) return;
          this.scanError = '';
          await this.loadSubfolders(false);
          const payload = this.buildScanPayload(rescan);
          if (!payload) return;

          this.isScanning = true;
          this.scanStatus = 'running';
          this.scanProgress = 0;
          this.scanCurrentFile = '';
          this.scanCandidates = [];
          this.clearPoll();

          fetch(`/api/v1/contracts/${this.contractId}/folder-scan`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify(payload),
          })
            .then(async (resp) => {
              const data = await resp.json().catch(() => ({}));
              if (!resp.ok) {
                if ((data && data.message) === '未绑定文件夹') {
                  this.hasFolderBinding = false;
                  window.dispatchEvent(
                    new CustomEvent('contract-folder-scan-needs-binding', { detail: { contractId: this.contractId } })
                  );
                }
                throw new Error(data.message || data.detail || this.texts.failed || '扫描失败');
              }
              return data;
            })
            .then((data) => {
              this.scanSessionId = (data && data.session_id) || '';
              this.fetchStatus(true);
            })
            .catch((err) => {
              this.isScanning = false;
              this.scanStatus = 'failed';
              this.scanError = (err && err.message) || (this.texts.failed || '扫描失败');
            });
        },

        fetchStatus(keepPolling) {
          if (!this.scanSessionId) return;
          fetch(`/api/v1/contracts/${this.contractId}/folder-scan/${this.scanSessionId}`, {
            headers: { 'X-CSRFToken': getCsrfToken() },
          })
            .then(async (resp) => {
              const data = await resp.json().catch(() => ({}));
              if (!resp.ok) {
                throw new Error(data.message || data.detail || this.texts.failed || '扫描失败');
              }
              return data;
            })
            .then((data) => {
              this.scanStatus = (data && data.status) || '';
              this.scanProgress = (data && data.progress) || 0;
              this.scanCurrentFile = (data && data.current_file) || '';
              this.scanSummary = (data && data.summary) || { total_files: 0, deduped_files: 0, classified_files: 0 };
              this.scanCandidates = this.normalizeCandidates((data && data.candidates) || []);
              this.scanError = (data && data.error_message) || '';

              this.isScanning = ['pending', 'running', 'classifying'].includes(this.scanStatus);
              if (keepPolling && this.isScanning) {
                this.clearPoll();
                this.pollTimer = window.setTimeout(() => {
                  this.fetchStatus(true);
                }, 1200);
              } else {
                this.clearPoll();
              }
            })
            .catch((err) => {
              this.isScanning = false;
              this.scanStatus = 'failed';
              this.scanError = (err && err.message) || (this.texts.failed || '扫描失败');
              this.clearPoll();
            });
        },

        normalizeCandidates(candidates) {
          return (candidates || []).map((candidate) => {
            const category = ['contract_original', 'supplementary_agreement', 'invoice'].includes(
              candidate.suggested_category
            )
              ? candidate.suggested_category
              : 'invoice';
            return {
              source_path: candidate.source_path,
              filename: candidate.filename,
              selected: candidate.selected !== false,
              category: category,
              reason: candidate.reason || '',
            };
          });
        },

        confirmImport() {
          if (this.isConfirming || !this.scanSessionId) return;
          const items = (this.scanCandidates || []).map((candidate) => ({
            source_path: candidate.source_path,
            selected: candidate.selected,
            category: candidate.category || 'invoice',
          }));

          this.isConfirming = true;
          fetch(`/api/v1/contracts/${this.contractId}/folder-scan/${this.scanSessionId}/confirm`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ items }),
          })
            .then(async (resp) => {
              const data = await resp.json().catch(() => ({}));
              if (!resp.ok) {
                throw new Error(data.message || data.detail || this.texts.importFailed || '导入失败，请稍后重试');
              }
              return data;
            })
            .then(() => {
              window.location.reload();
            })
            .catch((err) => {
              this.scanError = (err && err.message) || (this.texts.importFailed || '导入失败，请稍后重试');
            })
            .finally(() => {
              this.isConfirming = false;
            });
        },
      };
    });
  });
})();
