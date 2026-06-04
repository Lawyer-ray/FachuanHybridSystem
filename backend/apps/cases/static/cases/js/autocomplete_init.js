(function () {
    'use strict';

    function initAll() {
        if (typeof window.initCauseAutocomplete !== 'function' || typeof window.initCourtAutocomplete !== 'function') {
            return;
        }

        const caseTypeSelector = '#id_case_type';

        document.querySelectorAll('input.js-cause-autocomplete').forEach((el) => {
            if (!el.id) return;
            if (el.closest('.autocomplete-container')) return;
            if (el.dataset.autocompleteInitialized) return;  // 已初始化，跳过
            el.dataset.autocompleteInitialized = 'true';
            window.initCauseAutocomplete(`#${el.id}`, caseTypeSelector);
        });

        document.querySelectorAll('input.js-court-autocomplete').forEach((el) => {
            if (!el.id) return;
            if (el.closest('.autocomplete-container')) return;
            if (el.dataset.autocompleteInitialized) return;  // 已初始化，跳过
            el.dataset.autocompleteInitialized = 'true';
            window.initCourtAutocomplete(`#${el.id}`);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }

    document.addEventListener('formset:added', function () {
        initAll();
    });
})();
