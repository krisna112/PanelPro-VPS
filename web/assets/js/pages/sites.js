/* Websites page: CRUD, vhost editor, domains, proxy, PHP, logs, SSL deploy */
PP.pages = PP.pages || {};
function newSiteForm(server = '') {
  return { domain: '', aliases: '', mode: 'static', server, php_version: '', proxy_target: '',
    withDb: false, db_name: '', db_user: '', db_password: '' };
}

PP.pages.sites = {
  data: () => ({
    sites: [], servers: [], busy: true, loadError: '', reloading: false,
    showCreate: false, creating: false, createError: '', form: newSiteForm(),
    phpVersions: [],
    editor: { open: false, site: null, path: '', content: '', saving: false },
    logs: { open: false, site: null, type: 'access', text: '' },
    domains: { open: false, site: null, value: '' },
    proxy: { open: false, site: null, target: '' },
    sslList: [], sslFor: null, showSslPick: false, sslSaving: false, changingSites: {},
  }),
  computed: {
    canManage() { return ['admin', 'operator'].includes(PP.store.user?.role); },
    canEditConfig() { return PP.store.user?.role === 'admin'; },
    activeServers() { return this.servers.filter(server => server.active); },
    activePhp() { return this.phpVersions.filter(version => version.fpm_active); },
  },
  methods: {
    async load() {
      this.loadError = '';
      try {
        const [sites, status, php] = await Promise.all([
          PP.api('sites'), PP.api('sites/server-status'), PP.api('php/versions').catch(() => []),
        ]);
        this.sites = sites;
        this.servers = status.servers;
        this.phpVersions = php;
      } catch (e) { this.loadError = e.message; }
      finally { this.busy = false; }
    },
    async reloadServer(server) {
      this.reloading = true;
      try {
        await PP.api('sites/reload', { method: 'POST', params: { server } });
        PP.ui.success(PP.t('sites.reloaded'), server);
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      finally { this.reloading = false; }
    },
    openCreate() {
      this.form = newSiteForm(this.activeServers[0]?.server);
      this.createError = '';
      this.showCreate = true;
    },
    async create() {
      if (this.creating) return;
      this.creating = true;
      this.createError = '';
      try {
        const body = {
          domain: this.form.domain.trim(),
          aliases: this.form.aliases.split(',').map(s => s.trim()).filter(Boolean),
          server: this.form.server,
          php_version: this.form.mode === 'php' ? this.form.php_version : null,
          proxy_target: this.form.mode === 'proxy' ? this.form.proxy_target.trim() : null,
          create_db: this.form.withDb ? {
            type: 'mysql',
            name: this.form.db_name,
            user: this.form.db_user,
            password: this.form.db_password || undefined,
          } : null,
        };
        const res = await PP.api('sites', { method: 'POST', body });
        this.showCreate = false;
        this.form = newSiteForm();
        PP.ui.success(PP.t('sites.create'), res.site.root);
        if (res.db && res.db.password) {
          PP.ui.toast('DB: ' + res.db.database + ' / ' + res.db.user, res.db.password, 'warn', 15000);
        }
        await this.load();
      } catch (e) { this.createError = e.message; }
      finally { this.creating = false; }
    },
    async del(site) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), site.name);
      if (!ok) return;
      try {
        await PP.api('sites/' + site.id + '/delete', { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async toggle(site) {
      this.changingSites[site.id] = true;
      try {
        await PP.api('sites/' + site.id + '/toggle', { method: 'POST' });
        await this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      finally { delete this.changingSites[site.id]; }
    },
    async openConf(site) {
      try {
        const data = await PP.api('sites/' + site.id + '/conf');
        this.editor = { open: true, site, path: data.path, content: data.content, saving: false };
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async saveConf() {
      this.editor.saving = true;
      try {
        await PP.api('sites/' + this.editor.site.id + '/conf', {
          method: 'POST',
          body: { content: this.editor.content },
        });
        PP.ui.success(PP.t('common.save'));
        this.editor.open = false;
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.editor.saving = false;
    },
    async openLogs(site) {
      this.logs = { open: true, site, type: 'access', text: '' };
      this.fetchLogs();
    },
    async fetchLogs() {
      try {
        const data = await PP.api('sites/' + this.logs.site.id + '/logs', {
          params: { type: this.logs.type },
        });
        this.logs.text = data.log || '(empty)';
      } catch (e) { this.logs.text = e.message; }
    },
    openDomains(site) {
      this.domains = { open: true, site, value: '' };
    },
    async addDomain() {
      if (!this.domains.value) return;
      try {
        const data = await PP.api('sites/' + this.domains.site.id + '/domains', {
          method: 'POST', body: { domain: this.domains.value.trim() },
        });
        this.domains.site.aliases = data.aliases;
        this.domains.value = '';
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async removeDomain(alias) {
      try {
        const data = await PP.api('sites/' + this.domains.site.id + '/domains/remove', {
          method: 'POST', body: { domain: alias },
        });
        this.domains.site.aliases = data.aliases;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    openProxy(site) {
      this.proxy = { open: true, site, target: site.proxy_target || '' };
    },
    async saveProxy() {
      try {
        await PP.api('sites/' + this.proxy.site.id + '/proxy', {
          method: 'POST', body: { target: this.proxy.target.trim() || null },
        });
        this.proxy.open = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async setPhp(site, control) {
      this.changingSites[site.id] = true;
      try {
        await PP.api('sites/' + site.id + '/php', { method: 'POST', body: { version: control.value || null } });
        await this.load();
      } catch (e) {
        control.value = site.php_version || '';
        PP.ui.error(PP.t('common.error'), e.message);
      } finally { delete this.changingSites[site.id]; }
    },
    async setHttps(site, value) {
      this.sslSaving = true;
      try {
        const data = await PP.api('sites/' + site.id + '/https', { method: 'POST', body: { force: value } });
        this.sslFor.force_https = data.force_https;
        await this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      finally { this.sslSaving = false; }
    },
    openSsl(site) {
      this.sslFor = site;
      PP.api('ssl').then(data => { this.sslList = data.certs; this.showSslPick = true; }).catch(e => PP.ui.error(PP.t('common.error'), e.message));
    },
    async deploySsl(certId) {
      this.sslSaving = true;
      try {
        await PP.api('sites/' + this.sslFor.id + '/ssl', { method: 'POST', body: { cert_id: certId } });
        this.showSslPick = false;
        await this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      finally { this.sslSaving = false; }
    },
    async detachSsl() {
      this.sslSaving = true;
      try {
        await PP.api('sites/' + this.sslFor.id + '/ssl/remove', { method: 'POST' });
        this.showSslPick = false;
        await this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      finally { this.sslSaving = false; }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.sites') }}</h1>
      <span v-for="server in servers" :key="server.server" class="badge" :class="server.active ? 'green' : 'gray'">
        {{ server.server }} · {{ PP.t(server.active ? 'common.enabled' : 'common.disabled') }}</span>
      <span class="spacer"></span>
      <template v-if="canManage">
        <button v-for="server in activeServers" :key="server.server" class="btn" :disabled="reloading"
                @click="reloadServer(server.server)">{{ PP.t('sites.reload') }} {{ server.server }}</button>
        <button class="btn primary" :disabled="!activeServers.length" @click="openCreate">+ {{ PP.t('sites.create') }}</button>
      </template>
    </div>
    <p v-if="loadError" class="muted" role="alert">{{ loadError }} <button class="btn small" @click="load">{{ PP.t('sites.retry') }}</button></p>
    <p v-else-if="!busy && !activeServers.length" class="muted" role="status">{{ PP.t('sites.noWebserver') }}</p>

    <p-table :cols="[
        { key: 'name', label: PP.t('sites.domain') },
        { key: 'server', label: 'Server', width: '90px' },
        { key: 'php', label: 'PHP', width: '90px' },
        { key: 'ssl', label: 'SSL', width: '110px' },
        { key: 'status', label: PP.t('common.status'), width: '110px' },
        { key: 'actions', label: PP.t('common.actions'), cls: 'actions' }]"
      :rows="sites" :empty="PP.t(busy ? 'common.loading' : 'sites.empty')">

      <template #col-name="{ row }">
        <div class="site-domain-cell">
          <a v-if="row.enabled && !row.name.startsWith('*')" :href="(row.ssl ? 'https://' : 'http://') + row.name" class="mono" target="_blank" rel="noopener noreferrer">{{ row.name }}</a>
          <span v-else class="mono">{{ row.name }}</span>
          <div class="small faint" v-if="row.aliases && row.aliases.length">{{ row.aliases.join(', ') }}</div>
          <router-link v-if="canManage" :to="{ name: 'files', query: { path: row.root } }" class="small mono">{{ row.root }}</router-link>
        </div>
      </template>
      <template #col-php="{ row }">
        <span v-if="row.proxy_target">{{ PP.t('sites.proxy') }}</span>
        <select v-else-if="canManage" class="select site-php-select" :value="row.php_version || ''"
                :aria-label="PP.t('sites.phpVersion') + ' ' + row.name" :disabled="changingSites[row.id]"
                @change="setPhp(row, $event.target)">
          <option value="">—</option>
          <option v-if="row.php_version && !activePhp.some(v => v.version === row.php_version)"
                  :value="row.php_version" disabled>{{ row.php_version }}</option>
          <option v-for="v in activePhp" :key="v.version" :value="v.version">{{ v.version }}</option>
        </select>
        <span v-else>{{ row.php_version || '—' }}</span>
      </template>
      <template #col-ssl="{ row }">
        <span v-if="row.ssl" class="badge green">{{ row.ssl.issuer }}</span>
        <span v-else class="badge gray">—</span>
      </template>
      <template #col-status="{ row }">
        <button v-if="canManage" class="btn small" :class="{ active: row.enabled }" :aria-pressed="row.enabled"
                :disabled="changingSites[row.id]" @click="toggle(row)">{{ PP.t(row.enabled ? 'common.enabled' : 'common.disabled') }}</button>
        <span v-else>{{ PP.t(row.enabled ? 'common.enabled' : 'common.disabled') }}</span>
      </template>
      <template #col-actions="{ row }">
        <button v-if="canEditConfig" class="btn small" :disabled="!row.enabled" :title="PP.t('sites.editConf')" :aria-label="PP.t('sites.editConf')" @click="openConf(row)">⚙</button>
        <button v-if="canManage" class="btn small" :title="PP.t('sites.aliases')" :aria-label="PP.t('sites.aliases')" @click="openDomains(row)">🌐</button>
        <button v-if="canManage" class="btn small" :title="PP.t('sites.proxy')" :aria-label="PP.t('sites.proxy')" @click="openProxy(row)">🔀</button>
        <button v-if="canManage" class="btn small" title="SSL / HTTPS" aria-label="SSL / HTTPS" @click="openSsl(row)">🔒</button>
        <button class="btn small" :title="PP.t('sites.logs')" :aria-label="PP.t('sites.logs')" @click="openLogs(row)">📜</button>
        <button v-if="canManage" class="btn small danger" :title="PP.t('common.confirmDelete')" :aria-label="PP.t('common.confirmDelete')" @click="del(row)">🗑</button>
      </template>
    </p-table>

    <p-modal :open="showCreate" :title="PP.t('sites.create')" size="lg" @close="!creating && (showCreate = false)">
      <form id="create-website" @submit.prevent="create">
      <div class="form-row">
        <div class="field"><label for="site-domain">{{ PP.t('sites.domain') }}</label>
          <input id="site-domain" class="input mono" v-model.trim="form.domain" spellcheck="false" required placeholder="example.com"></div>
        <div class="field"><label for="site-aliases">{{ PP.t('sites.aliases') }} ({{ PP.t('common.optional') }})</label>
          <input id="site-aliases" class="input mono" v-model="form.aliases" spellcheck="false" placeholder="www.example.com, api.example.com"></div>
      </div>
      <div class="form-row">
        <div class="field"><label for="site-server">Webserver</label>
          <select id="site-server" class="select" v-model="form.server">
            <option v-for="server in activeServers" :key="server.server" :value="server.server">{{ server.server }}</option>
          </select></div>
        <div class="field"><label for="site-mode">{{ PP.t('sites.mode') }}</label>
          <select id="site-mode" class="select" v-model="form.mode">
            <option value="static">{{ PP.t('sites.static') }}</option>
            <option value="php">PHP-FPM</option>
            <option value="proxy">{{ PP.t('sites.proxy') }}</option>
          </select></div>
      </div>
      <div class="field" v-if="form.mode === 'php'">
        <label for="site-runtime">{{ PP.t('sites.phpVersion') }}</label>
        <select id="site-runtime" class="select" v-model="form.php_version" required>
          <option value="" disabled>{{ PP.t(activePhp.length ? 'sites.selectPhp' : 'sites.noPhp') }}</option>
          <option v-for="v in activePhp" :key="v.version" :value="v.version">{{ v.version }}</option>
        </select>
      </div>
      <div class="field" v-if="form.mode === 'proxy'">
        <label for="site-backend">{{ PP.t('sites.backend') }}</label>
        <input id="site-backend" class="input mono" type="url" v-model.trim="form.proxy_target" required placeholder="http://127.0.0.1:3000">
        <span class="small faint">{{ PP.t('sites.backendHint') }}</span>
      </div>
      <label class="checkbox-row mb">
        <input type="checkbox" v-model="form.withDb">
        <span>{{ PP.t('sites.withDb') }} (MySQL)</span>
      </label>
      <div class="form-row" v-if="form.withDb">
        <div class="field"><label for="site-db">Database</label><input id="site-db" class="input mono" v-model="form.db_name"></div>
        <div class="field"><label for="site-db-user">{{ PP.t('common.username') }}</label><input id="site-db-user" class="input mono" v-model="form.db_user"></div>
        <div class="field"><label for="site-db-password">{{ PP.t('common.password') }} ({{ PP.t('common.optional') }})</label><input id="site-db-password" class="input mono" type="password" autocomplete="new-password" v-model="form.db_password"></div>
      </div>
      <p v-if="createError" class="site-error" role="alert">{{ createError }}</p>
      </form>
      <template #foot>
        <button class="btn" :disabled="creating" @click="showCreate = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" type="submit" form="create-website" :disabled="creating || !form.server">
          {{ PP.t(creating ? 'common.loading' : 'common.create') }}</button>
      </template>
    </p-modal>

    <p-modal :open="editor.open" :title="PP.t('sites.editConf') + ' — ' + (editor.site ? editor.site.name : '')" size="lg" @close="editor.open = false">
      <div class="small faint mb">{{ editor.path }}</div>
      <textarea class="input code-editor" v-model="editor.content" spellcheck="false"></textarea>
      <template #foot>
        <button class="btn" @click="editor.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" :disabled="editor.saving" @click="saveConf">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="logs.open" :title="PP.t('sites.logs') + ' — ' + (logs.site ? logs.site.name : '')" size="lg" @close="logs.open = false">
      <div class="tabs">
        <button class="tab" :class="{ active: logs.type === 'access' }" @click="logs.type = 'access'; fetchLogs()">access</button>
        <button class="tab" :class="{ active: logs.type === 'error' }" @click="logs.type = 'error'; fetchLogs()">error</button>
      </div>
      <div class="log-view">{{ logs.text }}</div>
    </p-modal>

    <p-modal :open="domains.open" :title="PP.t('sites.aliases')" @close="domains.open = false">
      <div class="flex mb" v-for="alias in (domains.site ? domains.site.aliases : [])" :key="alias">
        <span class="mono grow">{{ alias }}</span>
        <button class="btn small danger" @click="removeDomain(alias)">✕</button>
      </div>
      <div class="flex">
        <input class="input mono grow" v-model="domains.value" placeholder="sub.example.com"
               @keyup.enter="addDomain">
        <button class="btn primary" @click="addDomain">+</button>
      </div>
    </p-modal>

    <p-modal :open="proxy.open" :title="PP.t('sites.proxy')" @close="proxy.open = false">
      <div class="field">
        <label for="edit-site-backend">{{ PP.t('sites.backend') }} ({{ PP.t('common.optional') }})</label>
        <input id="edit-site-backend" class="input mono" v-model="proxy.target" placeholder="http://127.0.0.1:3000">
      </div>
      <template #foot>
        <button class="btn" @click="proxy.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="saveProxy">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="showSslPick" :title="PP.t('ssl.deploy')" @close="showSslPick = false">
      <label v-if="sslFor?.ssl" class="checkbox-row mb">
        <input type="checkbox" :checked="sslFor.force_https" :disabled="sslSaving" @change="$event.target.checked = sslFor.force_https; setHttps(sslFor, !sslFor.force_https)">
        <span>{{ PP.t('sites.forceHttps') }}</span>
      </label>
      <div class="btn-row" v-if="sslList.length" style="flex-direction:column; align-items:stretch">
        <button v-for="c in sslList" :key="c.id" class="btn" :disabled="sslSaving || sslFor?.ssl?.cert_id === c.id" @click="deploySsl(c.id)">
          {{ c.name }} <span class="faint small">({{ c.domain }})</span>
        </button>
      </div>
      <template #foot>
        <button v-if="sslFor?.ssl" class="btn danger" :disabled="sslSaving" @click="detachSsl">{{ PP.t('sites.detachSsl') }}</button>
        <router-link v-if="sslFor?.enabled" class="btn primary" :to="{ name: 'ssl', query: { site: sslFor.id } }">{{ PP.t('ssl.letsencrypt') }}</router-link>
      </template>
    </p-modal>
  </div>`,
};
