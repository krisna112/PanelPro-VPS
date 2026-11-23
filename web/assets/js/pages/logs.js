/* Logs page: source picker, tail + search, download */
PP.pages = PP.pages || {};
PP.pages.logs = {
  data: () => ({
    sources: [], source: 'panel-audit', text: '', query: '',
    lines: 200, timer: null, loading: false,
  }),
  methods: {
    async loadSources() {
      try { this.sources = await PP.api('logs/sources'); }
      catch (e) { PP.ui.warn(e.message); }
    },
    async tail() {
      this.loading = true;
      try {
        const data = await PP.api('logs/tail', {
          params: { source: this.source, lines: this.lines, query: this.query },
        });
        this.text = data.log || '(empty)';
      } catch (e) { this.text = e.message; }
      this.loading = false;
    },
    download() {
      window.open('/api/logs/download?source=' + encodeURIComponent(this.source), '_blank');
    },
  },
  mounted() {
    this.loadSources();
    this.tail();
    this.timer = setInterval(this.tail, 5000);
  },
  unmounted() { clearInterval(this.timer); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.logs') }}</h1>
      <span class="spacer"></span>
      <div class="btn-row">
        <input class="input mono" style="width:180px" v-model="query"
               :placeholder="PP.t('common.search')" @keyup.enter="tail">
        <select class="select" style="width:110px" v-model.number="lines">
          <option :value="100">100</option><option :value="500">500</option>
          <option :value="1000">1000</option><option :value="2000">2000</option>
        </select>
        <button class="btn small" @click="download">⬇</button>
        <button class="btn small" @click="tail">⟳</button>
      </div>
    </div>

    <div class="btn-row mb wrap">
      <button v-for="s in sources" :key="s.id" class="btn small"
              :class="{ primary: source === s.id }" @click="source = s.id; tail()">
        {{ s.name }}</button>
    </div>

    <div class="log-view" style="max-height:600px">{{ text }}</div>
  </div>`,
};
