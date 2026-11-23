/* Dashboard: live stats, charts, SSL warnings, recent activity */
PP.pages = PP.pages || {};
PP.pages.dashboard = {
  data: () => ({
    summary: null, snap: null, busy: true, timer: null,
  }),
  computed: {
    memPct() { return this.snap ? this.snap.mem_percent : 0; },
    diskPct() { return this.snap ? this.snap.disk_percent : 0; },
  },
  methods: {
    async load() {
      try {
        const [s, rt] = await Promise.all([
          PP.api('dashboard/summary'),
          PP.api('monitor/realtime'),
        ]);
        this.summary = s;
        this.snap = rt;
      } catch (e) {
        PP.ui.error(PP.t('common.error'), e.message);
      } finally {
        this.busy = false;
      }
      this.$nextTick(() => this.drawCharts());
    },
    drawCharts() {
      if (!this.snap) return;
      const cpuCanvas = this.$refs.cpuChart;
      const memCanvas = this.$refs.memChart;
      if (cpuCanvas) {
        PP.charts.line(cpuCanvas, {
          series: [{ data: [{ x: this.snap.ts - 60, y: 0 }, { x: this.snap.ts, y: this.snap.cpu }], fill: true }],
          yFormat: v => Math.round(v) + '%', grid: true,
        });
      }
      if (memCanvas) {
        const used = this.snap.mem_total ? this.snap.mem_used / this.snap.mem_total * 100 : 0;
        PP.charts.line(memCanvas, {
          series: [{ data: [{ x: this.snap.ts - 60, y: 0 }, { x: this.snap.ts, y: used }], color: '#7c8cf8', fill: true }],
          yFormat: v => Math.round(v) + '%', grid: true,
        });
      }
    },
    count(key) { return (this.summary && this.summary.counts[key]) ?? '-'; },
  },
  mounted() {
    this.load();
    this.timer = setInterval(this.load, 5000);
  },
  unmounted() { clearInterval(this.timer); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.dashboard') }}</h1>
      <span class="spacer"></span>
      <button class="btn" @click="load">⟳ {{ PP.t('common.refresh') }}</button>
    </div>

    <div class="grid cols-4 mb">
      <p-stat :label="PP.t('menu.sites')" :value="count('sites')" />
      <p-stat :label="PP.t('menu.databases')" :value="count('databases')" />
      <p-stat :label="PP.t('menu.ssl')" :value="count('certs')" />
      <p-stat :label="PP.t('menu.apps')" :value="count('apps')" />
    </div>

    <div class="grid cols-2 mb">
      <div class="card">
        <div class="card-title">{{ PP.t('dashboard.cpu') }}
          <span class="spacer"></span>
          <span class="badge violet">{{ snap ? snap.cpu : 0 }}%</span>
        </div>
        <div class="chart-box"><canvas ref="cpuChart"></canvas></div>
        <div class="small faint mt">{{ PP.t('dashboard.load') }}: {{ snap ? snap.load1 : 0 }}
          · {{ PP.t('dashboard.uptime') }}: {{ snap ? PP.ui.fmtUptime(snap.uptime) : '-' }}</div>
      </div>
      <div class="card">
        <div class="card-title">{{ PP.t('dashboard.memory') }}
          <span class="spacer"></span>
          <span class="badge blue">{{ memPct }}%</span>
        </div>
        <div class="chart-box"><canvas ref="memChart"></canvas></div>
        <div class="small faint mt">{{ PP.ui.fmtBytes(snap?.mem_used) }} / {{ PP.ui.fmtBytes(snap?.mem_total) }}</div>
      </div>
    </div>

    <div class="grid cols-2 mb">
      <div class="card">
        <div class="card-title">{{ PP.t('dashboard.disk') }}</div>
        <p-progress :value="diskPct"></p-progress>
        <div class="small faint mt">{{ PP.ui.fmtBytes(snap?.disk_used) }} / {{ PP.ui.fmtBytes(snap?.disk_total) }} ({{ diskPct }}%)</div>
        <div class="mt" v-if="snap && snap.disks && snap.disks.length > 1">
          <div v-for="d in snap.disks" :key="d.mount" class="flex mb" style="margin:8px 0">
            <span class="small mono" style="width:130px">{{ d.mount }}</span>
            <p-progress :value="d.percent" class="grow"></p-progress>
            <span class="small faint">{{ d.percent }}%</span>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">{{ PP.t('dashboard.network') }}</div>
        <div class="kv">
          <span class="k">↓ {{ PP.t('common.status') }}</span>
          <span class="mono">{{ PP.ui.fmtRate(snap?.net_rate_in) }}</span>
          <span class="k">↑ {{ PP.t('common.status') }}</span>
          <span class="mono">{{ PP.ui.fmtRate(snap?.net_rate_out) }}</span>
          <span class="k">Total ↓</span><span class="mono">{{ PP.ui.fmtBytes(snap?.net_in) }}</span>
          <span class="k">Total ↑</span><span class="mono">{{ PP.ui.fmtBytes(snap?.net_out) }}</span>
        </div>
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <div class="card-title">{{ PP.t('dashboard.sslExpiring') }}</div>
        <p-table v-if="summary && summary.ssl_expiring.length" :cols="[
            { key: 'name', label: PP.t('common.name') },
            { key: 'days_left', label: PP.t('ssl.days') }]"
          :rows="summary.ssl_expiring">
          <template #col-days_left="{ row }">
            <span class="badge" :class="row.days_left <= 7 ? 'red' : 'amber'">{{ row.days_left }}</span>
          </template>
        </p-table>
        <div v-else class="table-empty">✓ {{ PP.t('common.none') }}</div>
      </div>
      <div class="card">
        <div class="card-title">{{ PP.t('dashboard.activity') }}</div>
        <p-table v-if="summary && summary.recent_audit.length" :cols="[
            { key: 'username', label: PP.t('common.owner') },
            { key: 'method', label: '' },
            { key: 'path', label: '' },
            { key: 'status', label: PP.t('common.status') }]"
          :rows="summary.recent_audit">
          <template #col-status="{ row }">
            <span class="badge" :class="row.status < 400 ? 'green' : 'red'">{{ row.status }}</span>
          </template>
        </p-table>
        <div v-else class="table-empty">— {{ PP.t('common.none') }}</div>
      </div>
    </div>
  </div>`,
};
