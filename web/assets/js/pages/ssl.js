/* SSL page: cert list, Let's Encrypt, self-signed, custom upload, renew */
PP.pages = PP.pages || {};
PP.pages.ssl = {
  data: () => ({
    certs: [], certbot: false, sites: [],
    le: { open: false, form: { domain: '', aliases: '', webroot: '', email: '', site_id: null, auto_renew: true } },
    ss: { open: false, form: { domain: '', days: 3650 } },
    custom: { open: false, form: { name: '', cert: '', key: '' } },
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
    async issueLE() {
      const f = this.le.form;
      if (!f.domain || !f.webroot) return;
      try {
        const res = await PP.api('ssl/letsencrypt', {
          method: 'POST',
          body: { ...f, aliases: f.aliases.split(',').map(s => s.trim()).filter(Boolean) },
        });
        this.le.open = false;
        this.le.form = { domain: '', aliases: '', webroot: '', email: '', site_id: null, auto_renew: true };
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
      <div class="field"><label>{{ PP.t('sites.domain') }}</label>
        <input class="input mono" v-model="le.form.domain"></div>
      <div class="field"><label>{{ PP.t('sites.aliases') }} ({{ PP.t('common.optional') }})</label>
        <input class="input mono" v-model="le.form.aliases"></div>
      <div class="field"><label>Webroot</label>
        <input class="input mono" v-model="le.form.webroot" placeholder="/www/wwwroot/example.com"></div>
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
