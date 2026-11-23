/* Docker page: containers, images, volumes, networks, stats */
PP.pages = PP.pages || {};
PP.pages.docker = {
  data: () => ({
    available: false, tab: 'containers',
    containers: [], images: [], volumes: [], networks: [], stats: [],
    pullImage: '', logsModal: { open: false, name: '', text: '' },
  }),
  methods: {
    async load() {
      try {
        this.available = (await PP.api('docker/status')).available;
        if (!this.available) return;
        if (this.tab === 'containers') {
          this.containers = await PP.api('docker/containers');
        } else if (this.tab === 'images') {
          this.images = await PP.api('docker/images');
        } else if (this.tab === 'volumes') {
          this.volumes = await PP.api('docker/volumes');
        } else if (this.tab === 'networks') {
          this.networks = await PP.api('docker/networks');
        } else if (this.tab === 'stats') {
          this.stats = await PP.api('docker/stats');
        }
      } catch (e) { PP.ui.warn(e.message); }
    },
    async action(name, act) {
      if (act === 'remove') {
        const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), name);
        if (!ok) return;
      }
      try {
        await PP.api('docker/containers/' + encodeURIComponent(name) + '/' + act, { method: 'POST' });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async viewLogs(name) {
      try {
        const data = await PP.api('docker/containers/' + encodeURIComponent(name) + '/logs', { params: { tail: 300 } });
        this.logsModal = { open: true, name, text: data.log || '(empty)' };
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async pull() {
      if (!this.pullImage) return;
      try {
        await PP.api('docker/images/pull', { method: 'POST', body: { image: this.pullImage.trim() } });
        PP.ui.success('pull', this.pullImage);
        this.pullImage = '';
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async rmi(image) {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), image);
      if (!ok) return;
      try {
        await PP.api('docker/images/remove', { method: 'POST', body: { image } });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async prune() {
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), 'prune images');
      if (!ok) return;
      try { await PP.api('docker/images/prune', { method: 'POST' }); this.load(); }
      catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.docker') }}</h1>
      <span class="badge" :class="available ? 'green' : 'amber'">{{ available ? 'connected' : 'not available' }}</span>
      <span class="spacer"></span>
      <button class="btn" @click="load">⟳</button>
    </div>

    <template v-if="available">
      <p-tabs v-model="tab" @update:modelValue="load" :tabs="[
        { key: 'containers', label: PP.t('docker.containers') },
        { key: 'images', label: PP.t('docker.images') },
        { key: 'volumes', label: PP.t('docker.volumes') },
        { key: 'networks', label: PP.t('docker.networks') },
        { key: 'stats', label: 'stats' }]"></p-tabs>

      <p-table v-if="tab === 'containers'" :cols="[
          { key: 'Names', label: PP.t('common.name') },
          { key: 'Image', label: 'Image' },
          { key: 'Status', label: PP.t('common.status') },
          { key: 'Ports', label: 'Ports' },
          { key: 'actions', label: '', cls: 'actions' }]" :rows="containers">
        <template #col-Names="{ row }"><span class="mono">{{ row.Names }}</span></template>
        <template #col-Status="{ row }">
          <span class="badge" :class="PP.ui.statusBadge(row.State)">{{ row.Status }}</span>
        </template>
        <template #col-actions="{ row }">
          <button v-if="row.State !== 'running'" class="btn small" @click="action(row.Names, 'start')">▶</button>
          <button v-else class="btn small" @click="action(row.Names, 'stop')">⏹</button>
          <button class="btn small" @click="action(row.Names, 'restart')">⟳</button>
          <button class="btn small" @click="viewLogs(row.Names)">📜</button>
          <button class="btn small danger" @click="action(row.Names, 'remove')">🗑</button>
        </template>
      </p-table>

      <template v-else-if="tab === 'images'">
        <div class="flex mb">
          <input class="input mono grow" v-model="pullImage" placeholder="nginx:alpine" @keyup.enter="pull">
          <button class="btn primary" @click="pull">⬇ pull</button>
          <button class="btn" @click="prune">🧹 prune</button>
        </div>
        <p-table :cols="[{ key: 'Repository', label: 'Repository' }, { key: 'Tag', label: 'Tag' },
                         { key: 'Size', label: PP.t('common.size') }, { key: 'actions', label: '', cls: 'actions' }]"
                 :rows="images">
          <template #col-Repository="{ row }"><span class="mono">{{ row.Repository }}</span></template>
          <template #col-actions="{ row }">
            <button class="btn small danger" @click="rmi(row.Repository + ':' + row.Tag)">🗑</button>
          </template>
        </p-table>
      </template>

      <p-table v-else-if="tab === 'volumes'" :cols="[{ key: 'Name', label: PP.t('common.name') }, { key: 'Driver', label: 'Driver' }]"
               :rows="volumes">
        <template #col-Name="{ row }"><span class="mono">{{ row.Name }}</span></template>
      </p-table>

      <p-table v-else-if="tab === 'networks'" :cols="[{ key: 'Name', label: PP.t('common.name') }, { key: 'Driver', label: 'Driver' }, { key: 'Scope', label: 'Scope' }]"
               :rows="networks">
        <template #col-Name="{ row }"><span class="mono">{{ row.Name }}</span></template>
      </p-table>

      <p-table v-else-if="tab === 'stats'" :cols="[{ key: 'Name', label: PP.t('common.name') }, { key: 'CPUPerc', label: 'CPU' },
                                                    { key: 'MemUsage', label: 'MEM' }, { key: 'NetIO', label: 'NET' }]"
               :rows="stats">
        <template #col-Name="{ row }"><span class="mono">{{ row.Name }}</span></template>
      </p-table>
    </template>
    <div v-else class="card"><div class="table-empty">🐳 — install Docker via App Store / package manager</div></div>

    <p-modal :open="logsModal.open" :title="'logs — ' + logsModal.name" size="lg" @close="logsModal.open = false">
      <div class="log-view">{{ logsModal.text }}</div>
    </p-modal>
  </div>`,
};
