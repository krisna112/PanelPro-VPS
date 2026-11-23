/* Security page: firewall, port rules, IP blocks, SSH port, fail2ban */
PP.pages = PP.pages || {};
PP.pages.security = {
  data: () => ({
    fw: null, pingBlocked: null, fail2ban: null,
    portForm: { port: 80, proto: 'tcp' },
    ipForm: { ip: '' },
    sshPort: 22, sshPortNew: 22,
  }),
  methods: {
    async load() {
      try {
        const data = await PP.api('security/status');
        this.fw = data.firewall;
        this.pingBlocked = data.ping_blocked;
        this.fail2ban = data.fail2ban;
        try { this.sshPort = (await PP.api('security/ssh-port')).port; this.sshPortNew = this.sshPort; } catch (e) {}
      } catch (e) { PP.ui.warn(e.message); }
    },
    async allowPort() {
      try {
        await PP.api('security/firewall/allow', { method: 'POST', body: this.portForm });
        PP.ui.success(PP.t('sec.allowPort'), this.portForm.port + '/' + this.portForm.proto);
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async removePort(raw) {
      const m = String(raw).match(/(\d+)\/(tcp|udp)/);
      if (!m) { PP.ui.warn('Ambiguous rule: edit via CLI'); return; }
      try {
        await PP.api('security/firewall/remove', { method: 'POST', body: { port: +m[1], proto: m[2] } });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async toggleFw() {
      try {
        await PP.api('security/firewall/' + (this.fw.active ? 'disable' : 'enable'), { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async blockIp() {
      if (!this.ipForm.ip) return;
      try {
        await PP.api('security/block', { method: 'POST', body: { ip: this.ipForm.ip.trim() } });
        this.ipForm.ip = '';
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async unblockIp(ip) {
      try {
        await PP.api('security/unblock', { method: 'POST', body: { ip } });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async setPing(value) {
      try {
        await PP.api('security/ping', { method: 'POST', body: { blocked: value } });
        this.pingBlocked = value;
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); this.load(); }
    },
    async saveSshPort() {
      const ok = await PP.ui.confirm(
        'sshd akan direstart dengan port baru ' + this.sshPortNew +
        '. Pastikan port sudah dibuka di firewall!', PP.t('sec.sshPort'));
      if (!ok) return;
      try {
        await PP.api('security/ssh-port', { method: 'POST', body: { port: this.sshPortNew } });
        PP.ui.success(PP.t('sec.sshPort'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head"><h1>{{ PP.t('menu.security') }}</h1>
      <span class="spacer"></span>
      <button class="btn" @click="load">⟳</button></div>

    <div class="grid cols-2">
      <div class="card">
        <div class="card-title">{{ PP.t('sec.firewall') }}
          <span class="badge" :class="fw && fw.active ? 'green' : 'gray'">{{ fw ? fw.tool : '?' }}</span>
          <span class="spacer"></span>
          <button class="btn small" :class="{ danger: fw && fw.active }" @click="toggleFw" v-if="fw && fw.tool">
            {{ fw.active ? PP.t('common.stop') : PP.t('common.start') }}</button>
        </div>
        <div class="form-row mb" v-if="fw && fw.tool">
          <div class="field"><label>Port</label><input class="input mono" type="number" v-model="portForm.port"></div>
          <div class="field"><label>Proto</label>
            <select class="select" v-model="portForm.proto">
              <option value="tcp">tcp</option><option value="udp">udp</option>
            </select></div>
          <div class="field"><label>&nbsp;</label>
            <button class="btn primary" @click="allowPort">+ {{ PP.t('sec.allowPort') }}</button></div>
        </div>
        <div class="log-view" style="max-height:260px" v-if="fw && fw.rules && fw.rules.length">
          <div v-for="(r, i) in fw.rules.slice(0, 60)" :key="i" class="flex">
            <span class="grow">{{ r.raw !== undefined ? r.raw : r }}</span>
            <button class="btn small danger" @click="removePort(r.raw !== undefined ? r.raw : r)">✕</button>
          </div>
        </div>
      </div>

      <div>
        <div class="card mb">
          <div class="card-title">{{ PP.t('sec.blockIp') }}</div>
          <div class="flex">
            <input class="input mono grow" v-model="ipForm.ip" placeholder="1.2.3.4" @keyup.enter="blockIp">
            <button class="btn danger" @click="blockIp">⛔</button>
          </div>
          <div class="log-view mt" style="max-height:160px">
            <div v-for="r in (fw && fw.rules ? fw.rules.filter(r => /deny|DROP|REJECT/.test(String(r.raw !== undefined ? r.raw : r))) : [])"
                 :key="r.raw" class="flex">
              <span class="grow">{{ r.raw }}</span>
              <button class="btn small" @click="unblockIp((r.raw.match(/from ([0-9.]+)/) || [])[1] || '')">🔓</button>
            </div>
          </div>
        </div>

        <div class="card mb">
          <div class="card-title">{{ PP.t('sec.sshPort') }}</div>
          <div class="flex">
            <span class="badge blue">{{ sshPort }}</span>
            <input class="input mono" style="width:110px" type="number" v-model="sshPortNew">
            <button class="btn" @click="saveSshPort">{{ PP.t('common.save') }}</button>
          </div>
        </div>

        <div class="card mb">
          <div class="card-title">{{ PP.t('sec.ping') }}</div>
          <div class="flex">
            <p-switch :modelValue="pingBlocked === true" @update:modelValue="setPing"></p-switch>
            <span class="small muted">{{ pingBlocked ? 'ICMP blocked' : 'ICMP allowed' }}</span>
          </div>
        </div>

        <div class="card">
          <div class="card-title">{{ PP.t('sec.fail2ban') }}
            <span class="badge" :class="fail2ban && fail2ban.installed ? 'green' : 'gray'">
              {{ fail2ban && fail2ban.installed ? fail2ban.jails.length + ' jails' : 'not installed' }}</span>
          </div>
          <div class="small faint" v-if="fail2ban && fail2ban.installed">{{ fail2ban.jails.join(', ') }}</div>
        </div>
      </div>
    </div>
  </div>`,
};
