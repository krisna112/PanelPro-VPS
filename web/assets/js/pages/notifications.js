/* Notifications page: channels (webhook/telegram/smtp) CRUD + test */
PP.pages = PP.pages || {};
PP.pages.notifications = {
  data: () => ({
    channels: [], events: [],
    show: false,
    form: { name: '', type: 'webhook', config: {}, events: [], enabled: true },
    editing: null,
  }),
  computed: {
    configFields() {
      if (this.form.type === 'webhook') {
        return [{ key: 'url', label: 'URL', type: 'text' }];
      }
      if (this.form.type === 'telegram') {
        return [
          { key: 'bot_token', label: 'Bot token', type: 'text' },
          { key: 'chat_id', label: 'Chat ID', type: 'text' },
        ];
      }
      return [
        { key: 'host', label: 'SMTP host', type: 'text' },
        { key: 'port', label: 'Port', type: 'number' },
        { key: 'username', label: 'User', type: 'text' },
        { key: 'password', label: 'Password', type: 'password' },
        { key: 'from', label: 'From', type: 'text' },
        { key: 'to', label: 'To', type: 'text' },
      ];
    },
  },
  methods: {
    async load() {
      try {
        this.channels = await PP.api('notifications/channels');
        this.events = await PP.api('notifications/events');
      } catch (e) { PP.ui.warn(e.message); }
    },
    openCreate() {
      this.editing = null;
      this.form = { name: '', type: 'webhook', config: {}, events: [], enabled: true };
      this.show = true;
    },
    openEdit(ch) {
      this.editing = ch.id;
      this.form = { name: ch.name, type: ch.type, config: { ...(ch.config || {}) }, events: ch.events || [], enabled: ch.enabled };
      this.show = true;
    },
    async save() {
      if (!this.form.name) return;
      try {
        if (this.editing) {
          await PP.api('notifications/channels/' + this.editing + '/update', { method: 'POST', body: this.form });
        } else {
          await PP.api('notifications/channels', { method: 'POST', body: this.form });
        }
        this.show = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async test(ch) {
      try {
        await PP.api('notifications/channels/' + ch.id + '/test', { method: 'POST' });
        PP.ui.success(PP.t('common.test'));
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async del(ch) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), ch.name);
      if (!ok) return;
      try { await PP.api('notifications/channels/' + ch.id + '/delete', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.notifications') }}</h1>
      <span class="spacer"></span>
      <button class="btn primary" @click="openCreate">+ channel</button>
    </div>

    <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                     { key: 'type', label: PP.t('common.type') },
                     { key: 'events', label: 'Events' },
                     { key: 'enabled', label: PP.t('common.status') },
                     { key: 'actions', label: '', cls: 'actions' }]" :rows="channels">
      <template #col-name="{ row }"><span class="mono">{{ row.name }}</span></template>
      <template #col-events="{ row }">
        <span v-for="ev in (row.events || [])" :key="ev" class="badge gray" style="margin-right:4px">{{ ev }}</span>
        <span v-if="!(row.events || []).length" class="faint">—</span>
      </template>
      <template #col-enabled="{ row }">
        <span class="badge" :class="row.enabled ? 'green' : 'gray'">{{ row.enabled ? 'on' : 'off' }}</span>
      </template>
      <template #col-actions="{ row }">
        <button class="btn small" @click="test(row)">⚡</button>
        <button class="btn small" @click="openEdit(row)">✎</button>
        <button class="btn small danger" @click="del(row)">🗑</button>
      </template>
    </p-table>

    <p-modal :open="show" :title="editing ? PP.t('common.edit') : 'channel'" size="lg" @close="show = false">
      <div class="form-row">
        <div class="field"><label>{{ PP.t('common.name') }}</label>
          <input class="input" v-model="form.name"></div>
        <div class="field"><label>{{ PP.t('common.type') }}</label>
          <select class="select" v-model="form.type">
            <option value="webhook">webhook</option>
            <option value="telegram">telegram</option>
            <option value="smtp">smtp / email</option>
          </select></div>
      </div>
      <div class="field" v-for="f in configFields" :key="f.key">
        <label>{{ f.label }}</label>
        <input class="input mono" :type="f.type" v-model="form.config[f.key]">
      </div>
      <div class="field">
        <label>Events (kosong = semua)</label>
        <div class="flex wrap">
          <label v-for="ev in events" :key="ev" class="checkbox-row" style="margin-right:12px">
            <input type="checkbox" :value="ev" v-model="form.events"> <span class="small mono">{{ ev }}</span>
          </label>
        </div>
      </div>
      <div class="checkbox-row mb"><p-switch v-model="form.enabled"></p-switch><span>{{ PP.t('common.enabled') }}</span></div>
      <template #foot>
        <button class="btn" @click="show = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="save">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
