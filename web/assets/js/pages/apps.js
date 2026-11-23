/* App store: one-click installers + installed apps */
PP.pages = PP.pages || {};
PP.pages.apps = {
  data: () => ({
    available: [], installed: [],
    install: { open: false, app: null, params: {} },
  }),
  methods: {
    async load() {
      try {
        const data = await PP.api('apps');
        this.available = data.available;
        this.installed = data.installed;
      } catch (e) { PP.ui.warn(e.message); }
    },
    openInstall(app) {
      const params = {};
      for (const p of app.params || []) params[p.name] = p.default || '';
      this.install = { open: true, app, params };
    },
    async doInstall() {
      const app = this.install.app;
      try {
        PP.ui.toast(PP.t('common.install'), app.name + ' — running, please wait…', 'info', 10000);
        await PP.api('apps/install', { method: 'POST', body: { app_id: app.id, params: this.install.params } });
        this.install.open = false;
        PP.ui.success(PP.t('common.install'), app.name);
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async uninstall(row) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), row.name);
      if (!ok) return;
      try {
        await PP.api('apps/' + row.id + '/uninstall', { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.apps') }}</h1>
      <span class="spacer"></span>
      <button class="btn" @click="load">⟳</button>
    </div>

    <div class="card mb" v-if="installed.length">
      <div class="card-title">{{ PP.t('common.installed') }}</div>
      <p-table :cols="[{ key: 'name', label: PP.t('common.name') }, { key: 'type', label: PP.t('common.type') },
                       { key: 'port', label: 'Port' }, { key: 'status', label: PP.t('common.status') },
                       { key: 'actions', label: '', cls: 'actions' }]" :rows="installed">
        <template #col-status="{ row }">
          <span class="badge" :class="PP.ui.statusBadge(row.status)">{{ row.status }}</span>
        </template>
        <template #col-actions="{ row }">
          <a v-if="row.port" class="btn small" :href="'http://' + location.hostname + ':' + row.port" target="_blank">↗</a>
          <button class="btn small danger" @click="uninstall(row)">{{ PP.t('common.uninstall') }}</button>
        </template>
      </p-table>
    </div>

    <div class="grid cols-3">
      <div class="card" v-for="app in available" :key="app.id">
        <div class="card-title">{{ app.name }}
          <span class="spacer"></span>
          <span class="badge violet">{{ app.category }}</span>
        </div>
        <div class="small muted" style="min-height:40px">{{ app.description }}</div>
        <div class="flex mt">
          <span class="badge gray" v-if="app.type === 'docker'">docker</span>
          <span class="badge gray" v-if="app.port">:{{ app.port }}</span>
          <span class="grow"></span>
          <button class="btn small primary" @click="openInstall(app)">{{ PP.t('common.install') }}</button>
        </div>
      </div>
    </div>

    <p-modal :open="install.open" :title="PP.t('apps.install') + ' — ' + (install.app ? install.app.name : '')" @close="install.open = false">
      <div class="field" v-for="p in (install.app ? install.app.params : [])" :key="p.name">
        <label>{{ p.label }}</label>
        <input class="input mono" v-model="install.params[p.name]" :placeholder="p.default">
      </div>
      <template #foot>
        <button class="btn" @click="install.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="doInstall">{{ PP.t('common.install') }}</button>
      </template>
    </p-modal>
  </div>`,
};
