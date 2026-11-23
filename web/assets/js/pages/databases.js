/* Databases page: MySQL/PostgreSQL/Redis/MongoDB management */
PP.pages = PP.pages || {};
PP.pages.databases = {
  data: () => ({
    type: 'mysql',
    engines: {},
    dbs: [], users: [], busy: false,
    showCreate: false, form: { name: '', charset: 'utf8mb4', with_user: true, user: '', password: '' },
    showUser: false, userForm: { user: '', host: 'localhost', password: '', database: '' },
    redisInfo: null,
  }),
  methods: {
    async load() {
      this.busy = true;
      try {
        this.engines = await PP.api('databases/engines');
        if (this.type === 'mysql' || this.type === 'postgres') {
          this.dbs = await PP.api('databases', { params: { type: this.type } });
          this.users = await PP.api('databases/users', { params: { type: this.type } });
        } else if (this.type === 'redis') {
          this.redisInfo = await PP.api('databases/redis/info');
        } else {
          this.dbs = await PP.api('databases', { params: { type: this.type } });
        }
      } catch (e) {
        PP.ui.warn(e.message);
        this.dbs = []; this.users = [];
      }
      this.busy = false;
    },
    setType(t) { this.type = t; this.load(); },
    async create() {
      if (!this.form.name) return;
      try {
        const res = await PP.api('databases', { method: 'POST', body: this.form });
        this.showCreate = false;
        this.form = { name: '', charset: 'utf8mb4', with_user: true, user: '', password: '' };
        if (res.password) PP.ui.toast(res.user, res.password, 'warn', 15000);
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async delDb(row) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), row.name);
      if (!ok) return;
      try {
        await PP.api('databases/' + encodeURIComponent(row.name) + '/delete', {
          method: 'POST', params: { type: this.type },
        });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async createUser() {
      if (!this.userForm.user) return;
      try {
        const res = await PP.api('databases/users', { method: 'POST', body: { ...this.userForm, type: this.type } });
        this.showUser = false;
        PP.ui.toast(res.user, this.userForm.password, 'warn', 15000);
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async delUser(row) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), row.user);
      if (!ok) return;
      try {
        await PP.api('databases/users/delete', {
          method: 'POST', body: { type: this.type, user: row.user, host: row.host || 'localhost' },
        });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async saveRootPassword() {
      const value = prompt(PP.t('db.rootPass'));
      if (!value) return;
      try {
        await PP.api('databases/root-password', { method: 'POST', body: { password: value } });
        PP.ui.success(PP.t('common.save'));
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.databases') }}</h1>
      <span class="spacer"></span>
      <button class="btn" @click="saveRootPassword" v-if="type === 'mysql'">🔑 {{ PP.t('db.rootPass') }}</button>
      <button class="btn primary" v-if="type === 'mysql' || type === 'postgres'" @click="showCreate = true">+ {{ PP.t('db.create') }}</button>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: type === 'mysql' }" @click="setType('mysql')">MySQL / MariaDB
        <span class="badge" :class="engines.mysql ? 'green' : 'gray'">{{ engines.mysql ? '✓' : '✕' }}</span></button>
      <button class="tab" :class="{ active: type === 'postgres' }" @click="setType('postgres')">PostgreSQL
        <span class="badge" :class="engines.postgres ? 'green' : 'gray'">{{ engines.postgres ? '✓' : '✕' }}</span></button>
      <button class="tab" :class="{ active: type === 'redis' }" @click="setType('redis')">Redis
        <span class="badge" :class="engines.redis ? 'green' : 'gray'">{{ engines.redis ? '✓' : '✕' }}</span></button>
      <button class="tab" :class="{ active: type === 'mongo' }" @click="setType('mongo')">MongoDB
        <span class="badge" :class="engines.mongo ? 'green' : 'gray'">{{ engines.mongo ? '✓' : '✕' }}</span></button>
    </div>

    <div v-if="type === 'redis'">
      <div class="card" v-if="redisInfo">
        <div class="card-title">Redis INFO</div>
        <div class="kv">
          <template v-for="(v, k) in redisInfo" :key="k">
            <span class="k mono">{{ k }}</span><span class="mono">{{ v }}</span>
          </template>
        </div>
      </div>
    </div>

    <div v-else>
      <div class="card mb" v-if="type === 'mysql' || type === 'postgres'">
        <div class="card-title">{{ PP.t('db.users') }}
          <span class="spacer"></span>
          <button class="btn small primary" @click="showUser = true">+ {{ PP.t('db.users') }}</button>
        </div>
        <p-table :cols="[{ key: 'user', label: PP.t('common.username') }, { key: 'host', label: 'Host' },
                         { key: 'actions', label: '', cls: 'actions' }]" :rows="users">
          <template #col-actions="{ row }">
            <button class="btn small danger" @click="delUser(row)">🗑</button>
          </template>
        </p-table>
      </div>

      <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                       { key: 'charset', label: PP.t('db.charset') },
                       { key: 'owner_user', label: PP.t('common.owner') },
                       { key: 'size', label: PP.t('common.size') },
                       { key: 'actions', label: '', cls: 'actions' }]" :rows="dbs">
        <template #col-name="{ row }"><span class="mono">{{ row.name }}</span></template>
        <template #col-size="{ row }">{{ row.size !== null && row.size !== undefined ? PP.ui.fmtBytes(row.size) : '-' }}</template>
        <template #col-actions="{ row }">
          <button class="btn small danger" @click="delDb(row)">🗑</button>
        </template>
      </p-table>
    </div>

    <p-modal :open="showCreate" :title="PP.t('db.create')" @close="showCreate = false">
      <div class="field"><label>{{ PP.t('common.name') }}</label>
        <input class="input mono" v-model="form.name" placeholder="myapp_db"></div>
      <div class="checkbox-row mb">
        <p-switch v-model="form.with_user"></p-switch><span>{{ PP.t('db.withUser') }}</span>
      </div>
      <div class="form-row" v-if="form.with_user">
        <div class="field"><label>User</label><input class="input mono" v-model="form.user"></div>
        <div class="field"><label>{{ PP.t('common.password') }} ({{ PP.t('common.optional') }})</label>
          <input class="input mono" v-model="form.password"></div>
      </div>
      <template #foot>
        <button class="btn" @click="showCreate = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" :disabled="!form.name" @click="create">{{ PP.t('common.create') }}</button>
      </template>
    </p-modal>

    <p-modal :open="showUser" :title="PP.t('db.users')" @close="showUser = false">
      <div class="form-row">
        <div class="field"><label>User</label><input class="input mono" v-model="userForm.user"></div>
        <div class="field" v-if="type === 'mysql'"><label>Host</label><input class="input mono" v-model="userForm.host"></div>
      </div>
      <div class="field"><label>{{ PP.t('common.password') }}</label><input class="input mono" v-model="userForm.password"></div>
      <div class="field"><label>DB ({{ PP.t('common.optional') }})</label><input class="input mono" v-model="userForm.database"></div>
      <template #foot>
        <button class="btn" @click="showUser = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="createUser">{{ PP.t('common.create') }}</button>
      </template>
    </p-modal>
  </div>`,
};
