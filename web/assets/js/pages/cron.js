/* Cron page: scheduled tasks with schedule, run now, logs */
PP.pages = PP.pages || {};
PP.pages.cron = {
  data: () => ({
    jobs: [],
    show: false,
    form: { name: '', type: 'shell', schedule: '*/30 * * * *', command: '', enabled: true },
    editing: null,
    logModal: { open: false, name: '', text: '' },
  }),
  methods: {
    async load() {
      try { this.jobs = await PP.api('cron'); }
      catch (e) { PP.ui.warn(e.message); }
    },
    openCreate() {
      this.editing = null;
      this.form = { name: '', type: 'shell', schedule: '*/30 * * * *', command: '', enabled: true };
      this.show = true;
    },
    openEdit(job) {
      this.editing = job.id;
      this.form = { name: job.name, type: job.type, schedule: job.schedule, command: job.command, enabled: job.enabled };
      this.show = true;
    },
    async save() {
      if (!this.form.name) return;
      try {
        if (this.editing) {
          await PP.api('cron/' + this.editing + '/update', { method: 'POST', body: this.form });
        } else {
          await PP.api('cron', { method: 'POST', body: this.form });
        }
        this.show = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async toggle(job) {
      try {
        await PP.api('cron/' + job.id + '/toggle', { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async runNow(job) {
      try {
        const res = await PP.api('cron/' + job.id + '/run', { method: 'POST' });
        PP.ui.toast(res.ok ? 'OK' : 'FAILED', job.name, res.ok ? 'success' : 'error');
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async viewLog(job) {
      try {
        const data = await PP.api('cron/' + job.id + '/log');
        this.logModal = { open: true, name: job.name, text: data.log || '(empty)' };
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async del(job) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), job.name);
      if (!ok) return;
      try {
        await PP.api('cron/' + job.id + '/delete', { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    commandLabel(job) {
      if (job.type === 'url') return PP.t('cron.url');
      if (job.type === 'script') return PP.t('cron.script');
      return PP.t('cron.shell');
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.cron') }}</h1>
      <span class="spacer"></span>
      <button class="btn primary" @click="openCreate">+ {{ PP.t('cron.create') }}</button>
    </div>

    <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                     { key: 'schedule', label: PP.t('cron.schedule') },
                     { key: 'next_run', label: PP.t('common.nextRun') },
                     { key: 'last_status', label: PP.t('common.lastRun') },
                     { key: 'enabled', label: PP.t('common.status') },
                     { key: 'actions', label: '', cls: 'actions' }]" :rows="jobs">
      <template #col-name="{ row }">
        <span class="mono">{{ row.name }}</span>
        <span class="badge gray" style="margin-left:6px">{{ row.type }}</span>
        <div class="small faint mono">{{ row.command.slice(0, 60) }}</div>
      </template>
      <template #col-schedule="{ row }"><span class="mono">{{ row.schedule }}</span></template>
      <template #col-next_run="{ row }">{{ row.next_run ? PP.ui.fmtDate(row.next_run) : '—' }}</template>
      <template #col-last_status="{ row }">
        <span v-if="row.last_status" class="badge" :class="PP.ui.statusBadge(row.last_status)">{{ row.last_status }}</span>
        <span v-else class="faint">—</span>
      </template>
      <template #col-enabled="{ row }">
        <p-switch :modelValue="row.enabled" @update:modelValue="toggle(row)"></p-switch>
      </template>
      <template #col-actions="{ row }">
        <button class="btn small" @click="runNow(row)">▶</button>
        <button class="btn small" @click="viewLog(row)">📜</button>
        <button class="btn small" @click="openEdit(row)">✎</button>
        <button class="btn small danger" @click="del(row)">🗑</button>
      </template>
    </p-table>

    <p-modal :open="show" :title="editing ? PP.t('common.edit') : PP.t('cron.create')" @close="show = false">
      <div class="field"><label>{{ PP.t('common.name') }}</label>
        <input class="input" v-model="form.name"></div>
      <div class="form-row">
        <div class="field"><label>{{ PP.t('common.type') }}</label>
          <select class="select" v-model="form.type">
            <option value="shell">{{ PP.t('cron.shell') }}</option>
            <option value="url">{{ PP.t('cron.url') }}</option>
            <option value="script">{{ PP.t('cron.script') }}</option>
          </select></div>
        <div class="field"><label>{{ PP.t('cron.schedule') }}</label>
          <input class="input mono" v-model="form.schedule" placeholder="*/30 * * * *"></div>
      </div>
      <div class="field"><label>{{ commandLabelPlaceholder }}</label>
        <textarea class="input mono" v-model="form.command"
          :placeholder="form.type === 'url' ? 'https://example.com/cron' : '/bin/command --args'"
          style="min-height:80px"></textarea></div>
      <div class="checkbox-row"><p-switch v-model="form.enabled"></p-switch>
        <span>{{ PP.t('common.enabled') }}</span></div>
      <template #foot>
        <button class="btn" @click="show = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="save">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="logModal.open" :title="'log — ' + logModal.name" size="lg" @close="logModal.open = false">
      <div class="log-view">{{ logModal.text }}</div>
    </p-modal>
  </div>`,
  computed: {
    commandLabelPlaceholder() {
      return this.form.type === 'url' ? PP.t('cron.url') : this.form.type === 'script' ? PP.t('cron.script') : PP.t('cron.shell');
    },
  },
};
