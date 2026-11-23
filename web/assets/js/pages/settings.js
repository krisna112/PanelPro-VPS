/* Settings page: general, panel security, 2FA, sessions, panel SSL */
PP.pages = PP.pages || {};
PP.pages.settings = {
  data: () => ({
    tab: 'general',
    settings: {},
    entry: '', port: '', diskThreshold: 90, cpuThreshold: 85,
    twofa: { enabled: false, secret: '', uri: '', qr_svg: '', code: '' },
    sessions: [],
    panelSsl: { cert: '', key: '', enabled: false },
    pwd: { current: '', new: '' },
  }),
  methods: {
    async load() {
      try {
        this.settings = await PP.api('settings');
        this.entry = this.settings.entry_path || '';
        this.port = this.settings.panel_port || '';
        this.diskThreshold = this.settings.threshold_disk || 90;
        this.cpuThreshold = this.settings.threshold_cpu || 85;
        const me = await PP.api('auth/me');
        this.twofa.enabled = me.totp_enabled;
        if (me.totp_enabled) this.loadSessions();
      } catch (e) { PP.ui.warn(e.message); }
    },
    async saveKey(key, value) {
      try {
        const res = await PP.api('settings', { method: 'POST', body: { key, value } });
        if (res.note) PP.ui.toast(PP.t('common.save'), res.note, 'info', 8000);
        else PP.ui.success(PP.t('common.save'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async setup2fa() {
      try {
        const data = await PP.api('auth/2fa/setup', { method: 'POST' });
        this.twofa.secret = data.secret;
        this.twofa.uri = data.uri;
        this.twofa.qr_svg = data.qr_svg || '';
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async enable2fa() {
      try {
        await PP.api('auth/2fa/enable', { method: 'POST', body: { code: this.twofa.code } });
        PP.ui.success('2FA enabled');
        this.twofa = { enabled: true, secret: '', uri: '', qr_svg: '', code: '' };
        this.loadSessions();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async disable2fa() {
      try {
        await PP.api('auth/2fa/disable', { method: 'POST', body: { code: this.twofa.code } });
        PP.ui.success('2FA disabled');
        this.twofa = { enabled: false, secret: '', uri: '', qr_svg: '', code: '' };
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async loadSessions() {
      try { this.sessions = await PP.api('auth/sessions'); }
      catch (e) { /* ignore */ }
    },
    async revoke(session) {
      try { await PP.api('auth/sessions/' + session.id, { method: 'DELETE' }); this.loadSessions(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async revokeOthers() {
      try { await PP.api('auth/sessions/revoke-others', { method: 'POST' }); this.loadSessions(); PP.ui.success('OK'); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async savePanelSsl() {
      try {
        await PP.api('settings/panel-ssl', { method: 'POST', body: { cert: this.panelSsl.cert, key: this.panelSsl.key } });
        PP.ui.success(PP.t('settings.panelSsl'));
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async changePassword() {
      try {
        await PP.api('auth/password', { method: 'POST', body: { current: this.pwd.current, new: this.pwd.new } });
        PP.ui.success(PP.t('common.save'));
        setTimeout(() => { location.reload(); }, 1200);
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <p-tabs v-model="tab" :tabs="[
      { key: 'general', label: PP.t('settings.general') },
      { key: 'security', label: PP.t('settings.security') },
      { key: 'twofa', label: PP.t('settings.2fa') },
      { key: 'sessions', label: PP.t('settings.sessions') }]"></p-tabs>

    <div v-if="tab === 'general'" class="grid cols-2">
      <div class="card">
        <div class="card-title">{{ PP.t('settings.port') }}</div>
        <div class="flex">
          <input class="input mono" style="width:130px" v-model="port">
          <button class="btn primary" @click="saveKey('panel_port', +port)">{{ PP.t('common.save') }}</button>
        </div>
        <div class="small faint mt">{{ PP.t('settings.portNote') }}</div>
      </div>
      <div class="card">
        <div class="card-title">{{ PP.t('thresholds') }}</div>
        <div class="form-row">
          <div class="field"><label>Disk %</label>
            <input class="input mono" type="number" v-model="diskThreshold"></div>
          <div class="field"><label>CPU %</label>
            <input class="input mono" type="number" v-model="cpuThreshold"></div>
        </div>
        <button class="btn primary" @click="saveKey('threshold_disk', +diskThreshold); saveKey('threshold_cpu', +cpuThreshold)">
          {{ PP.t('common.save') }}</button>
      </div>
      <div class="card">
        <div class="card-title">{{ PP.t('common.password') }}</div>
        <div class="field"><label>current</label>
          <input class="input mono" type="password" v-model="pwd.current"></div>
        <div class="field"><label>new (min 8)</label>
          <input class="input mono" type="password" v-model="pwd.new"></div>
        <button class="btn primary" @click="changePassword">{{ PP.t('common.save') }}</button>
      </div>
    </div>

    <div v-if="tab === 'security'" class="grid cols-2">
      <div class="card">
        <div class="card-title">{{ PP.t('settings.entry') }}</div>
        <div class="flex">
          <span class="mono">/</span>
          <input class="input mono grow" v-model="entry">
          <button class="btn primary" @click="saveKey('entry_path', entry)">{{ PP.t('common.save') }}</button>
        </div>
        <div class="small faint mt">{{ PP.t('settings.entryNote') }}</div>
      </div>
      <div class="card">
        <div class="card-title">{{ PP.t('settings.panelSsl') }}</div>
        <div class="field"><label>Certificate (PEM)</label>
          <textarea class="input mono" v-model="panelSsl.cert" style="min-height:110px"></textarea></div>
        <div class="field"><label>Private key (PEM)</label>
          <textarea class="input mono" v-model="panelSsl.key" style="min-height:110px"></textarea></div>
        <button class="btn primary" @click="savePanelSsl">{{ PP.t('common.save') }}</button>
        <div class="small faint mt">Restart panel service untuk aktif.</div>
      </div>
    </div>

    <div v-if="tab === 'twofa'" class="grid cols-2">
      <div class="card">
        <div class="card-title">{{ PP.t('settings.2fa') }}
          <span class="badge" :class="twofa.enabled ? 'green' : 'gray'">{{ twofa.enabled ? 'on' : 'off' }}</span>
        </div>
        <template v-if="!twofa.enabled">
          <button class="btn primary mb" @click="setup2fa">{{ PP.t('settings.2faSetup') }}</button>
          <template v-if="twofa.secret">
            <div class="small mono mb" style="word-break:break-all">{{ twofa.secret }}</div>
            <div v-if="twofa.qr_svg" class="mb" style="background:#fff; padding:10px; border-radius:8px; width:180px"
                 v-html="twofa.qr_svg"></div>
            <div class="field"><label>Kode OTP</label>
              <input class="input mono" v-model="twofa.code" inputmode="numeric"></div>
            <button class="btn primary" @click="enable2fa">enable</button>
          </template>
        </template>
        <template v-else>
          <div class="field"><label>Kode OTP</label>
            <input class="input mono" v-model="twofa.code" inputmode="numeric"></div>
          <button class="btn danger" @click="disable2fa">{{ PP.t('settings.2faDisable') }}</button>
        </template>
      </div>
    </div>

    <div v-if="tab === 'sessions'" class="card">
      <div class="card-title">{{ PP.t('settings.sessions') }}
        <span class="spacer"></span>
        <button class="btn small" @click="revokeOthers">revoke others</button>
      </div>
      <p-table :cols="[{ key: 'ip', label: 'IP' }, { key: 'user_agent', label: 'User agent' },
                       { key: 'created_at', label: 'Created' }, { key: 'actions', label: '', cls: 'actions' }]"
               :rows="sessions">
        <template #col-user_agent="{ row }"><span class="small">{{ (row.user_agent || '').slice(0, 60) }}</span></template>
        <template #col-created_at="{ row }">{{ PP.ui.fmtDate(row.created_at) }}</template>
        <template #col-actions="{ row }">
          <button class="btn small danger" v-if="!row.current" @click="revoke(row)">✕</button>
          <span class="badge green" v-else>this</span>
        </template>
      </p-table>
    </div>
  </div>`,
};
