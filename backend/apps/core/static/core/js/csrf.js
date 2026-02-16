(function (global) {
  function getCSRFToken() {
    var tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tokenElement && tokenElement.value) return tokenElement.value;
    var metaToken = document.querySelector('meta[name="csrf-token"]');
    if (metaToken && metaToken.content) return metaToken.content;
    var cookies = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < cookies.length; i++) {
      var trimmed = cookies[i].trim();
      if (trimmed.indexOf('csrftoken=') === 0) {
        return decodeURIComponent(trimmed.substring('csrftoken='.length));
      }
    }
    return '';
  }

  function csrfFetch(url, options) {
    var opts = options || {};
    var method = String((opts.method || 'GET')).toUpperCase();
    var headers = opts.headers || {};
    var isSafe = method === 'GET' || method === 'HEAD' || method === 'OPTIONS' || method === 'TRACE';
    if (!isSafe) {
      if (typeof Headers !== 'undefined' && headers instanceof Headers) {
        if (!headers.has('X-CSRFToken')) headers.set('X-CSRFToken', getCSRFToken());
      } else {
        if (!headers['X-CSRFToken']) headers['X-CSRFToken'] = getCSRFToken();
      }
    }
    opts.headers = headers;
    return fetch(url, opts);
  }

  global.FachuanCSRF = {
    getToken: getCSRFToken,
    fetch: csrfFetch,
  };
})(window);
