/* Monitor page: history charts, disks, top processes */
PP.pages = PP.pages || {};
PP.pages.monitor = {
  data: () => ({
    hours: 24,
    history: [], snap: null, disks: [], processes: { by_cpu: [], by_mem: [] },
    timer: null,
  }),
  methods: {
    async loadHistory() {
      const rows = await PP.api('monitor/history', { params: { hours: this.hours } });
      this.history = rows;
      this.draw();
    },
    async loadLive() {
      const [rt, d, p] = await Promise.all([
        PP.api('monitor/realtime'),
        PP.api('monitor/disks'),
        PP.api('monitor/processes'),
      ]);
      this.snap = rt;
      this.disks = d;
      this.processes = p;
    },
    draw() {
      const cpuCanvas = this.$refs.cpuHist;
      if (cpuCanvas && this.history.length) {
        PP.charts.line(cpuCanvas, {
          series: [
            { data: this.history.map(r => ({ x: r.ts, y: r.cpu })), fill: true },
          ],
          yFormat: v => Math.round(v) + '%',
        });
      }
      const memCanvas = this.$refs.memHist;
      if (memCanvas && this.history.length) {
        PP.charts.line(memCanvas, {
          series: [
            { data: this.history.map(r => ({
                x: r.ts, y: r.mem_total ? r.mem_used / r.mem_total * 100 : 0 })),
              color: '#7c8cf8', fill: true },
          ],
          yFormat: v => Math.round(v) + '%',
        });
      }
      const netCanvas = this.$refs.netHist;
      if (netCanvas && this.history.length) {
        PP.charts.line(netCanvas, {
          series: [
            { data: this.history.map(r => ({ x: r.ts, y: r.net_in_rate || 0 })), fill: true },
            { data: this.history.map(r => ({ x: r.ts, y: r.net_out_rate || 0 })), color: '#fbbf24' },
          ],
          yFormat: v => PP.ui.fmtBytes(v),
        });
      }
      const loadCanvas = this.$refs.loadHist;
      if (loadCanvas && this.history.length) {
        PP.charts.line(loadCanvas, {
          series: [{ data: this.history.map(r => ({ x: r.ts, y: r.load1 })), color: '#38bdf8', fill: true }],
          yFormat: v => v.toFixed(1),
        });
      }
    },
    setHours(h) {
      this.hours = h;
      this.loadHistory();
    },
  },
  mounted() {
    this.loadHistory();
    this.loadLive();
    this.timer = setInterval(this.loadLive, 4000);
  },
  unmounted() { clearInterval(this.timer); },
  template: `
  <div>
    <div class="page-head">
      <h1>{{ PP.t('menu.monitor') }}</h1>
      <span class="spacer"></span>
      <div class="btn-row">
        <button v-for="h in [6, 12, 24, 72]" :key="h" class="btn small"
                :class="{ primary: hours === h }" @click="setHours(h)">{{ h }}h</button>
        <button class="btn" @click="loadHistory(); loadLive()">⟳</button>
      </div>
    </div>

    <div class="grid cols-2 mb">
      <div class="card"><div class="card-title">CPU</div><div class="chart-box"><canvas ref="cpuHist"></canvas></div></div>
      <div class="card"><div class="card-title">{{ PP.t('dashboard.memory') }}</div><div class="chart-box"><canvas ref="memHist"></canvas></div></div>
      <div class="card"><div class="card-title">{{ PP.t('dashboard.network') }}</div><div class="chart-box"><canvas ref="netHist"></canvas></div></div>
      <div class="card"><div class="card-title">{{ PP.t('dashboard.load') }} (load1)</div><div class="chart-box"><canvas ref="loadHist"></canvas></div></div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <div class="card-title">{{ PP.t('dashboard.disk') }}</div>
        <div v-for="d in disks" :key="d.mount" style="margin: 10px 0">
          <div class="flex small" style="margin-bottom:5px">
            <span class="mono">{{ d.device }}</span>
            <span class="faint">{{ d.mount }} ({{ d.fstype }})</span>
            <span class="grow"></span>
            <span class="faint">{{ PP.ui.fmtBytes(d.used) }} / {{ PP.ui.fmtBytes(d.total) }}</span>
          </div>
          <p-progress :value="d.percent"></p-progress>
        </div>
        <div v-if="!disks.length" class="table-empty">{{ PP.t('common.none') }}</div>
      </div>
      <div class="card">
        <div class="card-title">{{ PP.t('monitor.processes') }} (CPU)</div>
        <p-table :cols="[
          { key: 'pid', label: 'PID', width: '70px' },
          { key: 'name', label: PP.t('common.name') },
          { key: 'user', label: PP.t('common.owner') },
          { key: 'cpu', label: 'CPU %' },
          { key: 'mem', label: 'MEM %' }]"
          :rows="processes.by_cpu">
          <template #col-cpu="{ row }"><span :class="row.cpu > 50 ? 'text-danger' : ''">{{ row.cpu }}</span></template>
        </p-table>
      </div>
    </div>
  </div>`,
};
