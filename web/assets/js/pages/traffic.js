/* Traffic stats: per-site access-log analytics (pv/uv/spider) */
PP.pages = PP.pages || {};
PP.pages.traffic = {
  data: () => ({
    sites: [], siteId: null, days: 7,
    series: [], totals: {}, topIps: {}, topUrls: {}, loading: false,
  }),
  methods: {
    async load() {
      this.loading = true;
      try {
        this.sites = await PP.api('sites');
        const params = { days: this.days };
        if (this.siteId) params.site_id = this.siteId;
        const data = await PP.api('traffic', { params });
        this.series = data.series;
        this.totals = data.totals;
        this.topIps = data.top_ips;
        this.topUrls = data.top_urls;
        this.$nextTick(() => this.draw());
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
      this.loading = false;
    },
    async collect() {
      try {
        await PP.api('traffic/collect', { method: 'POST' });
        PP.ui.success(PP.t('traffic.collected'));
        this.load();
      } catch (e) { PP.ui.error(PP.t('common.error'), e.message); }
    },
    draw() {
      const cv = document.getElementById('traffic-chart');
      if (!cv) return;
      const pv = this.series.map((d, i) => ({ x: i, y: d.pv }));
      const uv = this.series.map((d, i) => ({ x: i, y: d.uv }));
      const spider = this.series.map((d, i) => ({ x: i, y: d.spiders }));
      PP.charts.line(cv, {
        series: [
          { data: pv, color: '#3b82f6', fill: true },
          { data: uv, color: '#10b981' },
          { data: spider, color: '#f59e0b' },
        ],
        grid: true,
        yFormat: v => String(Math.round(v)),
      });
    },
    fmtBytes(n) {
      if (!n) return '0';
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let i = 0, v = n;
      while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
      return v.toFixed(1) + ' ' + units[i];
    },
    topEntries(obj, limit) {
      return Object.entries(obj || {}).sort((a, b) => b[1] - a[1]).slice(0, limit);
    },
  },
  mounted() { this.load(); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.traffic') }}</h1>
      <span class="spacer"></span>
      <select class="select" style="width:auto" v-model="days" @change="load">
        <option :value="1">1d</option><option :value="7">7d</option>
        <option :value="14">14d</option><option :value="30">30d</option>
      </select>
      <select class="select" style="width:auto" v-model="siteId" @change="load">
        <option :value="null">— {{ PP.t('common.all') }} —</option>
        <option v-for="s in sites" :key="s.id" :value="s.id">{{ s.name }}</option>
      </select>
      <button class="btn" @click="collect">⟳ {{ PP.t('traffic.collect') }}</button>
    </div>

    <div class="grid cols-4 mb">
      <p-stat label="PV" :value="totals.pv || 0"></p-stat>
      <p-stat label="UV" :value="totals.uv || 0"></p-stat>
      <p-stat label="Bandwidth" :value="fmtBytes(totals.bytes)"></p-stat>
      <p-stat label="Spider/Bot" :value="totals.spiders || 0"></p-stat>
    </div>

    <div class="card mb">
      <canvas id="traffic-chart" style="width:100%; height:220px"></canvas>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Top IP</h3>
        <p-table :cols="[{ key: 'ip', label: 'IP' }, { key: 'hits', label: 'Hits' }]"
                 :rows="topEntries(topIps, 10).map(([ip, hits]) => ({ ip, hits }))">
          <template #col-ip="{ row }"><span class="mono">{{ row.ip }}</span></template>
        </p-table>
      </div>
      <div class="card">
        <h3>Top URL</h3>
        <p-table :cols="[{ key: 'url', label: 'URL' }, { key: 'hits', label: 'Hits' }]"
                 :rows="topEntries(topUrls, 10).map(([url, hits]) => ({ url, hits }))">
          <template #col-url="{ row }"><span class="mono small">{{ row.url }}</span></template>
        </p-table>
      </div>
    </div>
  </div>`,
};
