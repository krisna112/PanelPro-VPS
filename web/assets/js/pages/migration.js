/* Migration: export this server's sites/DBs/certs, import a bundle */
PP.pages = PP.pages || {};
PP.pages.migration = {
  data: () => ({
    sites: [], selected: new Set(), includeDb: true, includeSsl: true,
    status: { state: 'idle', progress: 0, message: '' },
    pollTimer: null, importing: false,
  }),
  methods: {
    async load() {
      try {
        this.sites = await PP.api('sites');
        this.status = await PP.api('migration/status');
        if (this.status.state === 'running' && !this.pollTimer) {
          this.pollTimer = setInterval(() => this.load(), 2000);
        }
        if (this.status.state !== 'running' && this.pollTimer) {
          clearInterval(this.pollTimer);
          this.pollTimer = null;
        }
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    toggleSite(id) {
      if (this.selected.has(id)) this.selected.delete(id);
      else this.selected.add(id);
    },
    async exportBundle() {
      try {
        await PP.api('migration/export', {
          method: 'POST',
          body: {
            include_db: this.includeDb, include_ssl: this.includeSsl,
            site_ids: this.selected.size ? [...this.selected] : null,
          },
        });
        PP.ui.success(PP.t('migration.started'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async importBundle(ev) {
      const file = ev.target.files[0];
      if (!file) return;
      const ok = await PP.ui.confirm(PP.t('migration.importConfirm'), file.name);
      if (!ok) { ev.target.value = ''; return; }
      this.importing = true;
      const fd = new FormData();
      fd.append('file', file);
      try {
        const res = await fetch('/api/migration/import', {
          method: 'POST', credentials: 'same-origin',
          headers: { 'X-PP-Request': '1' }, body: fd,
        });
        const payload = await res.json();
        if (!payload.ok) throw new Error(payload.message || 'Import failed');
        PP.ui.success(PP.t('migration.importStarted'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.importing = false;
      ev.target.value = '';
    },
    stateBadge(state) {
      return state === 'done' ? 'green' : state === 'failed' ? 'red' : state === 'running' ? 'amber' : 'gray';
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.migration') }}</h1>
    </div>
    <p class="small">{{ PP.t('migration.desc') }}</p>

    <div class="grid cols-2">
      <div class="card">
        <h3>{{ PP.t('migration.export') }}</h3>
        <div class="checkbox-row mb"><p-switch v-model="includeDb"></p-switch><span>{{ PP.t('migration.includeDb') }}</span></div>
        <div class="checkbox-row mb"><p-switch v-model="includeSsl"></p-switch><span>{{ PP.t('migration.includeSsl') }}</span></div>
        <div class="field">
          <label>{{ PP.t('migration.sites') }} ({{ PP.t('common.optional') }} — kosong = semua)</label>
          <div class="flex wrap">
            <label class="badge" :class="selected.has(s.id) ? 'blue' : 'gray'" style="cursor:pointer;margin:2px"
                   v-for="s in sites" :key="s.id" @click="toggleSite(s.id)">
              {{ s.name }}</label>
          </div>
        </div>
        <button class="btn primary" @click="exportBundle" :disabled="status.state === 'running'">
          {{ PP.t('migration.export') }}</button>
      </div>

      <div class="card">
        <h3>{{ PP.t('migration.import') }}</h3>
        <p class="small">{{ PP.t('migration.importDesc') }}</p>
        <label class="btn" :class="{ 'opacity-50': importing }">
          {{ importing ? '…' : '⬆ ' + PP.t('migration.pickBundle') }}
          <input type="file" accept=".tar.gz,.tgz" style="display:none" @change="importBundle">
        </label>
      </div>
    </div>

    <div class="card mt">
      <h3>{{ PP.t('migration.status') }}</h3>
      <span class="badge" :class="stateBadge(status.state)">{{ status.state }}</span>
      <p class="small mono mt" v-if="status.message">{{ status.message }}</p>
      <p-progress :value="status.progress" v-if="status.state === 'running'"></p-progress>
    </div>
  </div>`,
};
