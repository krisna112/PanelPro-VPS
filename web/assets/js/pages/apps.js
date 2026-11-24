/* App Store catalog and installed software */
PP.pages = PP.pages || {};
PP.pages.apps = {
  data: () => ({
    available: [], installed: [], query: '', category: '',
    busy: true, loadError: '', accessApp: null,
    install: { open: false, app: null, params: {}, busy: false, error: '' },
  }),
  computed: {
    categories() { return [...new Set(this.available.map(app => app.category))].sort(); },
    results() {
      const query = this.query.trim().toLowerCase();
      return this.available.filter(app =>
        (!this.category || this.category === app.category) &&
        (app.name + ' ' + app.description).toLowerCase().includes(query)
      );
    },
    isAdmin() { return PP.store.user?.role === 'admin'; },
    canManage() { return ['admin', 'operator'].includes(PP.store.user?.role); },
  },
  methods: {
    async load() {
      this.busy = true;
      this.loadError = '';
      try {
        const data = await PP.api('apps');
        this.available = data.available;
        this.installed = data.installed;
      } catch (error) {
        this.loadError = error.message;
      } finally {
        this.busy = false;
      }
    },
    openInstall(app) {
      const params = Object.fromEntries((app.params || []).map(p => [p.name, p.default ?? '']));
      this.install = { open: true, app, params, busy: false, error: '' };
    },
    closeInstall() {
      if (!this.install.busy) this.install.open = false;
    },
    async doInstall() {
      if (this.install.busy) return;
      this.install.busy = true;
      this.install.error = '';
      const app = this.install.app;
      try {
        await PP.api('apps/install', { method: 'POST', body: { app_id: app.id, params: this.install.params } });
        this.install.open = false;
        PP.ui.success(PP.t('common.installed'), app.name);
        await this.load();
      } catch (error) {
        this.install.error = error.message;
      } finally {
        this.install.busy = false;
      }
    },
    async uninstall(row) {
      if (!await PP.ui.confirm(PP.t('common.confirmDelete'), row.name)) return;
      try {
        await PP.api('apps/' + row.id + '/uninstall', { method: 'POST' });
        await this.load();
      } catch (error) {
        PP.ui.error(PP.t('common.error'), error.message);
      }
    },
    appUrl(row) {
      if (row.loopback) return 'http://127.0.0.1:' + row.port + '/';
      const protocol = row.app_id === 'portainer' ? 'https:' : 'http:';
      return protocol + '//' + window.location.hostname + ':' + row.port + '/';
    },
    isInstalled(app) {
      return this.installed.some(row => row.app_id === app.id && row.type === app.type);
    },
    categoryName(category) {
      const key = 'apps.category.' + category;
      const label = PP.t(key);
      return label === key ? category : label;
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.apps') }}</h1>
      <span class="spacer"></span>
      <button class="btn" :disabled="busy" @click="load">{{ PP.t('common.refresh') }}</button>
    </div>
    <p v-if="loadError" class="site-error" role="alert">{{ loadError }}</p>
    <p v-else-if="busy && !available.length" class="muted" role="status">{{ PP.t('common.loading') }}</p>

    <div class="card mb" v-if="installed.length">
      <div class="card-title">{{ PP.t('common.installed') }}</div>
      <p-table :cols="[{ key: 'name', label: PP.t('common.name') }, { key: 'version', label: PP.t('common.version') },
                       { key: 'port', label: 'Port' }, { key: 'status', label: PP.t('common.status') },
                       { key: 'actions', label: '', cls: 'actions' }]" :rows="installed">
        <template #col-status="{ row }">
          <span class="badge" :class="PP.ui.statusBadge(row.status)">{{ row.status }}</span>
        </template>
        <template #col-actions="{ row }">
          <button v-if="row.loopback" class="btn small" @click="accessApp = row">{{ PP.t('apps.sshAccess') }}</button>
          <a v-else-if="row.port" class="btn small" :href="appUrl(row)" target="_blank" rel="noopener noreferrer">{{ PP.t('apps.open') }}</a>
          <button v-if="row.loopback ? isAdmin : (canManage && row.type !== 'native')"
                  class="btn small danger" @click="uninstall(row)">{{ PP.t(row.loopback ? 'apps.removeAccess' : 'common.uninstall') }}</button>
        </template>
      </p-table>
    </div>

    <div v-if="available.length" class="form-row">
      <div class="field">
        <label for="app-search">{{ PP.t('apps.search') }}</label>
        <input id="app-search" class="input" v-model="query" type="search" placeholder="PHP, Redis, WordPress">
      </div>
      <div class="field">
        <label for="app-category">{{ PP.t('apps.category') }}</label>
        <select id="app-category" class="select" v-model="category">
          <option value="">{{ PP.t('common.all') }}</option>
          <option v-for="item in categories" :key="item" :value="item">{{ categoryName(item) }}</option>
        </select>
      </div>
    </div>

    <p v-if="available.length && !results.length" class="muted" role="status">{{ PP.t('apps.noMatches') }}</p>
    <div class="grid cols-3">
      <div class="card" v-for="app in results" :key="app.id">
        <div class="card-title">
          {{ app.name }} <span class="spacer"></span>
          <span class="badge gray">{{ categoryName(app.category) }}</span>
        </div>
        <p class="small muted">{{ app.description }}</p>
        <p v-if="app.unavailable" class="small muted">{{ app.unavailable }}</p>
        <div class="flex mt">
          <span v-if="app.type === 'docker'" class="badge gray">Docker</span>
          <span v-if="isInstalled(app)" class="badge green">{{ PP.t('common.installed') }}</span>
          <span class="grow"></span>
          <button class="btn small primary" :disabled="app.unavailable || !canManage || (app.type === 'native' && !isAdmin) || (isInstalled(app) && app.type !== 'native')"
                  @click="openInstall(app)">{{ PP.t('common.install') }}</button>
        </div>
      </div>
    </div>

    <p-modal :open="install.open" :title="PP.t('apps.install') + ' — ' + (install.app?.name || '')" @close="closeInstall">
      <form id="app-install-form" @submit.prevent="doInstall">
        <p v-if="install.app" class="muted">{{ install.app.description }}</p>
        <div class="field" v-for="p in (install.app?.params || [])" :key="p.name">
          <label :for="'app-param-' + p.name">{{ p.label }}</label>
          <select v-if="p.choices" class="select" :id="'app-param-' + p.name" v-model="install.params[p.name]" :disabled="install.busy">
            <option v-for="choice in p.choices" :key="choice" :value="choice">{{ choice === 'default' ? PP.t('apps.distroDefault') : choice }}</option>
          </select>
          <input v-else class="input mono" :id="'app-param-' + p.name" :type="p.name === 'db_pass' ? 'password' : 'text'"
                 v-model="install.params[p.name]" :required="p.required" :disabled="install.busy">
        </div>
        <p v-if="install.error" class="site-error" role="alert">{{ install.error }}</p>
      </form>
      <template #foot>
        <button class="btn" :disabled="install.busy" @click="closeInstall">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" form="app-install-form" type="submit" :disabled="install.busy">{{ PP.t(install.busy ? 'apps.installing' : 'common.install') }}</button>
      </template>
    </p-modal>

    <p-modal :open="!!accessApp" :title="accessApp?.name || ''" @close="accessApp = null">
      <template v-if="accessApp">
        <p>{{ PP.t('apps.sshHelp') }}</p>
        <code class="mono">ssh -N -L {{ accessApp.port }}:127.0.0.1:{{ accessApp.port }} USER@IP_VPS</code>
        <p>{{ PP.t('apps.dbLogin') }}</p>
        <a class="btn primary" :href="appUrl(accessApp)" target="_blank" rel="noopener noreferrer">{{ PP.t('apps.open') }}</a>
      </template>
    </p-modal>
  </div>`,
};
