/* WAF: per-site nginx rules — CC limit, IP / user-agent blocklists */
PP.pages = PP.pages || {};
PP.pages.waf = {
  data: () => ({
    sites: [], profiles: {},
    form: { open: false, site_id: null, name: '', enabled: true, cc_rpm: 300,
            ipsText: '', uasText: '' },
  }),
  methods: {
    async load() {
      try {
        this.sites = await PP.api('sites');
        const data = await PP.api('waf');
        this.profiles = {};
        for (const p of data.profiles) this.profiles[p.site_id] = p;
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    profileOf(site) { return this.profiles[site.id]; },
    openForm(site) {
      const p = this.profileOf(site) || {};
      this.form = {
        open: true, site_id: site.id, name: site.name,
        enabled: p.enabled !== undefined ? p.enabled : true,
        cc_rpm: p.cc_rpm || 300,
        ipsText: (p.blocked_ips || []).join('\n'),
        uasText: (p.blocked_uas || []).join('\n'),
      };
    },
    async save() {
      const f = this.form;
      try {
        await PP.api('waf', {
          method: 'POST',
          body: {
            site_id: f.site_id, enabled: f.enabled, cc_rpm: Number(f.cc_rpm) || 300,
            blocked_ips: f.ipsText.split('\n').map(s => s.trim()).filter(Boolean),
            blocked_uas: f.uasText.split('\n').map(s => s.trim()).filter(Boolean),
          },
        });
        this.form.open = false;
        PP.ui.success(PP.t('waf.saved'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async removeProfile(site) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), site.name);
      if (!ok) return;
      try { await PP.api('waf/' + site.id + '/delete', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.waf') }}</h1>
    </div>
    <p class="small">{{ PP.t('waf.desc') }}</p>

    <p-table :cols="[{ key: 'name', label: PP.t('sites.domain') },
                     { key: 'server', label: 'Server' },
                     { key: 'waf', label: 'WAF' },
                     { key: 'cc', label: 'CC (r/m)' },
                     { key: 'rules', label: PP.t('waf.rules') },
                     { key: 'actions', label: '', cls: 'actions' }]" :rows="sites">
      <template #col-name="{ row }"><span class="mono">{{ row.name }}</span></template>
      <template #col-waf="{ row }">
        <span class="badge" :class="profileOf(row) && profileOf(row).enabled ? 'green' : 'gray'">
          {{ profileOf(row) ? (profileOf(row).enabled ? 'on' : 'off') : '—' }}</span>
      </template>
      <template #col-cc="{ row }">{{ profileOf(row) ? profileOf(row).cc_rpm : '—' }}</template>
      <template #col-rules="{ row }">
        <template v-if="profileOf(row)">
          {{ (profileOf(row).blocked_ips || []).length }} IP · {{ (profileOf(row).blocked_uas || []).length }} UA
        </template>
      </template>
      <template #col-actions="{ row }">
        <button class="btn small" @click="openForm(row)">✎</button>
        <button class="btn small danger" @click="removeProfile(row)">🗑</button>
      </template>
    </p-table>

    <p-modal :open="form.open" :title="'WAF — ' + form.name" @close="form.open = false">
      <div class="checkbox-row mb"><p-switch v-model="form.enabled"></p-switch><span>{{ PP.t('waf.enabled') }}</span></div>
      <div class="field"><label>CC limit ({{ PP.t('waf.reqPerMin') }})</label>
        <input class="input mono" type="number" min="10" v-model="form.cc_rpm"></div>
      <div class="field"><label>{{ PP.t('waf.blockedIps') }} (satu per baris)</label>
        <textarea class="input mono" v-model="form.ipsText" style="min-height:100px"
                  placeholder="203.0.113.10&#10;198.51.100.0"></textarea></div>
      <div class="field"><label>{{ PP.t('waf.blockedUas') }} (regex, satu per baris)</label>
        <textarea class="input mono" v-model="form.uasText" style="min-height:100px"
                  placeholder="sqlmap&#10nikto"></textarea></div>
      <template #foot>
        <button class="btn" @click="form.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="save">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
