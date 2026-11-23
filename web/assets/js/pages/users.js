/* Users & API keys page (admin) */
PP.pages = PP.pages || {};
PP.pages.users = {
  data: () => ({
    users: [], keys: [],
    showUser: false, editing: null,
    userForm: { username: '', password: '', role: 'operator' },
    showKey: false, keyForm: { name: '', role: 'operator' },
    newKey: '',
  }),
  methods: {
    async load() {
      try {
        this.users = await PP.api('users');
        this.keys = await PP.api('users/keys');
      } catch (e) { PP.ui.warn(e.message); }
    },
    openCreate() {
      this.editing = null;
      this.userForm = { username: '', password: '', role: 'operator' };
      this.showUser = true;
    },
    openEdit(user) {
      this.editing = user.id;
      this.userForm = { username: user.username, password: '', role: user.role };
      this.showUser = true;
    },
    async saveUser() {
      try {
        if (this.editing) {
          await PP.api('users/' + this.editing + '/update', {
            method: 'POST',
            body: { password: this.userForm.password || null, role: this.userForm.role },
          });
        } else {
          await PP.api('users', { method: 'POST', body: this.userForm });
        }
        this.showUser = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async delUser(user) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), user.username);
      if (!ok) return;
      try { await PP.api('users/' + user.id + '/delete', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async createKey() {
      if (!this.keyForm.name) return;
      try {
        const res = await PP.api('users/keys', { method: 'POST', body: this.keyForm });
        this.newKey = res.key;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async delKey(key) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), key.name);
      if (!ok) return;
      try { await PP.api('users/keys/' + key.id + '/delete', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.users') }}</h1>
      <span class="spacer"></span>
      <button class="btn" @click="showKey = true">+ {{ PP.t('users.newKey') }}</button>
      <button class="btn primary" @click="openCreate">+ user</button>
    </div>

    <div class="card mb">
      <div class="card-title">Users</div>
      <p-table :cols="[{ key: 'username', label: PP.t('common.username') },
                       { key: 'role', label: PP.t('users.role') },
                       { key: 'totp', label: '2FA' },
                       { key: 'last_login_at', label: 'Last login' },
                       { key: 'actions', label: '', cls: 'actions' }]" :rows="users">
        <template #col-username="{ row }"><span class="mono">{{ row.username }}</span></template>
        <template #col-role="{ row }">
          <span class="badge" :class="row.role === 'admin' ? 'violet' : row.role === 'operator' ? 'blue' : 'gray'">{{ row.role }}</span>
        </template>
        <template #col-totp="{ row }">
          <span class="badge" :class="row.totp_enabled ? 'green' : 'gray'">{{ row.totp_enabled ? '✓' : '—' }}</span>
        </template>
        <template #col-last_login_at="{ row }">{{ row.last_login_at ? PP.ui.fmtDate(row.last_login_at) : '—' }}</template>
        <template #col-actions="{ row }">
          <button class="btn small" @click="openEdit(row)">✎</button>
          <button class="btn small danger" @click="delUser(row)">🗑</button>
        </template>
      </p-table>
    </div>

    <div class="card">
      <div class="card-title">{{ PP.t('users.keys') }}</div>
      <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                       { key: 'role', label: PP.t('users.role') },
                       { key: 'last_used_at', label: 'Last used' },
                       { key: 'actions', label: '', cls: 'actions' }]" :rows="keys">
        <template #col-name="{ row }"><span class="mono">{{ row.name }}</span></template>
        <template #col-last_used_at="{ row }">{{ row.last_used_at ? PP.ui.fmtDate(row.last_used_at) : 'never' }}</template>
        <template #col-actions="{ row }">
          <button class="btn small danger" @click="delKey(row)">🗑</button>
        </template>
      </p-table>
    </div>

    <p-modal :open="showUser" :title="editing ? PP.t('common.edit') : 'user'" @close="showUser = false">
      <div class="field"><label>{{ PP.t('common.username') }}</label>
        <input class="input mono" v-model="userForm.username" :disabled="!!editing"></div>
      <div class="field" v-if="!editing"><label>{{ PP.t('common.password') }}</label>
        <input class="input mono" v-model="userForm.password"></div>
      <div class="field" v-else><label>{{ PP.t('common.password') }} baru ({{ PP.t('common.optional') }})</label>
        <input class="input mono" v-model="userForm.password"></div>
      <div class="field"><label>{{ PP.t('users.role') }}</label>
        <select class="select" v-model="userForm.role">
          <option value="admin">admin</option>
          <option value="operator">operator</option>
          <option value="viewer">viewer</option>
        </select></div>
      <template #foot>
        <button class="btn" @click="showUser = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="saveUser">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="showKey" :title="PP.t('users.newKey')" @close="showKey = false; newKey = ''">
      <template v-if="!newKey">
        <div class="field"><label>{{ PP.t('common.name') }}</label>
          <input class="input" v-model="keyForm.name"></div>
        <div class="field"><label>{{ PP.t('users.role') }}</label>
          <select class="select" v-model="keyForm.role">
            <option value="admin">admin</option>
            <option value="operator">operator</option>
            <option value="viewer">viewer</option>
          </select></div>
        <button class="btn primary" @click="createKey">{{ PP.t('common.create') }}</button>
      </template>
      <template v-else>
        <p class="text-warn small">{{ PP.t('users.keyOnce') }}</p>
        <div class="log-view mono">{{ newKey }}</div>
        <button class="btn mt" @click="PP.ui.copy(newKey)">📋 {{ PP.t('common.copy') }}</button>
      </template>
    </p-modal>
  </div>`,
};
