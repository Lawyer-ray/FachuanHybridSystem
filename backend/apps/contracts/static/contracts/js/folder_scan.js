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
        texts: config.texts || {},

        isOpen: false,
        isScanning: false,
        isConfirming: false,
        scanSessionId: '',
        scanStatus: '',
        scanProgress: 0,
        scanCurrentFile: '',
        scanSummary: { total_files: 0, deduped_files: 0, classified_files: 0 },
        scanCandidates: [],
        scanError: '',
        pollTimer: null,

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

        openModal() {
          this.isOpen = true;
          if (!this.scanSessionId && !this.isScanning) {
            this.startScan(false);
          } else if (this.scanSessionId) {
            this.fetchStatus(true);
          }
        },

        closeModal() {
          if (this.isScanning || this.isConfirming) return;
          this.isOpen = false;
        },

        clearPoll() {
          if (!this.pollTimer) return;
          window.clearTimeout(this.pollTimer);
          this.pollTimer = null;
        },

        startScan(rescan) {
          this.scanError = '';
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
            body: JSON.stringify({ rescan: Boolean(rescan) }),
          })
            .then(async (resp) => {
              const data = await resp.json().catch(() => ({}));
              if (!resp.ok) {
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
            const category = ['contract_original', 'supplementary_agreement', 'other'].includes(candidate.suggested_category)
              ? candidate.suggested_category
              : 'other';
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
            category: candidate.category || 'other',
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
