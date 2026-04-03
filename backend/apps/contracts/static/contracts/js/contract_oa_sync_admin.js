(function () {
  'use strict';

  function parseScriptJson(id) {
    var node = document.getElementById(id);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent || 'null');
    } catch (_error) {
      return null;
    }
  }

  function getCsrfToken() {
    var tokenField = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tokenField && tokenField.value) return tokenField.value;

    var cookies = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < cookies.length; i++) {
      var cookie = cookies[i].trim();
      if (cookie.indexOf('csrftoken=') === 0) return cookie.substring('csrftoken='.length);
    }
    return '';
  }

  window.contractOaSyncApp = function contractOaSyncApp() {
    return {
      config: {},
      missingContracts: [],
      message: { level: '', text: '' },
      sessionId: null,
      isRunning: false,
      isSaving: false,
      pollTimer: null,
      progressMessage: '',
      totalCount: 0,
      processedCount: 0,
      matchedCount: 0,
      multipleCount: 0,
      notFoundCount: 0,
      errorCount: 0,
      resultItems: [],
      selectedCandidateKeys: {},

      init: function init() {
        var initialContracts = parseScriptJson('oa-sync-initial-contracts') || [];
        this.replaceMissingContracts(initialContracts);
        this.config = parseScriptJson('oa-sync-config') || {};
      },

      normalizeMissingContract: function normalizeMissingContract(item) {
        return {
          id: Number(item.id),
          name: item.name || '',
          law_firm_oa_case_number: item.law_firm_oa_case_number || '',
          law_firm_oa_url: item.law_firm_oa_url || '',
        };
      },

      replaceMissingContracts: function replaceMissingContracts(items) {
        var self = this;
        this.missingContracts = (items || []).map(function (item) {
          return self.normalizeMissingContract(item);
        });
      },

      goBack: function goBack() {
        window.location.href = this.config.changeListUrl || '/admin/contracts/contract/';
      },

      setMessage: function setMessage(level, text) {
        this.message = { level: level || '', text: text || '' };
      },

      statusText: function statusText(status) {
        if (status === 'matched') return '唯一候选(待确认)';
        if (status === 'multiple') return '多结果';
        if (status === 'not_found') return '未匹配';
        if (status === 'error') return '错误';
        return status || '-';
      },

      resultForContract: function resultForContract(contractId) {
        var targetId = Number(contractId);
        for (var i = 0; i < this.resultItems.length; i++) {
          var item = this.resultItems[i];
          if (Number(item.contract_id) === targetId) return item;
        }
        return null;
      },

      selectedCandidateKey: function selectedCandidateKey(contractId) {
        return this.selectedCandidateKeys[String(contractId)] || '';
      },

      buildCandidateKey: function buildCandidateKey(candidate) {
        return [candidate.case_no || '', candidate.keyid || '', candidate.detail_url || ''].join('|');
      },

      isCandidateSelected: function isCandidateSelected(contractId, candidate) {
        return this.selectedCandidateKey(contractId) === this.buildCandidateKey(candidate);
      },

      applyCandidate: function applyCandidate(contractId, candidate) {
        var targetId = Number(contractId);
        var nextCaseNumber = (candidate.case_no || '').trim();
        var nextUrl = (candidate.detail_url || '').trim();
        var nextKey = this.buildCandidateKey(candidate);

        this.missingContracts = this.missingContracts.map(function (item) {
          if (Number(item.id) !== targetId) {
            return item;
          }
          return {
            id: item.id,
            name: item.name,
            law_firm_oa_case_number: nextCaseNumber,
            law_firm_oa_url: nextUrl,
          };
        });
        this.selectedCandidateKeys[String(targetId)] = nextKey;
        this.setMessage('success', '已回填候选结果，请检查后点击“保存手动修改”');
      },

      saveManualChanges: async function saveManualChanges() {
        if (this.isSaving || this.isRunning || !this.missingContracts.length) return;
        this.setMessage('', '');
        this.isSaving = true;

        try {
          var entries = this.missingContracts.map(function (item) {
            return {
              id: Number(item.id),
              law_firm_oa_case_number: (item.law_firm_oa_case_number || '').trim(),
              law_firm_oa_url: (item.law_firm_oa_url || '').trim(),
            };
          });

          var response = await fetch(this.config.saveUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify({ entries: entries }),
          });

          var data = await response.json().catch(function () { return {}; });
          if (!response.ok || !data.success) {
            throw new Error(data.message || '保存失败');
          }

          this.replaceMissingContracts(Array.isArray(data.remaining_contracts) ? data.remaining_contracts : []);
          if (Array.isArray(data.errors) && data.errors.length) {
            var firstError = data.errors[0] || {};
            var suffix = firstError.message ? ('：' + firstError.message) : '';
            this.setMessage('error', (data.message || '部分保存成功') + suffix);
          } else {
            this.setMessage('success', data.message || '保存成功');
          }
        } catch (error) {
          this.setMessage('error', error && error.message ? error.message : '保存失败');
        } finally {
          this.isSaving = false;
        }
      },

      startSync: async function startSync() {
        if (this.isRunning || this.isSaving || !this.missingContracts.length) return;
        this.setMessage('', '');
        this.isRunning = true;

        try {
          var response = await fetch(this.config.startUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify({}),
          });

          var data = await response.json().catch(function () { return {}; });
          if (!response.ok || !data.success) {
            throw new Error(data.message || '启动失败');
          }

          this.sessionId = data.session_id;
          this.setMessage('success', data.message || '已开始同步');
          this.pollStatus();
        } catch (error) {
          this.isRunning = false;
          this.setMessage('error', error && error.message ? error.message : '启动失败');
        }
      },

      pollStatus: async function pollStatus() {
        var self = this;
        if (!this.sessionId) return;

        var doPoll = async function () {
          try {
            var response = await fetch(self.config.statusUrl.replace('__SESSION_ID__', String(self.sessionId)), {
              method: 'GET',
              credentials: 'same-origin',
            });
            var data = await response.json().catch(function () { return {}; });
            if (!response.ok || !data.success) {
              throw new Error(data.message || '状态查询失败');
            }

            self.progressMessage = data.progress_message || '';
            self.totalCount = Number(data.total_count || 0);
            self.processedCount = Number(data.processed_count || 0);
            self.matchedCount = Number(data.matched_count || 0);
            self.multipleCount = Number(data.multiple_count || 0);
            self.notFoundCount = Number(data.not_found_count || 0);
            self.errorCount = Number(data.error_count || 0);
            self.resultItems = data.items || [];
            if (Array.isArray(data.remaining_contracts)) {
              self.replaceMissingContracts(data.remaining_contracts);
            }

            if (data.status === 'completed') {
              self.isRunning = false;
              self.setMessage(
                'success',
                (Number(data.matched_count || 0) + Number(data.multiple_count || 0)) > 0
                  ? '同步完成，请直接在当前表格中确认候选后再保存'
                  : '同步完成'
              );
              window.clearInterval(self.pollTimer);
              self.pollTimer = null;
              return;
            }
            if (data.status === 'failed') {
              self.isRunning = false;
              self.setMessage('error', data.error_message || '同步失败');
              window.clearInterval(self.pollTimer);
              self.pollTimer = null;
              return;
            }
          } catch (error) {
            self.isRunning = false;
            self.setMessage('error', error && error.message ? error.message : '状态查询失败');
            window.clearInterval(self.pollTimer);
            self.pollTimer = null;
          }
        };

        await doPoll();
        if (this.pollTimer) return;
        this.pollTimer = window.setInterval(doPoll, 2000);
      },
    };
  };
})();
