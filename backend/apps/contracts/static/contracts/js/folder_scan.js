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

        scanRootPath: '',
        scanSubfolderOptions: [],
        scanSubfolder: '',
        subfoldersLoaded: false,

        // 归档相关
        archiveCategory: '',
        archiveItemOptions: [],
        workLogSuggestions: [],

        // 案件信息提取（审级/法院/案号/主文）
        caseInfoExtractions: [],

        // AI 分类相关
        aiModels: [],
        aiModelId: '',
        isLoadingAIModels: false,
        aiClassifyResult: {},

        get selectedCount() {
          return (this.scanCandidates || []).filter((item) => item.selected).length;
        },

        get visibleCandidates() {
          return (this.scanCandidates || []).filter((item) => !item.skip_reason);
        },

        get showAIClassify() {
          return (
            !this.isScanning &&
            Boolean(this.scanSessionId) &&
            this.scanStatus === 'completed' &&
            this.visibleCandidates.length > 0
          );
        },

        get isAIClassifying() {
          return this.isScanning && this.scanStatus === 'classifying';
        },

        get aiClassifyLabel() {
          const count = this.visibleCandidates.length;
          return count > 0 ? '重新分类（' + count + '）' : '重新分类';
        },

        get aiClassifySummaryText() {
          const result = this.aiClassifyResult || {};
          if (!result || !result.targets) return '';
          const parts = ['成功 ' + (result.classified || 0)];
          if (result.invalid) parts.push('无法判定 ' + result.invalid);
          if (result.llm_failed) parts.push('调用失败 ' + result.llm_failed);
          const model = result.model ? '（模型：' + result.model + '）' : '';
          return 'AI 分类完成：' + parts.join(' / ') + model;
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

        get visibleCandidates() {
          return (this.scanCandidates || []).filter((item) => !item.skip_reason);
        },

        openModal() {
          if (!this.hasFolderBinding) {
            this.scanError = this.texts.needBindFolder || '请先在"文档与提醒"中绑定文件夹';
            window.dispatchEvent(
              new CustomEvent('contract-folder-scan-needs-binding', { detail: { contractId: this.contractId } })
            );
            return;
          }
          this.isOpen = true;
          this.scanError = '';
          this.loadSubfolders(false);
          this.loadAIModels();
          if (this.scanSessionId) {
            this.fetchStatus(true);
          } else {
            this.loadLatestSession();
          }
        },

        async loadLatestSession() {
          try {
            const resp = await fetch(`/api/v1/contracts/${this.contractId}/folder-scan/latest`, {
              headers: { 'X-CSRFToken': getCsrfToken() },
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) return;
            if (!data || !data.session_id) return;
            this.scanSessionId = data.session_id;
            this.scanStatus = data.status || '';
            this.scanProgress = data.progress || 0;
            this.scanCurrentFile = data.current_file || '';
            this.scanSummary = data.summary || { total_files: 0, deduped_files: 0, classified_files: 0 };
            this.scanCandidates = this.normalizeCandidates(data.candidates || []);
            this.scanError = data.error_message || '';
            this.archiveCategory = data.archive_category || '';
            this.archiveItemOptions = Array.isArray(data.archive_item_options) ? data.archive_item_options : [];
            this.workLogSuggestions = Array.isArray(data.work_log_suggestions)
              ? data.work_log_suggestions.map((item) => ({
                  date: item.date || '',
                  content: item.content || '',
                }))
              : [];
            this.aiClassifyResult = (data && data.ai_classify_result) || {};
            this.caseInfoExtractions = Array.isArray(data && data.case_info_extractions)
              ? data.case_info_extractions
              : [];
            this.isScanning = ['pending', 'running', 'classifying'].includes(this.scanStatus);
            if (this.isScanning) {
              this.fetchStatus(true);
            }
          } catch (_e) {
            // 静默忽略，用户可手动点扫描
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
            this.subfoldersLoaded = true;
          } catch (err) {
            this.scanSubfolderOptions = [];
            this.scanSubfolder = '';
            this.scanError = (err && err.message) || (this.texts.loadSubfoldersFailed || '加载子文件夹失败');
            this.subfoldersLoaded = false;
          } finally {
            this.isLoadingSubfolders = false;
          }
        },

        buildScanPayload(rescan) {
          // 不选子文件夹 = 扫描全部内容；选中则只扫该子文件夹
          return { rescan: Boolean(rescan), scan_subfolder: this.scanSubfolder || '' };
        },

        async loadAIModels() {
          if (this.aiModels.length || this.isLoadingAIModels) return;
          this.isLoadingAIModels = true;
          try {
            const resp = await fetch('/api/v1/llm/models', {
              headers: { 'X-CSRFToken': getCsrfToken() },
            });
            const data = await resp.json().catch(() => ({}));
            if (resp.ok && Array.isArray(data.models)) {
              this.aiModels = data.models;
            }
          } catch (_e) {
            // 静默忽略：仅影响模型下拉，默认模型仍可用
          } finally {
            this.isLoadingAIModels = false;
          }
        },

        async startAIClassify() {
          if (!this.scanSessionId || this.isScanning) return;
          this.scanError = '';
          this.isScanning = true;
          this.scanStatus = 'classifying';
          this.clearPoll();
          try {
            const resp = await fetch(
              `/api/v1/contracts/${this.contractId}/folder-scan/${this.scanSessionId}/ai-classify`,
              {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({
                  model_id: this.aiModelId || '',
                  scope: 'all',
                }),
              }
            );
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
              throw new Error(data.message || data.detail || this.texts.aiClassifyFailed || 'AI 分类发起失败');
            }
            this.fetchStatus(true);
          } catch (err) {
            this.isScanning = false;
            this.scanStatus = 'failed';
            this.scanError = (err && err.message) || (this.texts.aiClassifyFailed || 'AI 分类发起失败');
          }
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
          this.archiveCategory = '';
          this.archiveItemOptions = [];
          this.workLogSuggestions = [];
          this.aiClassifyResult = {};
          this.caseInfoExtractions = [];
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

              // 归档相关数据
              this.archiveCategory = (data && data.archive_category) || '';
              this.archiveItemOptions = Array.isArray(data && data.archive_item_options) ? data.archive_item_options : [];
              this.workLogSuggestions = Array.isArray(data && data.work_log_suggestions)
                ? data.work_log_suggestions.map((item) => ({
                    date: item.date || '',
                    content: item.content || '',
                  }))
                : [];
              this.aiClassifyResult = (data && data.ai_classify_result) || {};
              this.caseInfoExtractions = Array.isArray(data && data.case_info_extractions)
                ? data.case_info_extractions
                : [];

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
          var validCategories = [
            'contract_original', 'supplementary_agreement', 'invoice',
            'supervision_card', 'case_material',
          ];
          return (candidates || []).map((candidate) => {
            var suggestedCategory = candidate.suggested_category || '';
            // archive_document / authorization_material 归入案件材料
            var category = validCategories.includes(suggestedCategory)
              ? suggestedCategory
              : 'case_material';
            return {
              source_path: candidate.source_path,
              filename: candidate.filename,
              selected: candidate.already_imported ? false : (candidate.selected !== false),
              category: category,
              reason: candidate.reason || '',
              archive_item_code: candidate.archive_item_code || '',
              archive_item_name: candidate.archive_item_name || '',
              is_docx: candidate.is_docx || false,
              skip_reason: candidate.skip_reason || '',
              already_imported: candidate.already_imported || false,
              classified_by: candidate.classified_by || '',
            };
          });
        },

        categoryLabel(category) {
          var labels = {
            'contract_original': '合同正本',
            'supplementary_agreement': '补充协议',
            'invoice': '发票',
            'supervision_card': '监督卡',
            'case_material': '案件材料',
          };
          return labels[category] || category;
        },

        isCaseMaterial(candidate) {
          return candidate.category === 'case_material';
        },

        hasUnmatchedArchiveItem(candidate) {
          return candidate.category === 'case_material' && !candidate.archive_item_code;
        },

        selectArchiveItem(candidate, code) {
          var option = this.archiveItemOptions.find(function (opt) { return opt.code === code; });
          if (option) {
            candidate.archive_item_code = option.code;
            candidate.archive_item_name = option.name;
          }
        },

        addWorkLogEntry() {
          this.workLogSuggestions.push({ date: '', content: '' });
        },

        removeWorkLogEntry(index) {
          this.workLogSuggestions.splice(index, 1);
        },

        confirmImport() {
          if (this.isConfirming || !this.scanSessionId) return;
          const items = (this.scanCandidates || [])
            .filter((candidate) => !candidate.skip_reason)
            .map((candidate) => ({
              source_path: candidate.source_path,
              selected: candidate.selected,
              category: candidate.category || 'archive_document',
              archive_item_code: candidate.archive_item_code || '',
              is_docx: candidate.is_docx || false,
            }));

          // 过滤掉空的工作日志条目
          const validWorkLogs = (this.workLogSuggestions || []).filter(
            (entry) => entry.date && entry.content
          );

          this.isConfirming = true;
          fetch(`/api/v1/contracts/${this.contractId}/folder-scan/${this.scanSessionId}/confirm`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({
              items: items,
              work_log_suggestions: validWorkLogs,
            }),
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
