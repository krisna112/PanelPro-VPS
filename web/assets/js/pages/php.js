/* PHP page: versions, extensions, ini editor, pool tuning */
PP.pages = PP.pages || {};
PP.pages.php = {
  data: () => ({
    versions: [], current: null,
    extensions: [], showExt: false,
    ini: { sapi: 'fpm', content: '', path: '' },
    pool: { settings: {}, pm_max_children: '', pm_start_servers: '', pm_max_requests: '' },
    installVersion: '',
  }),
  methods: {
    async load() {
      try {
        this.versions = await PP.api('php/versions');
        if (this.versions.length && !this.current) this.current = this.versions[0].version;
        if (this.current) await this.select(this.current);
      } catch (e) { PP.ui.warn(e.message); }
    },
    async select(v) {
      this.current = v;
      try {
        this.extensions = await PP.api('php/versions/' + v + '/extensions');
        const iniData = await PP.api('php/versions/' + v + '/ini', { params: { sapi: this.ini.sapi } });
        this.ini.content = iniData.content;
        this.ini.path = iniData.path;
        const pool = await PP.api('php/versions/' + v + '/pool');
        this.pool.settings = pool.settings || {};
        this.pool.pm_max_children = this.pool.settings['pm.max_children'] || '';
        this.pool.pm_start_servers = this.pool.settings['pm.start_servers'] || '';
        this.pool.pm_max_requests = this.pool.settings['pm.max_requests'] || '';
      } catch (e) { PP.ui.warn(e.message); }
    },
    async saveIni() {
      try {
        await PP.api('php/versions/' + this.current + '/ini', {
          method: 'POST', body: { sapi: this.ini.sapi, content: this.ini.content },
        });
        PP.ui.success(PP.t('common.save'));
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async restart() {
      try {
        await PP.api('php/versions/' + this.current + '/restart', { method: 'POST' });
        PP.ui.success('FPM restarted');
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async savePool() {
      try {
        const settings = {};
        if (this.pool.pm_max_children) settings['pm.max_children'] = this.pool.pm_max_children;
        if (this.pool.pm_start_servers) settings['pm.start_servers'] = this.pool.pm_start_servers;
        if (this.pool.pm_max_requests) settings['pm.max_requests'] = this.pool.pm_max_requests;
        await PP.api('php/versions/' + this.current + '/pool', { method: 'POST', body: { settings } });
        PP.ui.success(PP.t('common.save'));
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    async installPhp() {
      if (!this.installVersion) return;
      const ok = await PP.ui.confirm('apt-get / dnf install php' + this.installVersion + '-fpm …', PP.t('php.install'));
      if (!ok) return;
      try {
        await PP.api('php/install', { method: 'POST', body: { version: this.installVersion } });
        PP.ui.success(PP.t('php.install'));
        this.installVersion = '';
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.php') }}</h1>
      <span class="spacer"></span>
      <div class="flex">
        <input class="input mono" style="width:110px" v-model="installVersion" placeholder="8.2">
        <button class="btn" @click="installPhp">{{ PP.t('php.install') }}</button>
      </div>
    </div>

    <div class="btn-row mb" v-if="versions.length">
      <button v-for="v in versions" :key="v.version" class="btn"
              :class="{ primary: current === v.version }" @click="select(v.version)">
        PHP {{ v.version }}
        <span class="badge" :class="v.fpm_active ? 'green' : 'gray'">{{ v.fpm_active ? 'fpm ✓' : 'fpm ✕' }}</span>
      </button>
    </div>
    <div class="card mb" v-else><div class="table-empty">— {{ PP.t('common.none') }}</div></div>

    <template v-if="current">
      <div class="grid cols-2 mb">
        <div class="card">
          <div class="card-title">{{ PP.t('php.extensions') }} ({{ extensions.length }})
            <span class="spacer"></span>
            <button class="btn small" @click="restart">⟳ FPM</button>
          </div>
          <div class="flex wrap">
            <span v-for="ext in extensions" :key="ext" class="badge gray mono">{{ ext }}</span>
          </div>
        </div>
        <div class="card">
          <div class="card-title">{{ PP.t('php.pool') }}</div>
          <div class="form-row">
            <div class="field"><label>pm.max_children</label>
              <input class="input mono" v-model="pool.pm_max_children"></div>
            <div class="field"><label>pm.start_servers</label>
              <input class="input mono" v-model="pool.pm_start_servers"></div>
            <div class="field"><label>pm.max_requests</label>
              <input class="input mono" v-model="pool.pm_max_requests"></div>
          </div>
          <button class="btn primary small" @click="savePool">{{ PP.t('common.save') }}</button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">{{ PP.t('php.ini') }}
          <span class="small faint">{{ ini.path }}</span>
          <span class="spacer"></span>
          <button class="btn small primary" @click="saveIni">{{ PP.t('common.save') }}</button>
        </div>
        <textarea class="input code-editor" v-model="ini.content" spellcheck="false" style="min-height:320px"></textarea>
      </div>
    </template>
  </div>`,
};
