/* Backup page: jobs, archives, run now, restore */
PP.pages = PP.pages || {};
PP.pages.backup = {
  data: () => ({
    jobs: [], runs: [], files: [], sites: [], databases: [],
    show: false,
    form: { name: '', sites: [], databases: [], schedule: '0 2 * * *', target: 'local', keep: 7, enabled: true },
    editing: null,
    restoreModal: { open: false, archive: '', members: [], member: '', dest: '' },
    sftpConfig: { host: '', port: 22, username: 'root', password: '', remote_dir: '/backups' },
  }),
  methods: {
    async load() {
      try {
        this.jobs = await PP.api('backup/jobs');
        this.runs = await PP.api('backup/runs');
        this.files = await PP.api('backup/files');
        this.sites = await PP.api('sites');
      } catch (e) { PP.ui.warn(e.message); }
    },
    openCreate() {
      this.editing = null;
      this.form = { name: '', sites: [], databases: [], schedule: '0 2 * * *', target: 'local', keep: 7, enabled: true };
      this.show = true;
    },
    openEdit(job) {
      this.editing = job.id;
      this.form = { ...job };
      this.show = true;
    },
    async save() {
      if (!this.form.name) return;
      const body = { ...this.form, target_config: this.form.target === 'sftp' ? this.sftpConfig : {} };
      try {
        if (this.editing) {
          await PP.api('backup/jobs/' + this.editing + '/update', { method: 'POST', body });
        } else {
          await PP.api('backup/jobs', { method: 'POST', body });
        }
        this.show = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async toggle(job) {
      try { await PP.api('backup/jobs/' + job.id + '/toggle', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async runNow(job) {
      try {
        const res = await PP.api('backup/jobs/' + job.id + '/run', { method: 'POST' });
        PP.ui.toast(res.status, res.filename, res.status === 'done' ? 'success' : 'error', 8000);
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async del(job) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), job.name);
      if (!ok) return;
      try { await PP.api('backup/jobs/' + job.id + '/delete', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    download(name) {
      window.open('/api/backup/download?name=' + encodeURIComponent(name), '_blank');
    },
    async openRestore(name) {
      try {
        const members = await PP.api('backup/archive-members', { params: { name } });
        this.restoreModal = { open: true, archive: name, members, member: members[0] || '', dest: this.sites.length ? this.sites[0].root : '/tmp' };
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async restore() {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), PP.t('backup.restore'));
      if (!ok) return;
      try {
        await PP.api('backup/restore', {
          method: 'POST',
          body: { archive: this.restoreModal.archive, member: this.restoreModal.member, dest: this.restoreModal.dest },
        });
        this.restoreModal.open = false;
        PP.ui.success(PP.t('backup.restore'));
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.backup') }}</h1>
      <span class="spacer"></span>
      <button class="btn primary" @click="openCreate">+ {{ PP.t('backup.jobs') }}</button>
    </div>

    <div class="card mb">
      <div class="card-title">{{ PP.t('backup.jobs') }}</div>
      <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                       { key: 'schedule', label: PP.t('cron.schedule') },
                       { key: 'target', label: PP.t('backup.targets') },
                       { key: 'last_status', label: PP.t('common.lastRun') },
                       { key: 'enabled', label: PP.t('common.status') },
                       { key: 'actions', label: '', cls: 'actions' }]" :rows="jobs">
        <template #col-name="{ row }">
          <span class="mono">{{ row.name }}</span>
          <div class="small faint">{{ (row.sites || []).length }} sites · {{ (row.databases || []).length }} dbs</div>
        </template>
        <template #col-schedule="{ row }"><span class="mono">{{ row.schedule }}</span></template>
        <template #col-last_status="{ row }">
          <span v-if="row.last_status" class="badge" :class="PP.ui.statusBadge(row.last_status)">{{ row.last_status }}</span>
          <span v-else class="faint">—</span>
        </template>
        <template #col-enabled="{ row }">
          <p-switch :modelValue="row.enabled" @update:modelValue="toggle(row)"></p-switch>
        </template>
        <template #col-actions="{ row }">
          <button class="btn small" @click="runNow(row)">▶ {{ PP.t('backup.runNow') }}</button>
          <button class="btn small" @click="openEdit(row)">✎</button>
          <button class="btn small danger" @click="del(row)">🗑</button>
        </template>
      </p-table>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <div class="card-title">{{ PP.t('backup.files') }}</div>
        <p-table :cols="[{ key: 'name', label: PP.t('common.name') }, { key: 'size', label: PP.t('common.size') },
                         { key: 'actions', label: '', cls: 'actions' }]" :rows="files">
          <template #col-name="{ row }"><span class="mono small">{{ row.name }}</span></template>
          <template #col-size="{ row }">{{ PP.ui.fmtBytes(row.size) }}</template>
          <template #col-actions="{ row }">
            <button class="btn small" @click="openRestore(row.name)">♻</button>
            <button class="btn small" @click="download(row.name)">⬇</button>
          </template>
        </p-table>
      </div>
      <div class="card">
        <div class="card-title">{{ PP.t('common.lastRun') }}</div>
        <p-table :cols="[{ key: 'filename', label: PP.t('common.name') }, { key: 'status', label: PP.t('common.status') },
                         { key: 'size', label: PP.t('common.size') }, { key: 'created_at', label: PP.t('common.modified') }]"
                 :rows="runs.slice(0, 15)">
          <template #col-filename="{ row }"><span class="mono small">{{ row.filename }}</span></template>
          <template #col-status="{ row }">
            <span class="badge" :class="PP.ui.statusBadge(row.status)">{{ row.status }}</span></template>
          <template #col-size="{ row }">{{ PP.ui.fmtBytes(row.size) }}</template>
          <template #col-created_at="{ row }">{{ PP.ui.fmtDate(row.created_at) }}</template>
        </p-table>
      </div>
    </div>

    <p-modal :open="show" :title="editing ? PP.t('common.edit') : PP.t('backup.jobs')" size="lg" @close="show = false">
      <div class="field"><label>{{ PP.t('common.name') }}</label>
        <input class="input" v-model="form.name"></div>
      <div class="field"><label>Sites</label>
        <select class="select" multiple v-model="form.sites" style="min-height:80px">
          <option v-for="s in sites" :key="s.name" :value="s.root">{{ s.name }}</option>
        </select></div>
      <div class="field"><label>Databases (mysql:dbname)</label>
        <input class="input mono" :value="(form.databases || []).join(', ')"
               @input="form.databases = $event.target.value.split(',').map(s => s.trim()).filter(Boolean)"></div>
      <div class="form-row">
        <div class="field"><label>{{ PP.t('cron.schedule') }}</label>
          <input class="input mono" v-model="form.schedule"></div>
        <div class="field"><label>{{ PP.t('backup.targets') }}</label>
          <select class="select" v-model="form.target">
            <option value="local">local</option>
            <option value="sftp">SFTP</option>
            <option value="rclone">rclone remote:</option>
          </select></div>
        <div class="field"><label>Retensi (jumlah)</label>
          <input class="input mono" type="number" v-model="form.keep"></div>
      </div>
      <div class="form-row" v-if="form.target === 'sftp'">
        <div class="field"><label>Host</label><input class="input mono" v-model="sftpConfig.host"></div>
        <div class="field"><label>User</label><input class="input mono" v-model="sftpConfig.username"></div>
        <div class="field"><label>{{ PP.t('common.password') }}</label>
          <input class="input mono" type="password" v-model="sftpConfig.password"></div>
      </div>
      <template #foot>
        <button class="btn" @click="show = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="save">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="restoreModal.open" :title="PP.t('backup.restore')" @close="restoreModal.open = false">
      <div class="field"><label>Member</label>
        <select class="select" v-model="restoreModal.member">
          <option v-for="m in restoreModal.members" :key="m" :value="m">{{ m }}</option>
        </select></div>
      <div class="field"><label>Dest</label>
        <input class="input mono" v-model="restoreModal.dest"></div>
      <template #foot>
        <button class="btn" @click="restoreModal.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn danger" @click="restore">{{ PP.t('backup.restore') }}</button>
      </template>
    </p-modal>
  </div>`,
};
