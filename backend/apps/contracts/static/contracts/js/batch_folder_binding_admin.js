(function () {
  'use strict';

  function parseScriptJson(id) {
    var node = document.getElementById(id);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent || '{}');
    } catch (error) {
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

  window.contractBatchFolderBindingApp = function contractBatchFolderBindingApp() {
    return {
      cards: [],
      config: {},
      isPreviewing: false,
      isSaving: false,
      isOpening: false,
      message: { level: '', text: '' },

      init: function init() {
        var initialCards = parseScriptJson('batch-folder-binding-cards') || [];
        this.cards = (initialCards || []).map(function (card) {
          return Object.assign(
            {
              error: '',
              options: [],
              rows: [],
              root_path: '',
            },
            card || {}
          );
        });
        this.config = parseScriptJson('batch-folder-binding-config') || {};
      },

      goBack: function goBack() {
        window.location.href = this.config.changeListUrl || '/admin/contracts/contract/';
      },

      setMessage: function setMessage(level, text) {
        this.message = { level: level, text: text || '' };
      },

      totalUnboundCount: function totalUnboundCount() {
        return (this.cards || []).reduce(function (sum, card) {
          return sum + Number(card.unbound_count || 0);
        }, 0);
      },

      configuredRootCount: function configuredRootCount() {
        return (this.cards || []).reduce(function (sum, card) {
          return sum + ((card.root_path || '').trim() ? 1 : 0);
        }, 0);
      },

      selectedApplyCount: function selectedApplyCount() {
        return (this.cards || []).reduce(function (sum, card) {
          return (
            sum +
            (card.rows || []).reduce(function (inner, row) {
              return inner + (row.apply && row.selected_folder_path ? 1 : 0);
            }, 0)
          );
        }, 0);
      },

      selectedRowsCount: function selectedRowsCount(card) {
        return (card.rows || []).reduce(function (sum, row) {
          return sum + (row.apply && row.selected_folder_path ? 1 : 0);
        }, 0);
      },

      formatConfidence: function formatConfidence(value) {
        var num = Number(value || 0);
        if (!Number.isFinite(num)) return '0.00';
        return num.toFixed(2);
      },

      confidenceClass: function confidenceClass(value) {
        var num = Number(value || 0);
        if (!Number.isFinite(num)) return 'is-low';
        if (num >= 0.85) return 'is-high';
        if (num >= 0.7) return 'is-medium';
        return 'is-low';
      },

      onSelectFolder: function onSelectFolder(row) {
        row.apply = !!row.selected_folder_path;
      },

      buildCaseTypePayload: function buildCaseTypePayload(cards) {
        return (cards || []).map(function (card) {
          return {
            case_type: card.case_type,
            root_path: (card.root_path || '').trim(),
          };
        });
      },

      previewAll: async function previewAll() {
        if (!this.cards.length) return;
        await this.submitPreview(this.cards);
      },

      previewSingle: async function previewSingle(card) {
        await this.submitPreview([card]);
      },

      submitPreview: async function submitPreview(targetCards) {
        if (!targetCards || !targetCards.length) return;
        this.isPreviewing = true;
        this.setMessage('', '');

        try {
          var response = await fetch(this.config.previewUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify({
              case_type_roots: this.buildCaseTypePayload(targetCards),
            }),
          });
          var data = await response.json().catch(function () {
            return {};
          });
          if (!response.ok || !data.success) throw new Error(data.message || '预览失败');

          var resultMap = {};
          (data.items || []).forEach(function (item) {
            resultMap[item.case_type] = item;
          });

          this.cards.forEach(function (card) {
            var result = resultMap[card.case_type];
            if (!result) return;
            card.error = result.error || '';
            card.options = result.options || [];
            card.rows = result.rows || [];
          });

          this.setMessage('success', '匹配完成，可按需调整后保存。');
        } catch (error) {
          this.setMessage('error', error && error.message ? error.message : '预览失败');
        } finally {
          this.isPreviewing = false;
        }
      },

      openFolder: async function openFolder(card, row) {
        if (!card || !row || !row.selected_folder_path) return;
        this.isOpening = true;
        this.setMessage('', '');

        try {
          var response = await fetch(this.config.openFolderUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify({
              root_path: (card.root_path || '').trim(),
              folder_path: row.selected_folder_path,
            }),
          });
          var data = await response.json().catch(function () {
            return {};
          });
          if (!response.ok || !data.success) throw new Error(data.message || '打开失败');
          this.setMessage('success', data.message || '已打开文件夹。');
        } catch (error) {
          this.setMessage('error', error && error.message ? error.message : '打开失败');
        } finally {
          this.isOpening = false;
        }
      },

      saveAll: async function saveAll() {
        if (!this.cards.length) return;
        this.isSaving = true;
        this.setMessage('', '');

        var selections = [];
        this.cards.forEach(function (card) {
          (card.rows || []).forEach(function (row) {
            selections.push({
              contract_id: row.contract_id,
              case_type: card.case_type,
              selected_folder_path: row.selected_folder_path || '',
              apply: !!row.apply,
            });
          });
        });

        try {
          var response = await fetch(this.config.saveUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify({
              case_type_roots: this.buildCaseTypePayload(this.cards),
              contract_selections: selections,
            }),
          });
          var data = await response.json().catch(function () {
            return {};
          });
          if (!response.ok || !data.success) throw new Error(data.message || '保存失败');

          var summary = '已绑定 ' + (data.bound_count || 0) + ' 条，跳过 ' + (data.skipped_count || 0) + ' 条。';
          if (data.error_count) {
            summary += ' 失败 ' + data.error_count + ' 条。';
          }
          this.setMessage('success', summary);
          if ((data.bound_count || 0) > 0) {
            window.setTimeout(function () {
              window.location.reload();
            }, 900);
          }
        } catch (error) {
          this.setMessage('error', error && error.message ? error.message : '保存失败');
        } finally {
          this.isSaving = false;
        }
      },
    };
  };
})();
