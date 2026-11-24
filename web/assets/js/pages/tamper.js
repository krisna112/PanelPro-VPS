/* Tamper protection: file-integrity watch per site */
PP.pages = PP.pages || {};
PP.pages.tamper = {
  data: () => ({
    sites: [], watches: {}, scanResult: null,
    form: { open: false, site_id: null, name: '', enabled: true, mode: 'alert' },
    busy: false,
  }),
  methods: {
    async load() {
      try {
        this.sites = await PP.api('sites');
        const data = await PP.api('tamper');
        this.watches = {};
        for (const w of data.watches) this.watches[w.site_id] = w;
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    watchOf(site) { return this.watches[site.id]; },
    openForm(site) {
      const w = this.watchOf(site) || {};
      this.form = { open: true, site_id: site.id, name: site.name,
                    enabled: w.enabled !== undefined ? w.enabled : true,
                    mode: w.mode || 'alert' };
    },
    async save() {
      try {
        await PP.api('tamper', { method: 'POST', body: { site_id: this.form.site_id,
          enabled: this.form.enabled, mode: this.form.mode } });
        this.form.open = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async buildBaseline(site) {
      this.busy = true;
      try {
        const w = this.watchOf(site);
        const res = await PP.api('tamper/' + w.id + '/baseline', { method: 'POST' });
        PP.ui.success(PP.t('tamper.baselineOk'), res.files + ' files');
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.busy = false;
    },
    async scan(site) {
      this.busy = true;
      this.scanResult = null;
      try {
        const w = this.watchOf(site);
        this.scanResult = await PP.api('tamper/' + w.id + '/scan', { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.busy = false;
    },
    async del(site) {
      const w = this.watchOf(site);
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), site.name);
      if (!ok) return;
      try { await PP.api('tamper/' + w.id + '/delete', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    changeCount(row) {
      if (!row.last_changes) return 0;
      return (row.last_changes.modified || []).length + (row.last_changes.added || []).length + (row.last_changes.deleted || []).length;
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.tamper') }}</h1>
    </div>
    <p class="small">{{ PP.t('tamper.desc') }}</p>

    <p-table :cols="[{ key: 'name', label: PP.t('sites.domain') },
                     { key: 'watch', label: PP.t('tamper.watch') },
                     { key: 'mode', label: PP.t('tamper.mode') },
                     { key: 'baseline', label: PP.t('tamper.baseline') },
                     { key: 'changes', label: PP.t('tamper.changes') },
                     { key: 'actions', label: '', cls: 'actions' }]" :rows="sites">
      <template #col-name="{ row }"><span class="mono">{{ row.name }}</span></template>
      <template #col-watch="{ row }">
        <span class="badge" :class="watchOf(row) && watchOf(row).enabled ? 'green' : 'gray'">
          {{ watchOf(row) ? (watchOf(row).enabled ? 'on' : 'off') : '—' }}</span>
      </template>
      <template #col-mode="{ row }">{{ watchOf(row) ? watchOf(row).mode : '—' }}</template>
      <template #col-baseline="{ row }">
        {{ watchOf(row) && watchOf(row).baseline_files ? watchOf(row).baseline_files + ' files' : '—' }}
      </template>
      <template #col-changes="{ row }">
        <span class="badge" :class="watchOf(row) && changeCount(watchOf(row)) ? 'red' : 'green'">
          {{ watchOf(row) ? changeCount(watchOf(row)) : '—' }}</span>
      </template>
      <template #col-actions="{ row }">
        <template v-if="watchOf(row)">
          <button class="btn small" @click="buildBaseline(row)" :disabled="busy">📋</button>
          <button class="btn small" @click="scan(row)" :disabled="busy">🔍</button>
          <button class="btn small" @click="openForm(row)">✎</button>
          <button class="btn small danger" @click="del(row)">🗑</button>
        </template>
        <button class="btn small primary" v-else @click="openForm(row)">+</button>
      </template>
    </p-table>

    <div class="card mt" v-if="scanResult">
      <h3>{{ PP.t('tamper.scanResult') }}</h3>
      <p class="small mono">{{ scanResult.modified.length }} modified · {{ scanResult.added.length }} added ·
         {{ scanResult.deleted.length }} deleted · {{ scanResult.restored }} restored</p>
      <p class="mono small" v-for="f in scanResult.modified.slice(0, 20)" :key="f">~ {{ f }}</p>
      <p class="mono small" v-for="f in scanResult.added.slice(0, 20)" :key="'a'+f">+ {{ f }}</p>
      <p class="mono small" v-for="f in scanResult.deleted.slice(0, 20)" :key="'d'+f">− {{ f }}</p>
    </div>

    <p-modal :open="form.open" :title="'Tamper — ' + form.name" @close="form.open = false">
      <div class="checkbox-row mb"><p-switch v-model="form.enabled"></p-switch><span>{{ PP.t('tamper.enabled') }}</span></div>
      <div class="field"><label>{{ PP.t('tamper.mode') }}</label>
        <select class="select" v-model="form.mode">
          <option value="alert">{{ PP.t('tamper.modeAlert') }}</option>
          <option value="auto_restore">{{ PP.t('tamper.modeRestore') }}</option>
        </select></div>
      <template #foot>
        <button class="btn" @click="form.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="save">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
