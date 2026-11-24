/* Load balancer: nginx upstream pools */
PP.pages = PP.pages || {};
PP.pages.lb = {
  data: () => ({
    upstreams: [],
    form: { open: false, id: null, name: '', servers: [{ host: '', port: 8080, weight: 1 }] },
  }),
  methods: {
    async load() {
      try {
        const data = await PP.api('lb');
        this.upstreams = data.upstreams;
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    openForm(row) {
      this.form = row
        ? { open: true, id: row.id, name: row.name, servers: (row.servers || []).map(s => ({ ...s })) }
        : { open: true, id: null, name: '', servers: [{ host: '', port: 8080, weight: 1 }] };
    },
    addServer() { this.form.servers.push({ host: '', port: 8080, weight: 1 }); },
    removeServer(i) { this.form.servers.splice(i, 1); },
    async save() {
      const f = this.form;
      if (!f.name || !f.servers.length) return;
      try {
        await PP.api('lb' + (f.id ? '/' + f.id + '/update' : ''), {
          method: 'POST',
          body: { name: f.name, servers: f.servers.map(s => ({
            host: s.host, port: Number(s.port) || 80, weight: Number(s.weight) || 1 })) },
        });
        this.form.open = false;
        PP.ui.success(PP.t('common.save'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async del(row) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), row.name);
      if (!ok) return;
      try { await PP.api('lb/' + row.id + '/delete', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.lb') }}</h1>
      <span class="spacer"></span>
      <button class="btn primary" @click="openForm(null)">+ {{ PP.t('lb.add') }}</button>
    </div>
    <p class="small">{{ PP.t('lb.desc') }}</p>

    <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                     { key: 'servers', label: PP.t('lb.servers') },
                     { key: 'actions', label: '', cls: 'actions' }]" :rows="upstreams">
      <template #col-name="{ row }"><span class="mono">upstream:{{ row.name }}</span></template>
      <template #col-servers="{ row }">
        <span class="mono small" v-for="s in row.servers" :key="s.host + ':' + s.port">
          {{ s.host }}:{{ s.port }} (w{{ s.weight }}) </span>
      </template>
      <template #col-actions="{ row }">
        <button class="btn small" @click="openForm(row)">✎</button>
        <button class="btn small danger" @click="del(row)">🗑</button>
      </template>
    </p-table>

    <p-modal :open="form.open" :title="form.id ? PP.t('lb.edit') : PP.t('lb.add')" size="lg" @close="form.open = false">
      <div class="field"><label>{{ PP.t('common.name') }} (lowercase)</label>
        <input class="input mono" v-model="form.name" placeholder="backend-pool"></div>
      <div class="field"><label>{{ PP.t('lb.servers') }}</label></div>
      <div class="flex wrap mb" v-for="(s, i) in form.servers" :key="i">
        <input class="input mono" style="width:220px" v-model="s.host" :placeholder="'host' + (i + 1)">
        <input class="input mono" style="width:90px" type="number" v-model="s.port" placeholder="port">
        <input class="input mono" style="width:90px" type="number" v-model="s.weight" min="1" max="100">
        <button class="btn small danger" @click="removeServer(i)">✕</button>
      </div>
      <button class="btn" @click="addServer">+ {{ PP.t('lb.addServer') }}</button>
      <template #foot>
        <button class="btn" @click="form.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="save">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
