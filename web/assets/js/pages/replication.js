/* MySQL replication: master/slave setup wizard + live status (admin) */
PP.pages = PP.pages || {};
PP.pages.replication = {
  data: () => ({
    status: null,
    slaveForm: { open: false, master_host: '', master_port: 3306, repl_user: 'panelpro_repl', repl_password: '' },
    masterResult: null,
  }),
  methods: {
    async load() {
      try { this.status = await PP.api('replication/status'); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async setupMaster() {
      try {
        this.masterResult = await PP.api('replication/setup-master', { method: 'POST' });
        PP.ui.success(PP.t('repl.masterReady'), this.masterResult.repl_user);
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    openSlave() {
      const m = this.masterResult;
      this.slaveForm = { open: true, master_host: '', master_port: 3306,
        repl_user: m ? m.repl_user : 'panelpro_repl',
        repl_password: m ? m.repl_password : '' };
    },
    async setupSlave() {
      const f = this.slaveForm;
      if (!f.master_host || !f.repl_user || !f.repl_password) return;
      try {
        await PP.api('replication/setup-slave', { method: 'POST', body: { ...f, master_port: Number(f.master_port) || 3306 } });
        this.slaveForm.open = false;
        PP.ui.success(PP.t('repl.slaveStarted'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async stopSlave() {
      const ok = await PP.ui.confirm(PP.t('repl.stopConfirm'), '');
      if (!ok) return;
      try { await PP.api('replication/stop-slave', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.replication') }}</h1>
      <span class="badge" :class="status && status.available ? 'green' : 'red'">
        MySQL {{ status && status.available ? '✓' : '✕' }}</span>
    </div>
    <p class="small">{{ PP.t('repl.desc') }}</p>

    <div class="grid cols-2" v-if="status">
      <div class="card">
        <h3>{{ PP.t('repl.master') }}</h3>
        <p class="small">binlog: <span class="badge" :class="status.master_configured ? 'green' : 'amber'">
          {{ status.master_configured ? 'on' : 'off' }}</span></p>
        <p class="mono small" v-if="status.master_status">
          file: {{ status.master_status.file }} · pos: {{ status.master_status.position }}</p>
        <p class="small" v-if="status.has_repl_password">{{ PP.t('repl.userExists') }}: <span class="mono">{{ status.repl_user }}</span></p>
        <button class="btn primary" @click="setupMaster" :disabled="!status.available">{{ PP.t('repl.setupMaster') }}</button>
        <div class="card mt" style="background:var(--bg-2)" v-if="masterResult">
          <p class="small">{{ PP.t('repl.copyCreds') }}</p>
          <p class="mono small">user: {{ masterResult.repl_user }}</p>
          <p class="mono small">password: {{ masterResult.repl_password }}</p>
        </div>
      </div>

      <div class="card">
        <h3>{{ PP.t('repl.slave') }}</h3>
        <template v-if="status.slave_status">
          <p class="small">
            <span class="badge" :class="status.slave_status.running ? 'green' : 'red'">
              {{ status.slave_status.running ? 'running' : 'stopped' }}</span>
            master: {{ status.slave_status.master_host }}
            · {{ PP.t('repl.lag') }}: {{ status.slave_status.seconds_behind }}s
          </p>
          <p class="mono small red" v-if="status.slave_status.last_error">{{ status.slave_status.last_error }}</p>
          <button class="btn danger" @click="stopSlave">{{ PP.t('repl.stopSlave') }}</button>
        </template>
        <template v-else>
          <p class="small">{{ PP.t('repl.notSlave') }}</p>
        </template>
        <button class="btn primary mt" @click="openSlave" :disabled="!status.available">+ {{ PP.t('repl.setupSlave') }}</button>
      </div>
    </div>

    <p-modal :open="slaveForm.open" :title="PP.t('repl.setupSlave')" @close="slaveForm.open = false">
      <div class="field"><label>Master host</label>
        <input class="input mono" v-model="slaveForm.master_host" placeholder="192.168.1.10"></div>
      <div class="field"><label>Master port</label>
        <input class="input mono" type="number" v-model="slaveForm.master_port"></div>
      <div class="field"><label>{{ PP.t('repl.user') }}</label>
        <input class="input mono" v-model="slaveForm.repl_user"></div>
      <div class="field"><label>{{ PP.t('repl.password') }}</label>
        <input class="input mono" type="password" v-model="slaveForm.repl_password"></div>
      <template #foot>
        <button class="btn" @click="slaveForm.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="setupSlave">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
