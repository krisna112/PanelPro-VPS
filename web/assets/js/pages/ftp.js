/* FTP page: account management (pure-ftpd / proftpd) */
PP.pages = PP.pages || {};
PP.pages.ftp = {
  data: () => ({
    backend: null, users: [],
    show: false, form: { name: '', password: '', directory: '' },
    passModal: { open: false, user: null, password: '' },
  }),
  methods: {
    async load() {
      try {
        const data = await PP.api('ftp');
        this.backend = data.backend;
        this.users = data.users;
      } catch (e) { PP.ui.warn(e.message); }
    },
    async create() {
      if (!this.form.name || !this.form.directory) return;
      if (this.form.password.length < 8) {
        PP.ui.error(PP.t('common.password'), 'min. 8 chars');
        return;
      }
      try {
        await PP.api('ftp', { method: 'POST', body: this.form });
        this.show = false;
        this.form = { name: '', password: '', directory: '' };
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async del(row) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), row.name);
      if (!ok) return;
      try {
        await PP.api('ftp/' + row.id + '/delete', { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async savePassword() {
      try {
        await PP.api('ftp/' + this.passModal.user.id + '/password', {
          method: 'POST', body: { password: this.passModal.password },
        });
        this.passModal.open = false;
        PP.ui.success(PP.t('common.save'));
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.ftp') }}</h1>
      <span v-if="backend" class="badge blue">{{ backend }}</span>
      <span v-else class="badge amber">no FTP server installed</span>
      <span class="spacer"></span>
      <button class="btn primary" v-if="backend" @click="show = true">+ {{ PP.t('common.create') }}</button>
    </div>

    <p-table :cols="[{ key: 'name', label: PP.t('common.username') },
                     { key: 'directory', label: PP.t('sites.root') },
                     { key: 'backend', label: 'Backend' },
                     { key: 'actions', label: '', cls: 'actions' }]" :rows="users">
      <template #col-name="{ row }"><span class="mono">{{ row.name }}</span></template>
      <template #col-directory="{ row }"><span class="mono small">{{ row.directory }}</span></template>
      <template #col-actions="{ row }">
        <button class="btn small" @click="passModal = { open: true, user: row, password: '' }">🔑</button>
        <button class="btn small danger" @click="del(row)">🗑</button>
      </template>
    </p-table>

    <p-modal :open="show" :title="PP.t('common.create')" @close="show = false">
      <div class="field"><label>{{ PP.t('common.username') }}</label>
        <input class="input mono" v-model="form.name"></div>
      <div class="field"><label>{{ PP.t('common.password') }}</label>
        <input class="input mono" v-model="form.password"></div>
      <div class="field"><label>{{ PP.t('sites.root') }}</label>
        <input class="input mono" v-model="form.directory" placeholder="/www/wwwroot/example.com"></div>
      <template #foot>
        <button class="btn" @click="show = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="create">{{ PP.t('common.create') }}</button>
      </template>
    </p-modal>

    <p-modal :open="passModal.open" :title="PP.t('common.password') + ' — ' + (passModal.user ? passModal.user.name : '')" @close="passModal.open = false">
      <div class="field"><label>{{ PP.t('common.password') }}</label>
        <input class="input mono" v-model="passModal.password"></div>
      <template #foot>
        <button class="btn" @click="passModal.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="savePassword">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
