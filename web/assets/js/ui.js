/* PanelPro UI helpers: toasts, confirm dialog state, formatters. */
(function () {
  PP.ui = {
    toasts: Vue.reactive([]),

    toast(title, message, type = 'info', timeout = 4200) {
      const id = Date.now() + Math.random();
      PP.ui.toasts.push({ id, title, message, type });
      setTimeout(() => PP.ui.dismiss(id), timeout);
    },
    success(title, message) { PP.ui.toast(title, message, 'success'); },
    error(title, message) { PP.ui.toast(title, message, 'error', 7000); },
    warn(title, message) { PP.ui.toast(title, message, 'warn'); },
    dismiss(id) {
      const i = PP.ui.toasts.findIndex(t => t.id === id);
      if (i >= 0) PP.ui.toasts.splice(i, 1);
    },

    /* Promise-based confirm dialog; rendered by the root App. */
    confirmState: Vue.reactive({ open: false, title: '', message: '', danger: false, _resolve: null }),
    confirm(message, title = '', danger = true) {
      return new Promise((resolve) => {
        PP.ui.confirmState.open = true;
        PP.ui.confirmState.title = title;
        PP.ui.confirmState.message = message;
        PP.ui.confirmState.danger = danger;
        PP.ui.confirmState._resolve = resolve;
      });
    },
    confirmAnswer(answer) {
      PP.ui.confirmState.open = false;
      if (PP.ui.confirmState._resolve) PP.ui.confirmState._resolve(answer);
      PP.ui.confirmState._resolve = null;
    },

    /* Formatters ------------------------------------------------------ */
    fmtBytes(n) {
      if (n === null || n === undefined || isNaN(n)) return '-';
      const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
      let i = 0, num = Number(n);
      while (Math.abs(num) >= 1024 && i < units.length - 1) { num /= 1024; i++; }
      return (i === 0 ? num : num.toFixed(1)) + ' ' + units[i];
    },
    fmtRate(bps) {
      if (!bps || bps < 0) return '0 B/s';
      return PP.ui.fmtBytes(bps) + '/s';
    },
    fmtUptime(seconds) {
      const d = Math.floor(seconds / 86400);
      const h = Math.floor((seconds % 86400) / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      return (d ? d + 'd ' : '') + h + 'h ' + m + 'm';
    },
    fmtDate(value) {
      if (!value) return '-';
      const d = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
      if (isNaN(d.getTime())) return String(value);
      return d.toLocaleString(PP.store.lang === 'id' ? 'id-ID' : 'en-US',
        { dateStyle: 'medium', timeStyle: 'short' });
    },
    timeAgo(iso) {
      if (!iso) return '-';
      const diff = (Date.now() - new Date(iso).getTime()) / 1000;
      if (diff < 60) return Math.floor(diff) + 's';
      if (diff < 3600) return Math.floor(diff / 60) + 'm';
      if (diff < 86400) return Math.floor(diff / 3600) + 'h';
      return Math.floor(diff / 86400) + 'd';
    },
    statusBadge(status) {
      const map = {
        running: 'green', active: 'green', enabled: 'green', done: 'green', installed: 'green',
        stopped: 'gray', inactive: 'gray', failed: 'red', exited: 'red', error: 'red',
        unknown: 'gray', disabled: 'amber', pending: 'amber', running_job: 'blue',
      };
      return map[String(status).toLowerCase()] || 'gray';
    },
    async copy(text) {
      try {
        await navigator.clipboard.writeText(text);
        PP.ui.success(PP.t('common.copied'));
      } catch (e) {
        PP.ui.error(PP.t('common.error'), String(e.message || e));
      }
    },
  };
})();
