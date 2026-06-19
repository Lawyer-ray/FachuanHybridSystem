/**
 * case_materials_manage.js
 * Main Alpine.js application for the case materials management page.
 * Handles core row management, filtering, upload, and save logic.
 * Scan-related methods are mixed in from CaseMaterialsScanMethods.
 * Must be loaded AFTER case_materials_manage_utils.js and case_materials_manage_scan.js.
 */
(function () {
  'use strict';

  var utils = window.CaseMaterialsUtils;
  var getCsrfToken = utils.getCsrfToken;
  var normalizeCandidate = utils.normalizeCandidate;
  var readQueryValue = utils.readQueryValue;
  var mergeFiles = utils.mergeFiles;
  var scanMethods = window.CaseMaterialsScanMethods;

  document.addEventListener('alpine:init', function () {
    Alpine.data('caseMaterialsManageApp', function (config) {
      return Object.assign({

        caseId: config.caseId,
        detailUrl: config.detailUrl || '',
        partyTypes: config.partyTypes || [],
        nonPartyTypes: config.nonPartyTypes || [],
        ourParties: config.ourParties || [],
        opponentParties: config.opponentParties || [],
        supervisingAuthorities: config.supervisingAuthorities || [],
        defaultCategory: ['party', 'non_party'].includes(config.defaultCategory) ? config.defaultCategory : '',

        rows: [],
        isLoading: false,
        isUploading: false,
        isSaving: false,
        isDragging: false,
        flashDropzone: false,
        recentUploadedCount: 0,
        message: '',
        messageType: 'success',
        messageTimer: null,
        uploadCategory: ['party', 'non_party'].includes(config.defaultCategory) ? config.defaultCategory : 'party',
        lastUploadedIds: [],
        pendingFiles: [],
        searchKeyword: '',
        filterCategory: ['party', 'non_party'].includes(config.defaultCategory) ? config.defaultCategory : 'all',
        filterSide: '',
        filterAuthorityId: '',
        onlyUnfinished: false,
        onlyUnbound: false,
        selectedIds: [],
        scanTexts: config.scanTexts || {},
        scanPanelVisible: Boolean(config.openScan),
        scanSessionId: config.scanSessionId || '',
        scanStatus: '',
        scanProgress: 0,
        scanCurrentFile: '',
        scanSummary: { total_files: 0, deduped_files: 0, classified_files: 0 },
        scanCandidates: [],
        scanPrefillMap: {},
        prefillAppliedSessionId: '',
        scanPollTimer: null,
        isScanning: false,
        isStaging: false,
        isLoadingScanSubfolders: false,
        scanStatusMessage: '',
        scanErrorMessage: '',
        scanScopeMode: 'all',
        scanRootPath: '',
        scanSubfolderOptions: [],
        scanSubfolder: '',
        scanSubfoldersLoaded: false,
        scanEnableRecognition: false,
        redirectTimer: null,

        get uploadButtonText() {
          if (this.isUploading) return '上传中...';
          const n = (this.pendingFiles || []).length;
          return n ? `上传（${n}）` : '上传';
        },

        get dropzoneTitle() {
          if (this.isDragging) return '松开鼠标即可添加文件';
          if (this.isUploading) return '正在上传...';
          if (this.recentUploadedCount) return `已上传 ${this.recentUploadedCount} 个文件`;
          const n = (this.pendingFiles || []).length;
          if (n) return `已选择 ${n} 个文件`;
          return '拖拽文件到这里';
        },

        get dropzoneDesc() {
          if (this.isDragging) return '支持多文件拖拽';
          if (this.isUploading) return '请稍候，上传完成后会出现在下方列表';
          if (this.recentUploadedCount) return '文件已落到日志附件，请在下方完善分类并保存';
          const n = (this.pendingFiles || []).length;
          if (n) return '点击右侧"上传"开始上传，或继续拖拽追加文件';
          return '';
        },

        get selectedScanCount() {
          return (this.scanCandidates || []).filter((item) => item.selected).length;
        },

        get scanStatusText() {
          if (this.scanStatusMessage) return this.scanStatusMessage;
          if (this.scanErrorMessage) return this.scanErrorMessage;
          if (this.scanStatus === 'running') return this.scanTexts.scanningFolder || '正在扫描文件夹';
          if (this.scanStatus === 'classifying') return this.scanTexts.classifying || '正在材料分类';
          if (this.scanStatus === 'completed' || this.scanStatus === 'staged') return this.scanTexts.completed || '扫描完成';
          if (this.scanStatus === 'failed') return this.scanTexts.failed || '扫描失败';
          return '';
        },

        get scanStatusClass() {
          if (this.scanStatus === 'failed') return 'is-error';
          if (this.scanStatus === 'completed' || this.scanStatus === 'staged') return 'is-success';
          return 'is-pending';
        },

        get scanScopeDisplay() {
          if (!this.scanSubfolder) return '扫描范围：全部文件夹';
          return `扫描范围：${this.scanSubfolder}`;
        },

        get filteredRows() {
          const keyword = (this.searchKeyword || '').toLowerCase();
          return (this.rows || []).filter((row) => {
            if (keyword && !(row.fileName || '').toLowerCase().includes(keyword)) return false;

            if (this.filterCategory === 'unclassified') {
              if (row.category) return false;
            } else if (this.filterCategory === 'party') {
              if (row.category !== 'party') return false;
              if (this.filterSide && row.side !== this.filterSide) return false;
            } else if (this.filterCategory === 'non_party') {
              if (row.category !== 'non_party') return false;
              if (this.filterAuthorityId && String(row.supervisingAuthorityId) !== String(this.filterAuthorityId)) return false;
            } else if (this.filterCategory === 'all') {
            } else {
              if (row.category !== this.filterCategory) return false;
            }

            if (this.onlyUnbound && row.isBound) return false;
            if (this.onlyUnfinished && !this.isRowUnfinished(row)) return false;
            return true;
          });
        },

        get allFilteredSelected() {
          const ids = (this.filteredRows || []).map((row) => String(row.attachmentId));
          if (!ids.length) return false;
          const selected = new Set((this.selectedIds || []).map(String));
          return ids.every((id) => selected.has(id));
        },

        get partiallyFilteredSelected() {
          const ids = (this.filteredRows || []).map((row) => String(row.attachmentId));
          if (!ids.length) return false;
          const selected = new Set((this.selectedIds || []).map(String));
          let hit = 0;
          for (const id of ids) {
            if (selected.has(id)) hit += 1;
          }
          return hit > 0 && hit < ids.length;
        },

        init() {
          const sessionFromQuery = readQueryValue('scan_session');
          if (sessionFromQuery) {
            this.scanSessionId = sessionFromQuery;
            this.scanPanelVisible = true;
          }
          // 从 URL 参数恢复 defaultCategory（覆盖配置中的值）
          const categoryFromQuery = readQueryValue('category');
          if (['party', 'non_party'].includes(categoryFromQuery)) {
            this.defaultCategory = categoryFromQuery;
            this.uploadCategory = categoryFromQuery;
            this.filterCategory = categoryFromQuery;
          }
          this.load();
          // 始终加载子文件夹列表，确保"指定子文件夹"选项可点击
          this.loadScanSubfolders(false);
          if (this.scanSessionId) {
            this.fetchScanStatus(this.scanSessionId, true);
          }
        },

        showMessage(message, type) {
          if (this.messageTimer) {
            window.clearTimeout(this.messageTimer);
            this.messageTimer = null;
          }
          this.message = message;
          this.messageType = type || 'success';
          this.messageTimer = window.setTimeout(() => {
            this.message = '';
            this.messageTimer = null;
          }, 5000);
        },

        redirectToDetailAfterSave() {
          if (!this.detailUrl) return;
          if (this.redirectTimer) {
            window.clearTimeout(this.redirectTimer);
            this.redirectTimer = null;
          }
          this.redirectTimer = window.setTimeout(() => {
            this.redirectTimer = null;
            // 根据 defaultCategory 设置返回详情页时激活的 Tab
            if (this.defaultCategory === 'party') {
              localStorage.setItem('caseDetailTab', 'party_materials');
            } else if (this.defaultCategory === 'non_party') {
              localStorage.setItem('caseDetailTab', 'non_party_materials');
            }
            window.location.href = this.detailUrl;
          }, 900);
        },

        authTitle(auth) {
          const type = auth.authority_type_display || auth.authority_type || '';
          const name = auth.name || '';
          if (type && name) return `${type} - ${name}`;
          return name || type || '主管机关';
        },

        partyTitle(p) {
          const name = p.name || '';
          const status = p.legal_status_display || '';
          if (name && status) return `${name}（${status}）`;
          return name || status || '当事人';
        },

        partyOptions(row) {
          if (row.side === 'our') return this.ourParties;
          if (row.side === 'opponent') return this.opponentParties;
          return [];
        },

        typeOptions(row) {
          if (row.category === 'party') return this.partyTypes;
          if (row.category === 'non_party') return this.nonPartyTypes;
          return [];
        },

        isUserEvent(event) {
          if (!event) return true;
          if (event.isTrusted === undefined) return true;
          return event.isTrusted === true;
        },

        onCategoryChange(row, event) {
          if (!this.isUserEvent(event)) return;
          const category = event && event.target ? String(event.target.value || '') : (row.category || '');
          if (row.lastCategory === category) return;
          this.applyCategory(row, category);
          row.lastCategory = category;
          if (this.shouldBroadcast(row)) {
            this.broadcastToSelected((target) => {
              if (target.lastCategory === category) return;
              this.applyCategory(target, category);
              target.lastCategory = category;
            });
          }
          // 切换大类后，如果当前筛选为"未分类"，自动切到"全部"。
          // 否则仅按当前分类过滤会让其余待处理文件看起来"消失"，影响连续处理。
          if (category && this.filterCategory === 'unclassified') {
            this.filterCategory = 'all';
            this.onFilterCategoryChange();
          }
        },

        onScanCandidateCategoryChange(candidate) {
          // 切换为非当事人材料且只有一个主管机关时，自动选择
          if (candidate.category === 'non_party' && !candidate.supervising_authority_id && (this.supervisingAuthorities || []).length === 1) {
            candidate.supervising_authority_id = String(this.supervisingAuthorities[0].id);
          }
          // 切换为当事人材料时，清空主管机关
          if (candidate.category === 'party') {
            candidate.supervising_authority_id = '';
          }
        },

        onSideChange(row, event) {
          if (!this.isUserEvent(event)) return;
          const side = row.side || '';
          row.partyIds = [];
          if (this.shouldBroadcast(row)) {
            this.broadcastToSelected((target) => {
              if (target.category !== 'party') return;
              target.side = side;
              target.partyIds = [];
            });
          }
        },

        onAuthorityChange(row, event) {
          if (!this.isUserEvent(event)) return;
          const authorityId = row.supervisingAuthorityId || '';
          if (this.shouldBroadcast(row)) {
            this.broadcastToSelected((target) => {
              if (target.category !== 'non_party') return;
              target.supervisingAuthorityId = authorityId;
            });
          }
        },

        onPartyChange(row, event) {
          if (!this.isUserEvent(event)) return;
          const ids = (row.partyIds || []).map(String);
          if (this.shouldBroadcast(row)) {
            this.broadcastToSelected((target) => {
              if (target.category !== 'party') return;
              target.partyIds = ids.slice();
            });
          }
        },

        onTypeSelect(row, event) {
          if (!this.isUserEvent(event)) return;
          const typeSelect = row.typeSelect || '';
          if (typeSelect !== '__custom__') {
            row.customTypeName = '';
          }
          if (this.shouldBroadcast(row)) {
            this.broadcastToSelected((target) => {
              if (!target.category) return;
              target.typeSelect = typeSelect;
              target.customTypeName = typeSelect === '__custom__' ? (row.customTypeName || '') : '';
            });
          }
        },

        onCustomTypeNameChange(row) {
          if (row.typeSelect !== '__custom__') return;
          const value = row.customTypeName || '';
          if (this.shouldBroadcast(row)) {
            this.broadcastToSelected((target) => {
              if (target.typeSelect !== '__custom__') return;
              target.customTypeName = value;
            });
          }
        },

        applyCategory(row, category) {
          row.category = category;
          row.side = '';
          row.partyIds = [];
          row.supervisingAuthorityId = '';
          row.typeSelect = '';
          row.customTypeName = '';
          // 非当事人材料且只有一个主管机关时，自动选择
          if (category === 'non_party' && (this.supervisingAuthorities || []).length === 1) {
            row.supervisingAuthorityId = String(this.supervisingAuthorities[0].id);
          }
        },

        isRowSelected(row) {
          return (this.selectedIds || []).includes(String(row.attachmentId));
        },

        toggleRowSelected(row) {
          const id = String(row.attachmentId);
          const next = new Set((this.selectedIds || []).map(String));
          if (next.has(id)) {
            next.delete(id);
          } else {
            next.add(id);
          }
          this.selectedIds = Array.from(next);
        },

        toggleSelectAllFiltered() {
          const ids = (this.filteredRows || []).map((row) => String(row.attachmentId));
          const next = new Set((this.selectedIds || []).map(String));
          if (this.allFilteredSelected) {
            ids.forEach((id) => next.delete(id));
          } else {
            ids.forEach((id) => next.add(id));
          }
          this.selectedIds = Array.from(next);
        },

        shouldBroadcast(row) {
          return this.allFilteredSelected && this.isRowSelected(row);
        },

        broadcastToSelected(updater) {
          const selected = new Set((this.selectedIds || []).map(String));
          const scope = this.filteredRows || [];
          for (const target of scope) {
            if (!selected.has(String(target.attachmentId))) continue;
            updater(target);
          }
        },

        isRowUnfinished(row) {
          if (!row || !row.category) return true;
          if (row.category === 'party') {
            if (!row.side) return true;
          }
          if (row.category === 'non_party') {
            if (!row.supervisingAuthorityId) return true;
          }
          if (!row.typeSelect) return true;
          if (row.typeSelect === '__custom__' && !(row.customTypeName || '').trim()) return true;
          return false;
        },

        onFilterCategoryChange() {
          this.filterSide = '';
          this.filterAuthorityId = '';
        },

        resetFilters() {
          this.searchKeyword = '';
          this.filterCategory = this.defaultCategory || 'all';
          this.filterSide = '';
          this.filterAuthorityId = '';
          this.onlyUnfinished = false;
          this.onlyUnbound = false;
        },

        onFilePick(event) {
          const input = event && event.target ? event.target : null;
          const files = input && input.files ? Array.from(input.files) : [];
          this.pendingFiles = mergeFiles(this.pendingFiles, files);
          this.recentUploadedCount = 0;
          this.flashDropzone = true;
          window.setTimeout(() => {
            this.flashDropzone = false;
          }, 700);
          if (input) input.value = '';
        },

        openFilePicker() {
          const input = this.$refs.uploadFiles;
          if (input && typeof input.click === 'function') input.click();
        },

        onDragOver(event) {
          this.isDragging = true;
        },

        onDragLeave(event) {
          this.isDragging = false;
        },

        onDrop(event) {
          this.isDragging = false;
          const files = event && event.dataTransfer && event.dataTransfer.files ? Array.from(event.dataTransfer.files) : [];
          this.pendingFiles = mergeFiles(this.pendingFiles, files);
          this.recentUploadedCount = 0;
          this.flashDropzone = true;
          window.setTimeout(() => {
            this.flashDropzone = false;
          }, 700);
          const input = event && event.target ? event.target : null;
          if (input && 'value' in input) input.value = '';
        },

        removePending(index) {
          const next = Array.from(this.pendingFiles || []);
          next.splice(index, 1);
          this.pendingFiles = next;
        },

        load() {
          this.isLoading = true;
          return fetch(`/api/v1/cases/${this.caseId}/materials/bind-candidates`, {
            headers: { 'X-CSRFToken': getCsrfToken() },
          })
            .then((resp) => {
              if (!resp.ok) throw new Error('load failed');
              return resp.json();
            })
            .then((data) => {
              const uploadedSet = new Set(this.lastUploadedIds.map(String));
              const prefillMap = this.scanPrefillMap || {};
              const dc = this.defaultCategory;
              this.rows = (data || []).map((c) => {
                let prefill = prefillMap[String(c.attachment_id)] || null;
                if (!prefill && uploadedSet.has(String(c.attachment_id))) {
                  prefill = { category: dc || this.uploadCategory };
                }
                return normalizeCandidate(c, prefill, this.defaultCategory, this.supervisingAuthorities);
              });
              const existing = new Set((this.rows || []).map((row) => String(row.attachmentId)));
              this.selectedIds = (this.selectedIds || []).map(String).filter((id) => existing.has(id));
            })
            .catch(() => {
              this.showMessage('加载附件失败', 'error');
            })
            .finally(() => {
              this.isLoading = false;
            });
        },

        buildBindPayload() {
          const items = [];
          for (const row of this.rows) {
            if (!row.category) continue;
            if (!row.typeSelect) {
              throw new Error(`文件「${row.fileName}」未选择类型`);
            }
            if (row.typeSelect === '__custom__' && !(row.customTypeName || '').trim()) {
              throw new Error(`文件「${row.fileName}」自定义类型为空`);
            }
            if (row.category === 'party') {
              if (!row.side) throw new Error(`文件「${row.fileName}」未选择我方/对方`);
            }
            if (row.category === 'non_party') {
              if (!row.supervisingAuthorityId) throw new Error(`文件「${row.fileName}」未选择主管机关`);
            }
            const item = {
              attachment_id: row.attachmentId,
              category: row.category,
              side: row.category === 'party' ? row.side : null,
              party_ids: row.category === 'party' ? (row.partyIds || []).map((x) => parseInt(x, 10)) : [],
              supervising_authority_id: row.category === 'non_party' ? row.supervisingAuthorityId : null,
            };
            if (row.typeSelect === '__custom__') {
              item.type_id = null;
              item.type_name = (row.customTypeName || '').trim();
            } else {
              const typeId = parseInt(row.typeSelect, 10);
              const options = this.typeOptions(row);
              const found = options.find((t) => String(t.id) === String(typeId));
              item.type_id = typeId;
              item.type_name = found ? found.name : '';
            }
            items.push(item);
          }
          return { items };
        },

        async save() {
          if (this.isSaving) return;
          this.isSaving = true;

          try {
            await this.ensureScanPreparedForSave();
            let payload;
            try {
              payload = this.buildBindPayload();
            } catch (e) {
              throw new Error(e.message || '保存参数不完整');
            }

            if (!Array.isArray(payload.items) || !payload.items.length) {
              throw new Error('没有可保存的材料。请先扫描文件或上传附件。');
            }

            const resp = await fetch(`/api/v1/cases/${this.caseId}/materials/bind`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
              },
              body: JSON.stringify(payload),
            });
            if (!resp.ok) throw new Error('保存失败');
            const data = await resp.json();
            const count = (data && data.saved_count) || 0;
            this.showMessage(`已保存 ${count} 条材料分类，正在返回案件详情...`, 'success');
            this.lastUploadedIds = [];
            this.redirectToDetailAfterSave();
          } catch (err) {
            this.showMessage((err && err.message) || '保存失败', 'error');
          } finally {
            this.isSaving = false;
          }
        },

        upload() {
          if (this.isUploading) return;
          const files = Array.from(this.pendingFiles || []);
          if (!files.length) {
            this.showMessage('请选择要上传的文件', 'error');
            return;
          }
          this.isUploading = true;
          this.recentUploadedCount = 0;
          this.flashDropzone = false;
          const fd = new FormData();
          files.forEach((f) => fd.append('files', f));
          fetch(`/api/v1/cases/${this.caseId}/materials/upload`, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() },
            body: fd,
          })
            .then((resp) => {
              if (!resp.ok) throw new Error('upload failed');
              return resp.json();
            })
            .then((data) => {
              this.lastUploadedIds = (data && data.attachment_ids) || [];
              this.pendingFiles = [];
              this.recentUploadedCount = this.lastUploadedIds.length || files.length;
              this.showMessage('上传成功，正在刷新...', 'success');
              window.setTimeout(() => {
                window.location.reload();
              }, 600);
            })
            .catch(() => {
              this.showMessage('上传失败', 'error');
            })
            .finally(() => {
              this.isUploading = false;
            });
        },

      }, scanMethods);
    });
  });
})();
