/* SSL page: cert list, Let's Encrypt, self-signed, custom upload, renew */
PP.pages = PP.pages || {};
PP.pages.ssl = {
  data: () => ({
    certs: [], certbot: false, sites: [],
    le: { open: false, form: { domain: '', aliases: '', webroot: '', email: '', site_id: null, auto_renew: true, challenge: 'webroot', dns_account_id: null } },
    ss: { open: false, form: { domain: '', days: 3650 } },
    custom: { open: false, form: { name: '', cert: '', key: '' } },
    dns: { open: false, accounts: [], providers: [], form: { name: '', provider: 'cloudflare', config: {} } },
  }),
  methods: {
    async load() {
      try {
        const data = await PP.api('ssl');
        this.certs = data.certs;
        this.certbot = data.certbot_available;
        this.sites = await PP.api('sites');
      } catch (e) { PP.ui.warn(e.message); }
    },
    async loadDns() {
      try {
        const data = await PP.api('ssl/dns-accounts');
        this.dns.accounts = data.accounts;
        this.dns.providers = data.providers;
        if (!this.dns.accounts.map(a => a.id).includes(this.le.form.dns_account_id)) {
          this.le.form.dns_account_id = null;
        }
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async openDnsAccounts() { this.dns.open = true; this.loadDns(); },
    async addDnsAccount() {
      try {
        await PP.api('ssl/dns-accounts', { method: 'POST', body: this.dns.form });
        this.dns.form = { name: '', provider: 'cloudflare', config: {} };
        PP.ui.success(PP.t('ssl.dnsAccounts'));
        this.loadDns();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async delDnsAccount(row) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), row.name);
      if (!ok) return;
      try {
        await PP.api('ssl/dns-accounts/' + row.id + '/delete', { method: 'POST' });
        this.loadDns();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    providerFields() {
      const map = {
        cloudflare: ['api_token'],
        digitalocean: ['token'],
        dnspod: ['id', 'token'],
        aliyun: ['access_key_id', 'access_key_secret'],
        godaddy: ['key', 'secret'],
      };
      return map[this.dns.form.provider] || [];
    },
    async issueLE() {
      const f = this.le.form;
      if (!f.domain) return;
      if (f.challenge === 'webroot' && !f.webroot) return;
      if (f.challenge === 'dns' && !f.dns_account_id) return;
      try {
        const body = {
          ...f,
          aliases: f.aliases.split(',').map(s => s.trim()).filter(Boolean),
        };
        if (f.challenge === 'dns') body.webroot = '';
        const res = await PP.api('ssl/letsencrypt', { method: 'POST', body });
        this.le.open = false;
        this.le.form = { domain: '', aliases: '', webroot: '', email: '', site_id: null, auto_renew: true, challenge: 'webroot', dns_account_id: null };
        PP.ui.success(PP.t('ssl.letsencrypt'), res.cert.domain);
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async issueSS() {
      const f = this.ss.form;
      if (!f.domain) return;
      try {
        await PP.api('ssl/selfsigned', { method: 'POST', body: f });
        this.ss.open = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async uploadCustom() {
      try {
        await PP.api('ssl/custom', { method: 'POST', body: this.custom.form });
        this.custom.open = false;
        this.custom.form = { name: '', cert: '', key: '' };
        PP.ui.success(PP.t('ssl.custom'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async del(row) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), row.name);
      if (!ok) return;
      try {
        await PP.api('ssl/' + row.id + '/delete', { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async renewAll() {
      try {
        await PP.api('ssl/renew', { method: 'POST' });
        PP.ui.success(PP.t('ssl.renew'));
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async deploy(row, siteId) {
      if (!siteId) return;
      try {
        await PP.api('ssl/' + row.id + '/deploy', { method: 'POST', body: { site_id: siteId } });
        PP.ui.success(PP.t('ssl.deploy'));
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.ssl') }}</h1>
      <span class="badge" :class="certbot ? 'green' : 'amber'">certbot {{ certbot ? '✓' : '✕' }}</span>
      <span class="spacer"></span>
      <button class="btn" @click="renewAll">⟳ {{ PP.t('ssl.renew') }}</button>
      <button class="btn" @click="openDnsAccounts">🔑 {{ PP.t('ssl.dnsAccounts') }}</button>
      <button class="btn" @click="ss.open = true">+ {{ PP.t('ssl.selfsigned') }}</button>
      <button class="btn" @click="custom.open = true">+ {{ PP.t('ssl.custom') }}</button>
      <button class="btn primary" @click="le.open = true">+ {{ PP.t('ssl.letsencrypt') }}</button>
    </div>

    <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                     { key: 'domain', label: PP.t('sites.domain') },
                     { key: 'issuer', label: 'Issuer' },
                     { key: 'not_after', label: 'Expires' },
                     { key: 'days_left', label: PP.t('ssl.days') },
                     { key: 'deploy', label: PP.t('ssl.deploy') },
                     { key: 'actions', label: '', cls: 'actions' }]" :rows="certs">
      <template #col-name="{ row }"><span class="mono">{{ row.name }}</span>
        <span class="badge blue" style="margin-left:6px">{{ row.source }}</span></template>
      <template #col-not_after="{ row }">{{ PP.ui.fmtDate(row.not_after) }}</template>
      <template #col-days_left="{ row }">
        <span class="badge" :class="row.days_left <= 7 ? 'red' : row.days_left <= 30 ? 'amber' : 'green'">
          {{ row.days_left }} {{ PP.t('ssl.days') }}</span>
      </template>
      <template #col-deploy="{ row }">
        <select class="select" style="padding:4px 8px; font-size:12px" @change="deploy(row, $event.target.value)">
          <option value="">→ situs…</option>
          <option v-for="s in sites" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </template>
      <template #col-actions="{ row }">
        <button class="btn small danger" @click="del(row)">🗑</button>
      </template>
    </p-table>

    <p-modal :open="le.open" :title="PP.t('ssl.letsencrypt')" @close="le.open = false">
      <div class="field"><label>{{ PP.t('sites.domain') }} (wildcard: *.contoh.com)</label>
        <input class="input mono" v-model="le.form.domain"></div>
      <div class="field"><label>{{ PP.t('sites.aliases') }} ({{ PP.t('common.optional') }})</label>
        <input class="input mono" v-model="le.form.aliases"></div>
      <div class="field"><label>{{ PP.t('ssl.challenge') }}</label>
        <select class="select" v-model="le.form.challenge" @change="le.form.dns_account_id = null">
          <option value="webroot">HTTP-01 (webroot)</option>
          <option value="dns">DNS-01 · {{ PP.t('ssl.dnsChallenge') }}</option>
        </select></div>
      <div class="field" v-if="le.form.challenge === 'webroot'"><label>Webroot</label>
        <input class="input mono" v-model="le.form.webroot" placeholder="/www/wwwroot/example.com"></div>
      <div class="field" v-if="le.form.challenge === 'dns'"><label>{{ PP.t('ssl.dnsAccounts') }}</label>
        <select class="select" v-model="le.form.dns_account_id">
          <option :value="null">—</option>
          <option v-for="a in dns.accounts" :key="a.id" :value="a.id">{{ a.name }} ({{ a.provider }})</option>
        </select>
        <p class="small" style="margin-top:6px">
          {{ PP.t('ssl.dnsAdd') }} → tombol "🔑 {{ PP.t('ssl.dnsAccounts') }}" di atas.
        </p></div>
      <div class="field"><label>Email ({{ PP.t('common.optional') }})</label>
        <input class="input mono" v-model="le.form.email"></div>
      <div class="field"><label>Deploy ke situs ({{ PP.t('common.optional') }})</label>
        <select class="select" v-model="le.form.site_id">
          <option :value="null">—</option>
          <option v-for="s in sites" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select></div>
      <div class="checkbox-row mb"><p-switch v-model="le.form.auto_renew"></p-switch>
        <span>auto-renew</span></div>
      <template #foot>
        <button class="btn" @click="le.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="issueLE">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="dns.open" :title="PP.t('ssl.dnsAccounts')" @close="dns.open = false">
      <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                       { key: 'provider', label: PP.t('ssl.dnsProvider') },
                       { key: 'actions', label: '', cls: 'actions' }]" :rows="dns.accounts">
        <template #col-actions="{ row }">
          <button class="btn small danger" @click="delDnsAccount(row)">🗑</button>
        </template>
      </p-table>
      <div class="card mt" style="background:var(--bg-2)">
        <div class="field"><label>{{ PP.t('common.name') }}</label>
          <input class="input mono" v-model="dns.form.name" placeholder="Cloudflare utama"></div>
        <div class="field"><label>{{ PP.t('ssl.dnsProvider') }}</label>
          <select class="select" v-model="dns.form.provider">
            <option v-for="p in dns.providers" :key="p" :value="p">{{ p }}</option>
          </select></div>
        <div class="field" v-for="field in providerFields()" :key="field">
          <label>{{ field }}</label>
          <input class="input mono" type="password" v-model="dns.form.config[field]">
        </div>
        <button class="btn primary" @click="addDnsAccount">+ {{ PP.t('ssl.dnsAdd') }}</button>
      </div>
      <template #foot>
        <button class="btn" @click="dns.open = false">{{ PP.t('common.cancel') }}</button>
      </template>
    </p-modal>

    <p-modal :open="ss.open" :title="PP.t('ssl.selfsigned')" @close="ss.open = false">
      <div class="field"><label>{{ PP.t('sites.domain') }}</label>
        <input class="input mono" v-model="ss.form.domain"></div>
      <div class="field"><label>Hari valid</label>
        <input class="input mono" v-model="ss.form.days"></div>
      <template #foot>
        <button class="btn primary" @click="issueSS">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="custom.open" :title="PP.t('ssl.custom')" size="lg" @close="custom.open = false">
      <div class="field"><label>{{ PP.t('common.name') }}</label>
        <input class="input mono" v-model="custom.form.name"></div>
      <div class="field"><label>Certificate (PEM)</label>
        <textarea class="input mono" v-model="custom.form.cert" style="min-height:130px"></textarea></div>
      <div class="field"><label>Private key (PEM)</label>
        <textarea class="input mono" v-model="custom.form.key" style="min-height:130px"></textarea></div>
      <template #foot>
        <button class="btn primary" @click="uploadCustom">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
