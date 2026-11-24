/* Fleet: manage multiple PanelPro servers from one master panel (admin) */
PP.pages = PP.pages || {};
PP.pages.fleet = {
  data: () => ({
    servers: [], nodes: [],
    form: { open: false, id: null, name: '', base_url: '', entry_path: '', api_key: '', enabled: true },
    busy: false,
  }),
  methods: {
    async load() {
      try {
        const data = await PP.api('fleet');
        this.servers = data.servers;
        const ov = await PP.api('fleet/overview');
        this.nodes = ov.nodes;
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    openForm(row) {
      this.form = row
        ? { open: true, id: row.id, name: row.name, base_url: row.base_url,
            entry_path: row.entry_path, api_key: '', enabled: row.enabled }
        : { open: true, id: null, name: '', base_url: '', entry_path: '', api_key: '', enabled: true };
    },
    async save() {
      const f = this.form;
      if (!f.name || !f.base_url) return;
      try {
        await PP.api('fleet' + (f.id ? '/' + f.id + '/update' : ''), { method: 'POST', body: { ...f } });
        this.form.open = false;
        PP.ui.success(PP.t('common.save'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async test(row) {
      this.busy = true;
      try {
        const res = await PP.api('fleet/' + row.id + '/test', { method: 'POST' });
        PP.ui.success(PP.t('fleet.testOk'), 'v' + res.version + ' · ' + res.latency_ms + 'ms');
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.busy = false;
    },
    async del(row) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), row.name);
      if (!ok) return;
      try { await PP.api('fleet/' + row.id + '/delete', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    nodeOf(row) { return this.nodes.find(n => n.id === row.id) || {}; },
    pct(used, total) {
      return used && total ? Math.round(used / total * 100) : 0;
    },
    fmtBytes(n) {
      if (!n) return '0';
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let i = 0, v = n;
      while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
      return v.toFixed(1) + ' ' + units[i];
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.fleet') }}</h1>
      <span class="spacer"></span>
      <button class="btn primary" @click="openForm(null)">+ {{ PP.t('fleet.add') }}</button>
    </div>
    <p class="small">{{ PP.t('fleet.desc') }}</p>

    <div class="grid cols-2 mb">
      <div class="card" v-for="s in servers" :key="s.id">
        <div class="flex">
          <h3 style="margin:0">{{ s.name }}</h3>
          <span class="spacer"></span>
          <span class="badge" :class="nodeOf(s).state === 'up' ? 'green' : 'red'">
            {{ nodeOf(s).state || '?' }}</span>
        </div>
        <p class="mono small">{{ s.base_url }} <span class="badge gray" v-if="s.version">v{{ s.version }}</span></p>
        <div v-if="nodeOf(s).monitor">
          <p class="small">CPU {{ nodeOf(s).monitor.cpu }}%</p>
          <p-progress :value="pct(nodeOf(s).monitor.cpu, 100)"></p-progress>
          <p class="small">MEM {{ pct(nodeOf(s).monitor.mem_used, nodeOf(s).monitor.mem_total) }}%</p>
          <p-progress :value="pct(nodeOf(s).monitor.mem_used, nodeOf(s).monitor.mem_total)"></p-progress>
        </div>
        <p class="small" v-if="nodeOf(s).error" style="color:var(--red)">{{ nodeOf(s).error }}</p>
        <div class="flex mt">
          <button class="btn small" @click="test(s)" :disabled="busy">⚡ {{ PP.t('fleet.test') }}</button>
          <button class="btn small" @click="openForm(s)">✎</button>
          <button class="btn small danger" @click="del(s)">🗑</button>
        </div>
      </div>
    </div>

    <p-modal :open="form.open" :title="form.id ? PP.t('fleet.edit') : PP.t('fleet.add')" @close="form.open = false">
      <div class="field"><label>{{ PP.t('common.name') }}</label>
        <input class="input mono" v-model="form.name" placeholder="vps-jakarta"></div>
      <div class="field"><label>Base URL</label>
        <input class="input mono" v-model="form.base_url" placeholder="https://203.0.113.10:21000"></div>
      <div class="field"><label>Entry path</label>
        <input class="input mono" v-model="form.entry_path" placeholder="aeb13e66"></div>
      <div class="field"><label>API key (ppk_… — {{ PP.t('fleet.keyHint') }})</label>
        <input class="input mono" type="password" v-model="form.api_key"></div>
      <div class="checkbox-row mb"><p-switch v-model="form.enabled"></p-switch><span>{{ PP.t('fleet.enabled') }}</span></div>
      <template #foot>
        <button class="btn" @click="form.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="save">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
