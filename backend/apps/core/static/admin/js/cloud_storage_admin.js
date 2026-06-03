/**
 * CloudStorageAccount admin — show/hide fieldsets based on storage_type.
 * Uses plain JS since Alpine.js requires x-data on a parent element
 * that the Django admin fieldset rendering doesn't easily provide.
 */
document.addEventListener('DOMContentLoaded', function () {
  var typeSelect = document.getElementById('id_storage_type');
  if (!typeSelect) return;

  var sectionMap = {
    local: 'local-section',
    webdav: 'webdav-section',
    onedrive: 'onedrive-section',
  };

  function toggle() {
    var val = typeSelect.value;
    Object.entries(sectionMap).forEach(function (entry) {
      var key = entry[0];
      var cls = entry[1];
      var fieldset = document.querySelector('.' + cls);
      if (fieldset) {
        // Django wraps fieldset content in a <div class="collapse">
        var wrapper = fieldset.closest('.grp-group') || fieldset.closest('fieldset');
        if (wrapper) {
          wrapper.style.display = key === val ? '' : 'none';
        } else {
          fieldset.style.display = key === val ? '' : 'none';
        }
      }
    });
  }

  typeSelect.addEventListener('change', toggle);
  toggle();
});
