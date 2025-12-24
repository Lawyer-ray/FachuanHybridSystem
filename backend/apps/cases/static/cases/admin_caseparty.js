document.addEventListener("DOMContentLoaded", function () {
  function updateRow(row) {
    var select =
      row.querySelector("select[id$='-client']") ||
      row.querySelector("input[id$='-client']") ||
      row.querySelector("select[name$='-client']") ||
      row.querySelector("input[name$='-client']");
    var displayCell = row.querySelector("td.field-is_our_client_display");
    if (!select || !displayCell) return;
    var cid = select.value;
    if (!cid) {
      displayCell.innerHTML = '<img src="/static/admin/img/icon-unknown.svg" alt="Unknown">';
      return;
    }
    fetch("/admin/cases/caseparty/is-our-client/" + cid + "/")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        displayCell.innerHTML = d.is_our_client
          ? '<img src="/static/admin/img/icon-yes.svg" alt="True">'
          : '<img src="/static/admin/img/icon-no.svg" alt="False">';
      })
      .catch(function () {
        displayCell.innerHTML = '<img src="/static/admin/img/icon-unknown.svg" alt="Unknown">';
      });
  }

  function initAll() {
    var rows = document.querySelectorAll("tr.dynamic-caseparty_set");
    rows.forEach(updateRow);
  }

  initAll();

  document.body.addEventListener("change", function (e) {
    var target = e.target;
    if (target && target.matches("select[id$='-client']")) {
      var row = target.closest("tr");
      if (row) updateRow(row);
    }
  });
});