/**
 * case_materials_manage_scan.js
 * Folder-scan related methods for the case materials management Alpine app.
 * Exposes `window.CaseMaterialsScanMethods` which are mixed into the main Alpine data.
 * Must be loaded AFTER case_materials_manage_utils.js and BEFORE case_materials_manage.js.
 */
(function () {
  'use strict';

  var utils = window.CaseMaterialsUtils;
  var getCsrfToken = utils.getCsrfToken;

  /**
   * Scan-related methods to be merged into the Alpine.data return object.
   * `this` inside each method refers to the Alpine component instance.
   */
  window.CaseMaterialsScanMethods = {

    clearScanPollTimer() {
      if (!this.scanPollTimer) return;
      window.clearTimeout(this.scanPollTimer);
      this.scanPollTimer = null;
    },

    async loadScanSubfolders(forceReload) {
      if (!forceReload && this.scanSubfoldersLoaded) return;
      this.isLoadingScanSubfolders = true;
      try {
        const resp = await fetch(`/api/v1/cases/${this.caseId}/folder-scan/subfolders`, {
          headers: { 'X-CSRFToken': getCsrfToken() },
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(data.message || data.detail || this.scanTexts.loadSubfoldersFailed || '加载子文件夹失败');
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
        this.scanSubfoldersLoaded = true;
      } catch (err) {
        this.scanSubfolderOptions = [];
        this.scanSubfolder = '';
        this.scanScopeMode = 'all';
        this.scanSubfoldersLoaded = false;
        this.scanErrorMessage = (err && err.message) || (this.scanTexts.loadSubfoldersFailed || '加载子文件夹失败');
      } finally {
        this.isLoadingScanSubfolders = false;
      }
    },

    buildScanPayload(rescan) {
      const payload = {
        rescan: Boolean(rescan),
        scan_subfolder: '',
        enable_recognition: Boolean(this.scanEnableRecognition),
      };

      if (this.scanScopeMode !== 'subfolder') return payload;
      if (!Array.isArray(this.scanSubfolderOptions) || !this.scanSubfolderOptions.length) {
        this.scanScopeMode = 'all';
        this.scanSubfolder = '';
        this.showMessage(this.scanTexts.noSubfolderOptions || '当前目录下没有可选子文件夹，将扫描全部内容', 'success');
        return payload;
      }
      if (!this.scanSubfolder) {
        this.scanErrorMessage = this.scanTexts.needSelectSubfolder || '请选择要扫描的子文件夹';
        return null;
      }

      payload.scan_subfolder = this.scanSubfolder;
      return payload;
    },

    async startFolderScan(rescan) {
      this.scanPanelVisible = true;
      this.scanErrorMessage = '';
      this.scanStatusMessage = '';
      await this.loadScanSubfolders(false);
      const payload = this.buildScanPayload(rescan);
      if (!payload) return;

      this.isScanning = true;
      this.clearScanPollTimer();
      fetch(`/api/v1/cases/${this.caseId}/folder-scan`, {
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
            throw new Error(data.message || data.detail || this.scanTexts.failed || '扫描失败');
          }
          return data;
        })
        .then((data) => {
          this.scanSessionId = (data && data.session_id) || '';
          this.scanStatus = (data && data.status) || 'running';
          this.scanProgress = 0;
          this.scanCandidates = [];
          this.scanPrefillMap = {};
          this.prefillAppliedSessionId = '';
          this.syncScanSessionToUrl(this.scanSessionId);
          this.fetchScanStatus(this.scanSessionId, true);
        })
        .catch((err) => {
          this.isScanning = false;
          this.scanStatus = 'failed';
          this.scanErrorMessage = (err && err.message) || (this.scanTexts.failed || '扫描失败');
          this.showMessage(this.scanErrorMessage, 'error');
        });
    },

    fetchScanStatus(sessionId, keepPolling) {
      if (!sessionId) return;
      fetch(`/api/v1/cases/${this.caseId}/folder-scan/${sessionId}`, {
        headers: { 'X-CSRFToken': getCsrfToken() },
      })
        .then(async (resp) => {
          const data = await resp.json().catch(() => ({}));
          if (!resp.ok) {
            throw new Error(data.message || data.detail || this.scanTexts.failed || '扫描失败');
          }
          return data;
        })
        .then((data) => {
          this.scanStatus = (data && data.status) || '';
          this.scanProgress = (data && data.progress) || 0;
          this.scanCurrentFile = (data && data.current_file) || '';
          this.scanSubfolder = (data && data.scan_subfolder) || '';
          this.scanScopeMode = this.scanSubfolder ? 'subfolder' : 'all';
          this.scanEnableRecognition = Boolean(data && data.enable_recognition);
          this.scanSummary = (data && data.summary) || { total_files: 0, deduped_files: 0, classified_files: 0 };
          this.scanCandidates = this.normalizeScanCandidates((data && data.candidates) || []);
          this.scanErrorMessage = (data && data.error_message) || '';
          if (data && data.prefill_map && typeof data.prefill_map === 'object') {
            this.scanPrefillMap = data.prefill_map;
          }

          this.isScanning = ['pending', 'running', 'classifying'].includes(this.scanStatus);

          if (this.scanStatus === 'staged' && this.prefillAppliedSessionId !== String(sessionId)) {
            this.prefillAppliedSessionId = String(sessionId);
            this.load();
          }

          if (keepPolling && this.isScanning) {
            this.clearScanPollTimer();
            this.scanPollTimer = window.setTimeout(() => {
              this.fetchScanStatus(sessionId, true);
            }, 1200);
          } else {
            this.clearScanPollTimer();
          }
        })
        .catch((err) => {
          this.isScanning = false;
          this.clearScanPollTimer();
          this.scanStatus = 'failed';
          this.scanErrorMessage = (err && err.message) || (this.scanTexts.failed || '扫描失败');
          this.showMessage(this.scanErrorMessage, 'error');
        });
    },

    normalizeScanCandidates(candidates) {
      const dc = this.defaultCategory;
      const singleAuthorityId = (this.supervisingAuthorities || []).length === 1 ? String(this.supervisingAuthorities[0].id) : '';
      return (candidates || []).map((candidate) => {
        let category = ['party', 'non_party'].includes(candidate.suggested_category) ? candidate.suggested_category : '';
        let side = category === 'party' && ['our', 'opponent'].includes(candidate.suggested_side) ? candidate.suggested_side : '';
        // 如果页面指定了 defaultCategory，覆盖扫描建议的分类
        if (dc && category !== dc) {
          category = dc;
          side = dc === 'party' ? (side || 'our') : '';
        }
        const partyIds = Array.isArray(candidate.suggested_party_ids)
          ? candidate.suggested_party_ids
              .map((item) => parseInt(item, 10))
              .filter((item) => Number.isInteger(item) && item > 0)
          : [];
        const supervisingAuthorityIdRaw = parseInt(candidate.suggested_supervising_authority_id, 10);
        let authorityId =
          category === 'non_party' && Number.isInteger(supervisingAuthorityIdRaw) && supervisingAuthorityIdRaw > 0
            ? String(supervisingAuthorityIdRaw)
            : '';
        // 非当事人材料且只有一个主管机关时，自动选择
        if (category === 'non_party' && !authorityId && singleAuthorityId) {
          authorityId = singleAuthorityId;
        }
        return {
          source_path: candidate.source_path,
          filename: candidate.filename,
          selected: candidate.selected !== false,
          category: category,
          side: side,
          type_name_hint: candidate.type_name_hint || '',
          party_ids: category === 'party' ? partyIds : [],
          supervising_authority_id: authorityId,
          reason: candidate.reason || '',
        };
      });
    },

    async stageSelectedScanCandidates(options) {
      const silent = Boolean(options && options.silent);
      if (this.isStaging || !this.scanSessionId) return null;
      const items = (this.scanCandidates || [])
        .filter((candidate) => candidate.selected)
        .map((candidate) => ({
          source_path: candidate.source_path,
          selected: true,
          category: candidate.category || 'unknown',
          side: candidate.side || 'unknown',
          type_name_hint: candidate.type_name_hint || '',
          supervising_authority_id: candidate.category === 'non_party' ? (candidate.supervising_authority_id ? parseInt(candidate.supervising_authority_id, 10) || null : null) : null,
          party_ids: candidate.category === 'party' ? candidate.party_ids || [] : [],
        }));

      if (!items.length) {
        const message = this.scanTexts.noPdf || '未找到可导入的 PDF';
        if (!silent) this.showMessage(message, 'error');
        throw new Error(message);
      }

      this.isStaging = true;
      try {
        const resp = await fetch(`/api/v1/cases/${this.caseId}/folder-scan/${this.scanSessionId}/stage`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
          },
          body: JSON.stringify({ items }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(data.message || data.detail || this.scanTexts.importFailed || '导入失败，请稍后重试');
        }

        this.scanStatus = (data && data.status) || 'staged';
        this.scanSessionId = (data && data.session_id) || this.scanSessionId;
        this.scanPrefillMap = (data && data.prefill_map) || {};
        this.prefillAppliedSessionId = this.scanSessionId;
        this.lastUploadedIds = (data && data.attachment_ids) || [];

        if (data && data.materials_url) {
          const targetUrl = new URL(data.materials_url, window.location.href);
          if (this.defaultCategory) {
            targetUrl.searchParams.set('category', this.defaultCategory);
          }
          window.history.replaceState({}, '', targetUrl.toString());
        } else {
          this.syncScanSessionToUrl(this.scanSessionId);
        }

        await this.load();
        if (!silent) {
          this.showMessage('导入附件成功，请完善分类后保存', 'success');
        }
        return data;
      } catch (err) {
        if (!silent) {
          this.showMessage((err && err.message) || (this.scanTexts.importFailed || '导入失败，请稍后重试'), 'error');
        }
        throw err;
      } finally {
        this.isStaging = false;
      }
    },

    async ensureScanPreparedForSave() {
      if (!this.scanSessionId || !(this.scanCandidates || []).length) return;
      if (this.scanStatus === 'staged') return;
      await this.stageSelectedScanCandidates({ silent: true });
    },

    syncScanSessionToUrl(sessionId) {
      if (!window || !window.history || !window.location) return;
      try {
        const url = new URL(window.location.href);
        if (sessionId) {
          url.searchParams.set('scan_session', sessionId);
        } else {
          url.searchParams.delete('scan_session');
        }
        url.searchParams.delete('open_scan');
        // 保留 category 参数
        if (this.defaultCategory) {
          url.searchParams.set('category', this.defaultCategory);
        }
        window.history.replaceState({}, '', url.toString());
      } catch (_) {
      }
    },

  };
})();
