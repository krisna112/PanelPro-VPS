/* Websites page: CRUD, vhost editor, domains, proxy, PHP, logs, SSL deploy */
PP.pages = PP.pages || {};
PP.pages.sites = {
  data: () => ({
    sites: [], serverStatus: null, busy: true,
    showCreate: false, creating: false,
    form: { domain: '', aliases: '', php_version: '', server: 'nginx', withDb: false, db_name: '', db_user: '', db_password: '' },
    phpVersions: [],
    editor: { open: false, site: null, path: '', content: '', saving: false },
    logs: { open: false, site: null, type: 'access', text: '' },
    domains: { open: false, site: null, value: '' },
    proxy: { open: false, site: null, target: '' },
    sslList: [], sslFor: null, showSslPick: false,
  }),
  methods: {
    async load() {
      try {
        this.sites = await PP.api('sites');
        this.serverStatus = await PP.api('sites/server-status');
        try { this.phpVersions = await PP.api('php/versions'); } catch (e) { /* ignore */ }
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.busy = false;
    },
    async reloadServer() {
      try {
        await PP.api('sites/reload', { method: 'POST' });
        PP.ui.success('Webserver reloaded');
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    openCreate() { this.showCreate = true; },
    async create() {
      if (!this.form.domain) return;
      this.creating = true;
      try {
        const body = {
          domain: this.form.domain.trim(),
          aliases: this.form.aliases.split(',').map(s => s.trim()).filter(Boolean),
          server: this.form.server,
          php_version: this.form.php_version || null,
          create_db: this.form.withDb ? {
            type: 'mysql',
            name: this.form.db_name,
            user: this.form.db_user,
            password: this.form.db_password || undefined,
          } : null,
        };
        const res = await PP.api('sites', { method: 'POST', body });
        this.showCreate = false;
        this.form = { domain: '', aliases: '', php_version: '', server: 'nginx', withDb: false, db_name: '', db_user: '', db_password: '' };
        PP.ui.success(PP.t('sites.create'), res.site.root);
        if (res.db && res.db.password) {
          PP.ui.toast('DB: ' + res.db.database + ' / ' + res.db.user, res.db.password, 'warn', 15000);
        }
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.creating = false;
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
      try {
        await PP.api('sites/' + site.id + '/toggle', { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
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
        await PP.api('sites/' + this.domains.site.id + '/domains', {
          method: 'POST', body: { domain: this.domains.value.trim() },
        });
        this.domains.value = '';
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async removeDomain(alias) {
      try {
        await PP.api('sites/' + this.domains.site.id + '/domains/remove', {
          method: 'POST', body: { domain: alias },
        });
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
    async setPhp(site, version) {
      try {
        await PP.api('sites/' + site.id + '/php', { method: 'POST', body: { version: version || null } });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async setHttps(site, value) {
      try {
        await PP.api('sites/' + site.id + '/https', { method: 'POST', body: { force: value } });
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.load();
    },
    openSsl(site) {
      this.sslFor = site;
      PP.api('ssl').then(data => { this.sslList = data.certs; this.showSslPick = true; }).catch(e => PP.ui.error(PP.t('common.error'), e.message));
    },
    async deploySsl(certId) {
      try {
        await PP.api('sites/' + this.sslFor.id + '/ssl', { method: 'POST', body: { cert_id: certId } });
        this.showSslPick = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.sites') }}</h1>
      <span v-if="serverStatus" class="badge" :class="serverStatus.active ? 'green' : 'gray'">
        {{ serverStatus.server }}: {{ serverStatus.active ? 'active' : 'down' }}</span>
      <span class="spacer"></span>
      <button class="btn" @click="reloadServer">⟳ webserver</button>
      <button class="btn primary" @click="openCreate">+ {{ PP.t('sites.create') }}</button>
    </div>

    <p-table :cols="[
        { key: 'name', label: PP.t('sites.domain') },
        { key: 'server', label: 'Server', width: '90px' },
        { key: 'php', label: 'PHP', width: '90px' },
        { key: 'ssl', label: 'SSL', width: '110px' },
        { key: 'status', label: PP.t('common.status'), width: '110px' },
        { key: 'actions', label: PP.t('common.actions'), cls: 'actions' }]"
      :rows="sites">

      <template #col-name="{ row }">
        <div>
          <div class="mono">{{ row.name }}</div>
          <div class="small faint" v-if="row.aliases && row.aliases.length">{{ row.aliases.join(', ') }}</div>
        </div>
      </template>
      <template #col-php="{ row }">
        <select class="select" style="padding:3px 6px; font-size:12px" :value="row.php_version || ''"
                @change="setPhp(row, $event.target.value)">
          <option value="">—</option>
          <option v-for="v in phpVersions" :key="v.version" :value="v.version">{{ v.version }}</option>
        </select>
      </template>
      <template #col-ssl="{ row }">
        <span v-if="row.ssl" class="badge green">{{ row.ssl.issuer }}</span>
        <span v-else class="badge gray">—</span>
      </template>
      <template #col-status="{ row }">
        <p-switch :modelValue="row.enabled" @update:modelValue="toggle(row)"></p-switch>
      </template>
      <template #col-actions="{ row }">
        <button class="btn small" @click="openConf(row)">⚙</button>
        <button class="btn small" @click="openDomains(row)">🌐</button>
        <button class="btn small" @click="openProxy(row)">🔀</button>
        <button class="btn small" @click="openSsl(row)">🔒</button>
        <button class="btn small" @click="openLogs(row)">📜</button>
        <button class="btn small danger" @click="del(row)">🗑</button>
      </template>
    </p-table>

    <p-modal :open="showCreate" :title="PP.t('sites.create')" size="lg" @close="showCreate = false">
      <div class="form-row">
        <div class="field"><label>{{ PP.t('sites.domain') }}</label>
          <input class="input mono" v-model="form.domain" placeholder="example.com"></div>
        <div class="field"><label>{{ PP.t('sites.aliases') }} ({{ PP.t('common.optional') }})</label>
          <input class="input mono" v-model="form.aliases" placeholder="www.example.com, api.example.com"></div>
      </div>
      <div class="form-row">
        <div class="field"><label>Server</label>
          <select class="select" v-model="form.server">
            <option value="nginx">nginx</option><option value="apache">apache</option>
          </select></div>
        <div class="field"><label>{{ PP.t('sites.phpVersion') }}</label>
          <select class="select" v-model="form.php_version">
            <option value="">—</option>
            <option v-for="v in phpVersions" :key="v.version" :value="v.version">{{ v.version }}</option>
          </select></div>
      </div>
      <div class="checkbox-row mb">
        <p-switch v-model="form.withDb"></p-switch>
        <span>{{ PP.t('sites.withDb') }} (MySQL)</span>
      </div>
      <div class="form-row" v-if="form.withDb">
        <div class="field"><label>DB name</label><input class="input mono" v-model="form.db_name"></div>
        <div class="field"><label>DB user</label><input class="input mono" v-model="form.db_user"></div>
        <div class="field"><label>DB pass ({{ PP.t('common.optional') }})</label><input class="input mono" v-model="form.db_password"></div>
      </div>
      <template #foot>
        <button class="btn" @click="showCreate = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" :disabled="creating || !form.domain" @click="create">
          {{ creating ? '…' : PP.t('common.create') }}</button>
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
        <label>{{ PP.t('sites.noProxy') }} → {{ PP.t('sites.proxy') }} (http://127.0.0.1:3000)</label>
        <input class="input mono" v-model="proxy.target" placeholder="http://127.0.0.1:3000">
      </div>
      <template #foot>
        <button class="btn" @click="proxy.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="saveProxy">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="showSslPick" :title="PP.t('ssl.deploy')" @close="showSslPick = false">
      <div class="btn-row" v-if="sslList.length" style="flex-direction:column; align-items:stretch">
        <button v-for="c in sslList" :key="c.id" class="btn" @click="deploySsl(c.id)">
          {{ c.name }} <span class="faint small">({{ c.domain }})</span>
        </button>
      </div>
      <p v-else class="muted">—</p>
    </p-modal>
  </div>`,
};
