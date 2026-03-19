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

  function formatTime(value) {
    const t = Date.parse(value);
    if (!Number.isFinite(t)) return '';
    const d = new Date(t);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function normalizeCandidate(candidate, prefill) {
    const material = candidate.material || null;
    const draft = prefill || {};
    const row = {
      attachmentId: candidate.attachment_id,
      fileName: candidate.file_name,
      fileUrl: candidate.file_url,
      uploadedAt: candidate.uploaded_at,
      uploadedAtDisplay: formatTime(candidate.uploaded_at),
      isBound: Boolean(material),
      materialId: material ? material.id : null,
      category: material ? material.category : (draft.category || ''),
      lastCategory: material ? material.category : (draft.category || ''),
      side: material ? (material.side || '') : (draft.side || ''),
      partyIds: material ? (material.party_ids || []).map(String) : [],
      supervisingAuthorityId: material ? (material.supervising_authority_id || '') : '',
      typeSelect: material && material.type_id ? String(material.type_id) : '',
      customTypeName: material && !material.type_id ? (material.type_name || '') : (draft.type_name_hint || ''),
    };
    if (!row.typeSelect && row.customTypeName) row.typeSelect = '__custom__';
    return row;
  }

  function readQueryValue(name) {
    try {
      const url = new URL(window.location.href);
      return url.searchParams.get(name) || '';
    } catch (_) {
      return '';
    }
  }

  function mergeFiles(existing, incoming) {
    const seen = new Set();
    const all = [];
    const push = (f) => {
      if (!f) return;
      const key = `${f.name || ''}__${String(f.size || 0)}__${String(f.lastModified || 0)}`;
      if (seen.has(key)) return;
      seen.add(key);
      all.push(f);
    };
    (existing || []).forEach(push);
    (incoming || []).forEach(push);
    return all;
  }

  document.addEventListener('alpine:init', function () {
    Alpine.data('caseMaterialsManageApp', function (config) {
      return {
        caseId: config.caseId,
        partyTypes: config.partyTypes || [],
        nonPartyTypes: config.nonPartyTypes || [],
        ourParties: config.ourParties || [],
        opponentParties: config.opponentParties || [],
        supervisingAuthorities: config.supervisingAuthorities || [],

        rows: [],
        isLoading: false,
        isUploading: false,
        isDragging: false,
        flashDropzone: false,
        recentUploadedCount: 0,
        message: '',
        messageType: 'success',
        uploadCategory: 'party',
        lastUploadedIds: [],
        pendingFiles: [],
        searchKeyword: '',
        filterCategory: 'unclassified',
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
        scanStatusMessage: '',
        scanErrorMessage: '',

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
          if (n) return '点击右侧“上传”开始上传，或继续拖拽追加文件';
          return '';
        },

        get selectedScanCount() {
          return (this.scanCandidates || []).filter((item) => item.selected).length;
        },

        get scanStatusText() {
          if (this.scanStatusMessage) return this.scanStatusMessage;
          if (this.scanErrorMessage) return this.scanErrorMessage;
          if (this.scanStatus === 'running') return this.scanTexts.scanningFolder || '正在扫描文件夹';
          if (this.scanStatus === 'classifying') return this.scanTexts.classifying || '正在 AI 分类';
          if (this.scanStatus === 'completed' || this.scanStatus === 'staged') return this.scanTexts.completed || '扫描完成';
          if (this.scanStatus === 'failed') return this.scanTexts.failed || '扫描失败';
          return '';
        },

        get scanStatusClass() {
          if (this.scanStatus === 'failed') return 'is-error';
          if (this.scanStatus === 'completed' || this.scanStatus === 'staged') return 'is-success';
          return 'is-pending';
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
          this.load();
          if (this.scanSessionId) {
            this.fetchScanStatus(this.scanSessionId, true);
          }
        },

        showMessage(message, type) {
          this.message = message;
          this.messageType = type || 'success';
          window.setTimeout(() => {
            this.message = '';
          }, 4000);
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
          const category = row.category || '';
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
          this.filterCategory = 'all';
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
          fetch(`/api/v1/cases/${this.caseId}/materials/bind-candidates`, {
            headers: { 'X-CSRFToken': getCsrfToken() },
          })
            .then((resp) => {
              if (!resp.ok) throw new Error('load failed');
              return resp.json();
            })
            .then((data) => {
              const uploadedSet = new Set(this.lastUploadedIds.map(String));
              const prefillMap = this.scanPrefillMap || {};
              this.rows = (data || []).map((c) => {
                let prefill = prefillMap[String(c.attachment_id)] || null;
                if (!prefill && uploadedSet.has(String(c.attachment_id))) {
                  prefill = { category: this.uploadCategory };
                }
                return normalizeCandidate(c, prefill);
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

        clearScanPollTimer() {
          if (!this.scanPollTimer) return;
          window.clearTimeout(this.scanPollTimer);
          this.scanPollTimer = null;
        },

        startFolderScan(rescan) {
          this.scanPanelVisible = true;
          this.scanErrorMessage = '';
          this.scanStatusMessage = '';
          this.isScanning = true;
          this.clearScanPollTimer();
          fetch(`/api/v1/cases/${this.caseId}/folder-scan`, {
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
          return (candidates || []).map((candidate) => {
            const category = ['party', 'non_party'].includes(candidate.suggested_category) ? candidate.suggested_category : '';
            const side = category === 'party' && ['our', 'opponent'].includes(candidate.suggested_side) ? candidate.suggested_side : '';
            return {
              source_path: candidate.source_path,
              filename: candidate.filename,
              selected: candidate.selected !== false,
              category: category,
              side: side,
              type_name_hint: candidate.type_name_hint || '',
              reason: candidate.reason || '',
            };
          });
        },

        stageSelectedScanCandidates() {
          if (this.isStaging || !this.scanSessionId) return;
          const items = (this.scanCandidates || [])
            .filter((candidate) => candidate.selected)
            .map((candidate) => ({
              source_path: candidate.source_path,
              selected: true,
              category: candidate.category || 'unknown',
              side: candidate.side || 'unknown',
              type_name_hint: candidate.type_name_hint || '',
            }));

          if (!items.length) {
            this.showMessage(this.scanTexts.noPdf || '未找到可导入的 PDF', 'error');
            return;
          }

          this.isStaging = true;
          fetch(`/api/v1/cases/${this.caseId}/folder-scan/${this.scanSessionId}/stage`, {
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
                throw new Error(data.message || data.detail || this.scanTexts.importFailed || '导入失败，请稍后重试');
              }
              return data;
            })
            .then((data) => {
              this.scanStatus = (data && data.status) || 'staged';
              this.scanSessionId = (data && data.session_id) || this.scanSessionId;
              this.scanPrefillMap = (data && data.prefill_map) || {};
              this.prefillAppliedSessionId = this.scanSessionId;
              this.lastUploadedIds = (data && data.attachment_ids) || [];

              if (data && data.materials_url) {
                window.history.replaceState({}, '', data.materials_url);
              } else {
                this.syncScanSessionToUrl(this.scanSessionId);
              }

              this.showMessage('导入附件成功，请完善分类后保存', 'success');
              this.load();
            })
            .catch((err) => {
              this.showMessage((err && err.message) || (this.scanTexts.importFailed || '导入失败，请稍后重试'), 'error');
            })
            .finally(() => {
              this.isStaging = false;
            });
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
            window.history.replaceState({}, '', url.toString());
          } catch (_) {
          }
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

        save() {
          let payload;
          try {
            payload = this.buildBindPayload();
          } catch (e) {
            this.showMessage(e.message || '保存参数不完整', 'error');
            return;
          }
          fetch(`/api/v1/cases/${this.caseId}/materials/bind`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify(payload),
          })
            .then((resp) => {
              if (!resp.ok) throw new Error('save failed');
              return resp.json();
            })
            .then((data) => {
              const count = (data && data.saved_count) || 0;
              this.showMessage(`已保存 ${count} 条材料分类`, 'success');
              this.lastUploadedIds = [];
              this.load();
            })
            .catch(() => {
              this.showMessage('保存失败', 'error');
            });
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
              this.showMessage('上传成功，请完善分类后保存', 'success');
              this.load();
              window.setTimeout(() => {
                this.recentUploadedCount = 0;
              }, 4500);
            })
            .catch(() => {
              this.showMessage('上传失败', 'error');
            })
            .finally(() => {
              this.isUploading = false;
            });
        },
      };
    });
  });
})();
