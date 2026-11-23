/* File manager: browse, editor, upload/download, archive ops, permissions */
PP.pages = PP.pages || {};
PP.pages.files = {
  data: () => ({
    path: '/', entries: [], disk: null, showHidden: true, loading: false,
    selected: new Set(),
    editor: { open: false, path: '', content: '', saving: false },
    zip: { open: false, out: '', fmt: 'zip' },
    chmod: { open: false, path: '', mode: '644' },
    uploading: false,
    searchQuery: '', searching: false,
  }),
  computed: {
    crumbs() {
      const parts = this.path.split('/').filter(Boolean);
      const out = [{ name: '/', path: '/' }];
      let acc = '';
      for (const p of parts) {
        acc += '/' + p;
        out.push({ name: p, path: acc });
      }
      return out;
    },
    selectedPaths() {
      return [...this.selected];
    },
  },
  methods: {
    async load() {
      this.loading = true;
      this.selected = new Set();
      try {
        const data = await PP.api('files/list', { params: { path: this.path, show_hidden: this.showHidden } });
        this.entries = data.entries;
        this.disk = data.disk;
        this.path = data.path;
      } catch (e) {
        PP.ui.error(PP.t('common.error'), e.message);
        this.entries = [];
      }
      this.loading = false;
    },
    open(entry) {
      if (entry.is_dir) {
        this.path = entry.path;
        this.load();
        return;
      }
      this.openEditor(entry.path);
    },
    goUp() {
      const parent = this.path === '/' ? '/' : this.path.replace(/\/[^/]+\/?$/, '') || '/';
      this.path = parent;
      this.load();
    },
    async openEditor(path) {
      try {
        const data = await PP.api('files/read', { params: { path } });
        this.editor = { open: true, path, content: data.content, saving: false };
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async saveEditor() {
      this.editor.saving = true;
      try {
        await PP.api('files/write', { method: 'POST', body: { path: this.editor.path, content: this.editor.content } });
        PP.ui.success(PP.t('common.save'));
        this.editor.open = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.editor.saving = false;
    },
    toggleSel(entry) {
      const s = new Set(this.selected);
      s.has(entry.path) ? s.delete(entry.path) : s.add(entry.path);
      this.selected = s;
    },
    async delSelected() {
      const paths = this.selectedPaths.length ? this.selectedPaths : [];
      if (!paths.length) return;
      const ok = await PP.ui.confirm(PP.t('common.confirmDelete'), paths.length + ' item(s)');
      if (!ok) return;
      try {
        await PP.api('files/delete', { method: 'POST', body: { paths } });
        PP.ui.success('OK');
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async mkdir() {
      const name = prompt(PP.t('files.newFolder'));
      if (!name) return;
      try {
        await PP.api('files/mkdir', { method: 'POST', body: { path: this.joinPath(name) } });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async rename(entry) {
      const name = prompt(PP.t('files.rename'), entry.name);
      if (!name || name === entry.name) return;
      try {
        await PP.api('files/rename', {
          method: 'POST',
          body: { src: entry.path, dst: this.joinPath(name) },
        });
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    joinPath(name) {
      return (this.path === '/' ? '' : this.path) + '/' + name;
    },
    openZip() {
      this.zip = { open: true, out: this.joinPath('archive.zip'), fmt: 'zip' };
    },
    async compress() {
      const paths = this.selectedPaths;
      if (!paths.length) { PP.ui.warn('Pilih file/folder dulu'); return; }
      try {
        await PP.api('files/compress', {
          method: 'POST', body: { paths, out: this.zip.out, fmt: this.zip.fmt },
        });
        this.zip.open = false;
        PP.ui.success(PP.t('files.compress'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async extract(entry) {
      const dest = this.joinPath(entry.name.replace(/\.(zip|tar\.gz|tgz)$/i, ''));
      try {
        await PP.api('files/extract', { method: 'POST', body: { path: entry.path, dest } });
        PP.ui.success(PP.t('files.extract'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    openChmod() {
      const paths = this.selectedPaths;
      if (paths.length !== 1) { PP.ui.warn('Pilih 1 item'); return; }
      const entry = this.entries.find(e => e.path === paths[0]);
      this.chmod = { open: true, path: paths[0], mode: entry ? entry.mode.replace('0o', '') : '644' };
    },
    async saveChmod() {
      try {
        await PP.api('files/chmod', { method: 'POST', body: { path: this.chmod.path, mode: this.chmod.mode } });
        this.chmod.open = false;
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async uploadFiles(ev) {
      const files = ev.target.files;
      if (!files.length) return;
      this.uploading = true;
      for (const file of files) {
        const fd = new FormData();
        fd.append('file', file);
        try {
          await PP.upload('files/upload?dest=' + encodeURIComponent(this.path), fd);
        } catch (e) { PP.ui.error(file.name, e.message); }
      }
      this.uploading = false;
      ev.target.value = '';
      this.load();
    },
    download(entry) {
      window.open('/api/files/download?path=' + encodeURIComponent(entry.path), '_blank');
    },
    async doSearch() {
      if (!this.searchQuery) return;
      this.searching = true;
      try {
        const results = await PP.api('files/search', { params: { path: this.path, query: this.searchQuery } });
        this.entries = results;
        this.selected = new Set();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.searching = false;
    },
    ico(entry) {
      if (entry.is_dir) return '📁';
      if ((entry.mime || '').startsWith('image/')) return '🖼️';
      if ((entry.mime || '').startsWith('text/')) return '📄';
      if (/\.zip$|\.tar\.gz$|\.tgz$/.test(entry.name)) return '🗜️';
      return '📄';
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.files') }}</h1>
      <span class="spacer"></span>
      <label class="btn" :class="{ 'opacity-50': uploading }">
        {{ uploading ? '…' : '⬆ ' + PP.t('common.upload') }}
        <input type="file" multiple style="display:none" @change="uploadFiles">
      </label>
      <button class="btn" @click="mkdir">📁+ {{ PP.t('files.newFolder') }}</button>
      <button class="btn" @click="openZip" :disabled="!selectedPaths.length">🗜️</button>
      <button class="btn" @click="openChmod" :disabled="selectedPaths.length !== 1">🔐</button>
      <button class="btn danger" @click="delSelected" :disabled="!selectedPaths.length">🗑</button>
    </div>

    <div class="card mb">
      <div class="flex wrap">
        <div class="crumbs grow">
          <template v-for="(c, i) in crumbs" :key="c.path">
            <button @click="path = c.path; load()">{{ c.name }}</button>
            <span class="sep" v-if="i < crumbs.length - 1">/</span>
          </template>
        </div>
        <input class="input mono" style="width:190px" v-model="searchQuery"
               :placeholder="PP.t('common.search')" @keyup.enter="doSearch">
        <button class="btn small" @click="doSearch">🔍</button>
        <button class="btn small" @click="showHidden = !showHidden; load()">👁</button>
        <button class="btn small" @click="goUp">↰</button>
        <button class="btn small" @click="load()">⟳</button>
      </div>
      <div class="small faint" v-if="disk">
        {{ PP.ui.fmtBytes(disk.used) }} / {{ PP.ui.fmtBytes(disk.total) }} ({{ disk.percent }}%)
      </div>
    </div>

    <p-table :cols="[{ key: 'name', label: PP.t('common.name') },
                     { key: 'size', label: PP.t('common.size'), width: '110px' },
                     { key: 'owner', label: PP.t('common.owner'), width: '150px' },
                     { key: 'mode', label: 'Mode', width: '90px' },
                     { key: 'mtime', label: PP.t('common.modified'), width: '160px' },
                     { key: 'actions', label: '', cls: 'actions', width: '170px' }]"
             :rows="entries">
      <template #col-name="{ row }">
        <span style="cursor:pointer" @click="open(row)">
          <span class="file-ico">{{ ico(row) }}</span>
          <span class="mono" :class="{ faint: row.hidden }">{{ row.name }}</span>
        </span>
        <label style="margin-left:10px; cursor:pointer">
          <input type="checkbox" :checked="selected.has(row.path)" @change="toggleSel(row)">
        </label>
      </template>
      <template #col-size="{ row }">{{ row.is_dir ? '—' : PP.ui.fmtBytes(row.size) }}</template>
      <template #col-owner="{ row }">{{ (row.owner || '?') + ':' + (row.group || '?') }}</template>
      <template #col-mtime="{ row }">{{ PP.ui.fmtDate(row.mtime) }}</template>
      <template #col-actions="{ row }">
        <button v-if="!row.is_dir" class="btn small" @click="openEditor(row.path)">✏️</button>
        <button v-if="!row.is_dir" class="btn small" @click="download(row)">⬇</button>
        <button v-if="!row.is_dir && /\\.(zip|tar\\.gz|tgz)$/i.test(row.name)" class="btn small" @click="extract(row)">📦</button>
        <button class="btn small" @click="rename(row)">✎</button>
      </template>
    </p-table>

    <p-modal :open="editor.open" :title="PP.t('files.editor') + ' — ' + editor.path" size="lg" @close="editor.open = false">
      <textarea class="input code-editor" v-model="editor.content" spellcheck="false"></textarea>
      <template #foot>
        <button class="btn" @click="editor.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" :disabled="editor.saving" @click="saveEditor">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="zip.open" :title="PP.t('files.compress')" @close="zip.open = false">
      <div class="field"><label>{{ PP.t('common.name') }}</label>
        <input class="input mono" v-model="zip.out"></div>
      <div class="field"><label>Format</label>
        <select class="select" v-model="zip.fmt">
          <option value="zip">zip</option><option value="tar.gz">tar.gz</option>
        </select></div>
      <template #foot>
        <button class="btn" @click="zip.open = false">{{ PP.t('common.cancel') }}</button>
        <button class="btn primary" @click="compress">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>

    <p-modal :open="chmod.open" :title="PP.t('files.chmod')" @close="chmod.open = false">
      <div class="field"><label>Mode (octal)</label>
        <input class="input mono" v-model="chmod.mode" placeholder="644"></div>
      <template #foot>
        <button class="btn primary" @click="saveChmod">{{ PP.t('common.save') }}</button>
      </template>
    </p-modal>
  </div>`,
};
