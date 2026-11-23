/* PanelPro API client — thin fetch wrapper around /api/*.
   All responses use { ok, data, message }. */
(function () {
  async function request(path, opts = {}) {
    const method = opts.method || 'GET';
    let url = '/api/' + path;
    if (opts.params) {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(opts.params)) {
        if (v !== undefined && v !== null && v !== '') qs.set(k, v);
      }
      const s = qs.toString();
      if (s) url += '?' + s;
    }
    const headers = {};
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
      headers['X-PP-Request'] = '1';
    }
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json';

    const res = await fetch(url, {
      method,
      headers,
      credentials: 'same-origin',
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });

    let payload = null;
    try { payload = await res.json(); } catch (e) { /* empty body */ }

    if (res.status === 401 && PP.store) PP.store.authed = false;
    if (!res.ok || !payload || payload.ok === false) {
      const err = new Error((payload && payload.message) || ('HTTP ' + res.status));
      err.status = res.status;
      throw err;
    }
    return payload.data;
  }

  async function upload(path, formData) {
    const res = await fetch('/api/' + path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-PP-Request': '1' },
      body: formData,
    });
    const payload = await res.json().catch(() => null);
    if (!res.ok || !payload || payload.ok === false) {
      throw new Error((payload && payload.message) || 'Upload failed');
    }
    return payload.data;
  }

  PP.api = request;
  PP.upload = upload;
})();
