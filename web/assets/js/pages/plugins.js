/* Plugins page: list installed plugins + short dev guide */
PP.pages = PP.pages || {};
PP.pages.plugins = {
  data: () => ({ plugins: [] }),
  methods: {
    async load() {
      try { this.plugins = await PP.api('plugins'); }
      catch (e) { PP.ui.warn(e.message); }
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.plugins') }}</h1>
      <span class="spacer"></span>
      <button class="btn" @click="load">⟳</button>
    </div>

    <div class="grid cols-3 mb">
      <div class="card" v-for="p in plugins" :key="p.id">
        <div class="card-title">{{ p.name }}
          <span class="spacer"></span>
          <span class="badge gray">v{{ p.version }}</span>
        </div>
        <div class="small muted">{{ p.description }}</div>
        <div class="small faint mt mono">{{ p.prefix }}</div>
      </div>
      <div class="card" v-if="!plugins.length">
        <div class="table-empty">{{ PP.t('common.none') }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Plugin API</div>
      <p class="small muted">Plugin = folder di <code>panelpro/plugins/&lt;nama&gt;/</code> berisi
        <code>manifest.json</code> dan <code>main.py</code> yang mengekspor FastAPI <code>router</code>.
        Contoh tersedia di <code>panelpro/plugins/sample_hello</code>. Restart panel untuk memuat plugin baru.</p>
      <div class="log-view">panelpro/plugins/
├── sample_hello/
│   ├── manifest.json   # { "id", "name", "prefix": "/api/plugins/hello" }
│   └── main.py         # router = APIRouter(); @router.get("/hello")
└── my_plugin/...</div>
    </div>
  </div>`,
};
