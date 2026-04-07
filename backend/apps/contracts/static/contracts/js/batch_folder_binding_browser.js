/**
 * 批量绑定页面文件夹选择器组件
 * Finder 风格，用于选择根目录
 */
(function () {
  'use strict';

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

  window.contractBatchFolderSelectorApp = function contractBatchFolderSelectorApp() {
    return {
      showBrowser: false,
      loading: false,
      loadingColumn: null,
      columns: [],
      error: null,
      manualPath: '',
      pendingCard: null,

      openBrowser: function openBrowser(card) {
        this.pendingCard = card || window.__batchFolderSelectorCard;
        this.showBrowser = true;
        this.error = null;
        this.columns = [];
        this.manualPath = this.pendingCard && this.pendingCard.root_path ? this.pendingCard.root_path : '';
        this.loadRoots();
      },

      closeBrowser: function closeBrowser() {
        this.showBrowser = false;
        this.columns = [];
        this.error = null;
        this.manualPath = '';
        this.pendingCard = null;
        window.__batchFolderSelectorCard = null;
      },

      loadRoots: async function loadRoots() {
        this.loading = true;
        this.error = null;

        try {
          var response = await fetch('/api/v1/contracts/folder-browse', {
            method: 'GET',
            headers: {
              'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
          });

          if (!response.ok) {
            throw new Error('加载根目录失败');
          }

          var data = await response.json();

          if (!data.browsable) {
            this.error = data.message || '无法访问根目录';
            return;
          }

          this.columns = [{
            path: null,
            entries: data.entries || [],
            selectedIndex: -1
          }];
        } catch (error) {
          this.error = '加载根目录失败';
        } finally {
          this.loading = false;
        }
      },

      selectFolder: async function selectFolder(columnIndex, entryIndex, entry) {
        if (this.loadingColumn) return;

        if (this.columns[columnIndex].selectedIndex === entryIndex) {
          return;
        }

        this.columns[columnIndex].selectedIndex = entryIndex;

        var newLength = columnIndex + 1;
        if (this.columns.length > newLength) {
          this.columns.splice(newLength);
        }

        this.loadingColumn = entry.path;
        await this.loadSubfolders(entry.path);

        var self = this;
        this.$nextTick(function () {
          var container = self.$el.querySelector('.finder-columns');
          if (container) {
            container.scrollLeft = container.scrollWidth;
          }
        });
      },

      loadSubfolders: async function loadSubfolders(path) {
        this.loadingColumn = path;
        this.error = null;

        try {
          var response = await fetch('/api/v1/contracts/folder-browse?path=' + encodeURIComponent(path), {
            method: 'GET',
            headers: {
              'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
          });

          if (!response.ok) {
            throw new Error('加载文件夹失败');
          }

          var data = await response.json();

          if (!data.browsable) {
            this.error = data.message || '无法访问此路径';
            return;
          }

          if (data.entries && data.entries.length > 0) {
            this.columns.push({
              path: path,
              entries: data.entries,
              selectedIndex: -1
            });
          }

          this.manualPath = path;
        } catch (error) {
          this.error = '加载文件夹失败';
        } finally {
          this.loadingColumn = null;
        }
      },

      bindManualPath: async function bindManualPath() {
        if (!this.manualPath || !this.manualPath.trim()) {
          this.error = '请输入文件夹路径';
          return;
        }
        await this.selectFolderPath(this.manualPath.trim());
      },

      selectFolderPath: async function selectFolderPath(path) {
        if (this.pendingCard) {
          this.pendingCard.root_path = path;
        }
        this.closeBrowser();
      },

      getCurrentPath: function getCurrentPath() {
        for (var i = this.columns.length - 1; i >= 0; i--) {
          var col = this.columns[i];
          if (col.selectedIndex >= 0 && col.entries[col.selectedIndex]) {
            return col.entries[col.selectedIndex].path;
          }
        }
        return null;
      },

      bindCurrentPath: async function bindCurrentPath() {
        var path = this.getCurrentPath();
        if (!path) {
          this.error = '请选择一个文件夹';
          return;
        }
        await this.selectFolderPath(path);
      },

      navigateUp: async function navigateUp() {
        var currentPath = this.getCurrentPath();
        if (!currentPath) return;

        var lastSepIndex = Math.max(currentPath.lastIndexOf('/'), currentPath.lastIndexOf('\\'));
        if (lastSepIndex <= 0) return;

        var parentPath = currentPath.substring(0, lastSepIndex);
        this.loading = true;
        this.error = null;
        this.columns = [];

        try {
          var response = await fetch('/api/v1/contracts/folder-browse?path=' + encodeURIComponent(parentPath), {
            method: 'GET',
            headers: {
              'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
          });

          if (!response.ok) {
            throw new Error('加载文件夹失败');
          }

          var data = await response.json();

          if (!data.browsable) {
            this.error = data.message || '无法访问此路径';
            return;
          }

          this.columns = [{
            path: parentPath,
            entries: data.entries || [],
            selectedIndex: -1
          }];
          this.manualPath = parentPath;

          if (data.parent_path) {
            this.columns.unshift({
              path: null,
              entries: [{name: '..', path: data.parent_path}],
              selectedIndex: 0
            });
          }
        } catch (error) {
          this.error = '加载文件夹失败';
        } finally {
          this.loading = false;
        }
      }
    };
  };
})();
