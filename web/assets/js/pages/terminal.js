/* Terminal page: xterm.js over WebSocket <-> SSH bridge */
PP.pages = PP.pages || {};
PP.pages.terminal = {
  data: () => ({
    username: 'root', password: '', cols: 100, rows: 30,
    connected: false, error: '', ws: null, term: null,
  }),
  methods: {
    async connect() {
      if (!window.Terminal) {
        this.error = 'xterm.js tidak termuat (butuh internet / jalankan scripts/vendor_assets.sh).';
        return;
      }
      this.error = '';
      const shell = this.$refs.shell;
      shell.innerHTML = '';
      const term = new window.Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: '"JetBrains Mono", Consolas, monospace',
        theme: { background: '#0a0f1a' },
      });
      this.term = term;
      try {
        const fit = window.FitAddon && new window.FitAddon.FitAddon();
        if (fit) { term.loadAddon(fit); term.open(shell); fit.fit(); this.cols = term.cols; this.rows = term.rows; }
        else term.open(shell);
      } catch (e) {
        term.open(shell);
      }

      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(proto + '://' + location.host + '/api/terminal/ws');
      this.ws = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({
          username: this.username,
          password: this.password,
          cols: this.cols,
          rows: this.rows,
        }));
        term.onData(data => {
          if (ws.readyState === 1) ws.send(JSON.stringify({ data }));
        });
        term.onResize(({ cols, rows }) => {
          if (ws.readyState === 1) ws.send(JSON.stringify({ resize: { cols, rows } }));
        });
        this.connected = true;
        this.password = '';
      };
      ws.onmessage = (ev) => {
        if (typeof ev.data === 'string' && ev.data.startsWith('{')) {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.error) { this.error = msg.error; this.cleanup(); return; }
          } catch (e) { /* binary-ish */ }
        }
        term.write(typeof ev.data === 'string' ? ev.data : new TextDecoder().decode(ev.data));
      };
      ws.onclose = () => { this.connected = false; };
      ws.onerror = () => { this.error = 'WebSocket error'; };
    },
    cleanup() {
      if (this.ws) { try { this.ws.close(); } catch (e) {} this.ws = null; }
      this.connected = false;
    },
  },
  unmounted() { this.cleanup(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.terminal') }}</h1>
      <span class="badge" :class="connected ? 'green' : 'gray'">{{ connected ? 'connected' : 'disconnected' }}</span>
      <span class="spacer"></span>
    </div>

    <div class="card mb" v-if="!connected">
      <div class="form-row">
        <div class="field"><label>SSH {{ PP.t('common.username') }}</label>
          <input class="input mono" v-model="username"></div>
        <div class="field"><label>{{ PP.t('common.password') }}</label>
          <input class="input mono" type="password" v-model="password" @keyup.enter="connect"></div>
        <div class="field"><label>&nbsp;</label>
          <button class="btn primary" @click="connect">⏎ connect</button></div>
      </div>
      <div class="small faint">SSH ke 127.0.0.1 — kredensial tidak disimpan, hanya dipakai sekali untuk login SSH.</div>
      <div class="text-danger small mt" v-if="error">{{ error }}</div>
    </div>

    <div class="terminal-shell" ref="shell"></div>
    <div class="mt">
      <button class="btn danger small" v-if="connected" @click="cleanup">⏏ disconnect</button>
    </div>
  </div>`,
};
