/* Daemon Guard: keep services/ports/pidfiles alive with auto-restart */
PP.pages = PP.pages || {};
PP.pages.daemon = {
  data: () => ({
    tasks: [], kinds: [],
    form: { open: false, id: null, name: '', kind: 'systemd', target: '', restart_cmd: '', check_interval: 60, enabled: true },
    testing: false,
  }),
  methods: {
    async load() {
      try {
        const data = await PP.api('daemon');
        this.tasks = data.tasks;
        this.kinds = data.kinds;
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    openForm(row) {
      this.form = row
        ? { open: true, id: row.id, name: row.name, kind: row.kind, target: row.target,
            restart_cmd: row.restart_cmd || '', check_interval: row.check_interval, enabled: row.enabled }
        : { open: true, id: null, name: '', kind: 'systemd', target: '', restart_cmd: '', check_interval: 60, enabled: true };
    },
    async save() {
      const f = this.form;
      if (!f.name || !f.target) return;
      try {
        const body = { name: f.name, kind: f.kind, target: f.target, restart_cmd: f.restart_cmd,
                       check_interval: Number(f.check_interval) || 60, enabled: f.enabled };
        await PP.api('daemon' + (f.id ? '/' + f.id + '/update' : ''), { method: 'POST', body });
        this.form.open = false;
        PP.ui.success(PP.t('common.save'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async toggle(row) {
      try { await PP.api('daemon/' + row.id + '/toggle', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async runNow(row) {
      this.testing = true;
      try {
        await PP.api('daemon/' + row.id + '/run-now', { method: 'POST' });
        PP.ui.success(PP.t('daemon.checked'), row.name);
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.testing = false;
    },
    async del(row) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), row.name);
      if (!ok) return;
      try { await PP.api('daemon/' + row.id + '/delete', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    statusBadge(row) {
      const s = row.last_status || 'unknown';
      return s === 'up' ? 'green' : s === 'restarted' ? 'amber' : s === 'down' ? 'red' : 'gray';
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.daemon') }}</h1>
      <span class="spacer"></span>
      <button class="btn primary" @click="openForm(null)">+ {{ PP.t('daemon.add') }}</button>
    </div>
    <p class="small">{{ PP.t('daemon.desc') }}</p>

    <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                     { key: 'kind', label: PP.t('daemon.kind') },
                     { key: 'target', label: PP.t('daemon.target') },
                     { key: 'status', label: PP.t('daemon.status') },
                     { key: 'restarts', label: PP.t('daemon.restarts') },
                     { key: 'interval', label: PP.t('daemon.interval') },
                     { key: 'actions', label: '', cls: 'actions' }]" :rows="tasks">
      <template #col-name="{ row }"><span class="mono">{{ row.name }}</span></template>
      <template #col-target="{ row }"><span class="mono small">{{ row.target }}</span></template>
      <template #col-status="{ row }">
        <span class="badge" :class="statusBadge(row)">{{ row.last_status || '—' }}</span>
        <span class="badge gray" v-if="!row.enabled">{{ PP.t('daemon.disabled') }}</span>
      </template>
      <template #col-restarts="{ row }">{{ row.restart_count }}</template>
      <template #col-interval="{ row }">{{ row.check_interval }}s</template>
      <template #col-actions="{ row }">
        <button class="btn small" @click="runNow(row)" :disabled="testing">▶</button>
        <button class="btn small" @click="toggle(row)">{{ row.enabled ? '⏸' : '▶' }}</button>
        <button class="btn small" @click="openForm(row)">✎</button>
        <button class="btn small danger" @click="del(row)">🗑</button>
      </template>
    </p-table>

    <p-modal :open="form.open" :title="form.id ? PP.t('daemon.edit') : PP.t('daemon.add')" @close="form.open = false">
      <div class="field"><label>{{ PP.t('common.name') }}</label>
        <input class="input mono" v-model="form.name"></div>
      <div class="field"><label>{{ PP.t('daemon.kind') }}</label>
        <select class="select" v-model="form.kind">
          <option v-for="k in kinds" :key="k" :value="k">{{ k }}</option>
        </select></div>
      <div class="field"><label>{{ PP.t('daemon.target') }}
        <span class="small">— systemd: nginx.service · pidfile: /var/run/x.pid · port: 127.0.0.1:80 · command: systemctl is-active nginx</span></label>
        <input class="input mono" v-model="form.target"></div>
      <div class="field"><label>{{ PP.t('daemon.restartCmd') }} ({{ PP.t('common.optional') }}, non-systemd)</label>
        <input class="input mono" v-model="form.restart_cmd" placeholder="systemctl start myapp || /usr/bin/myapp &"></div>
      <div class="field"><label>{{ PP.t('daemon.interval') }} (detik)</label>
        <input class="input mono" type="number" min="10" v-model="form.check_interval"></div>
      <div class="checkbox-row mb"><p-switch v-model="form.enabled"></p-switch><span>{{ PP.t('daemon.enabled') }}</span></div>
      <template #foot>
        <button class="btn" @click="form.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="save">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
