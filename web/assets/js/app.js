/* PanelPro SPA root: router, layout shell, auth guard. */
(function () {
  const { createApp, ref, computed, onMounted, watch, nextTick } = Vue;
  const { createRouter, createWebHashHistory } = VueRouter;

  // ------------------------------------------------------------------ //
  // Nav definition
  // ------------------------------------------------------------------ //
  const NAV = [
    { group: 'menu.group.general', items: [
      { route: 'dashboard', icon: '📊' },
      { route: 'monitor', icon: '📈' },
    ]},
    { group: 'menu.group.sites', items: [
      { route: 'sites', icon: '🌐' },
      { route: 'databases', icon: '🗄️' },
      { route: 'php', icon: '🐘' },
      { route: 'ftp', icon: '📁' },
      { route: 'ssl', icon: '🔒' },
    ]},
    { group: 'menu.group.system', items: [
      { route: 'files', icon: '📂' },
      { route: 'terminal', icon: '⌨️' },
      { route: 'cron', icon: '⏰' },
      { route: 'logs', icon: '📜' },
      { route: 'docker', icon: '🐳' },
    ]},
    { group: 'menu.group.advanced', items: [
      { route: 'apps', icon: '🛍️' },
      { route: 'backup', icon: '💾' },
      { route: 'security', icon: '🛡️' },
      { route: 'notifications', icon: '🔔' },
      { route: 'users', icon: '👥' },
      { route: 'settings', icon: '⚙️' },
      { route: 'plugins', icon: '🧩' },
    ]},
    { group: 'menu.group.pro', items: [
      { route: 'daemon', icon: '🩺' },
      { route: 'traffic', icon: '📊' },
      { route: 'waf', icon: '🧱' },
      { route: 'tamper', icon: '🔐' },
      { route: 'lb', icon: '⚖️' },
      { route: 'migration', icon: '🚚' },
      { route: 'replication', icon: '🗃️' },
      { route: 'fleet', icon: '🖥️' },
    ]},
  ];

  const routes = [
    { path: '/login', name: 'login', component: PP.pages.login, meta: { public: true } },
    ...Object.keys(PP.pages)
      .filter(name => name !== 'login')
      .map(name => ({ path: '/' + name, name, component: PP.pages[name] })),
    { path: '/', redirect: '/dashboard' },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ];

  const router = createRouter({ history: createWebHashHistory(), routes });

  router.beforeEach(async (to) => {
    if (to.meta.public) {
      const ok = await PP.store.resolveAuth();
      if (ok) return { name: 'dashboard' };
      return true;
    }
    const ok = await PP.store.resolveAuth();
    if (!ok) return { name: 'login' };
    return true;
  });

  // ------------------------------------------------------------------ //
  // Layout shell
  // ------------------------------------------------------------------ //
  const AppLayout = {
    setup() {
      const userMenuOpen = ref(false);
      const route = VueRouter.useRoute();
      const isLogin = computed(() => route.name === 'login');

      const pageTitle = computed(() => {
        const key = 'menu.' + route.name;
        return PP.t(key) || route.name;
      });

      const initials = computed(() => {
        const u = PP.store.user && PP.store.user.username;
        return u ? u.slice(0, 2).toUpperCase() : 'PP';
      });

      async function logout() {
        try { await PP.api('auth/logout', { method: 'POST' }); } catch (e) { /* ignore */ }
        PP.store.user = null;
        PP.store.authed = false;
        router.push({ name: 'login' });
      }

      onMounted(() => {
        document.addEventListener('click', (e) => {
          if (!e.target.closest('.user-chip')) userMenuOpen.value = false;
        });
      });

      return { PP, NAV, userMenuOpen, pageTitle, initials, logout, route, isLogin };
    },
    template: `
      <router-view v-if="isLogin"></router-view>
      <div class="layout" v-else>
        <aside class="sidebar" :class="{ open: PP.store.sidebarOpen }">
          <div class="sidebar-head">
            <img class="logo" src="/favicon.svg" alt="PanelPro">
            <span>PanelPro</span>
            <span class="ver">v1.0</span>
          </div>
          <nav class="nav-groups" @click="PP.store.sidebarOpen = false">
            <template v-for="g in NAV" :key="g.group">
              <div class="nav-group-title">{{ PP.t(g.group) }}</div>
              <router-link v-for="item in g.items" :key="item.route"
                           class="nav-item" :to="{ name: item.route }"
                           :class="{ active: route.name === item.route }">
                <span class="ico">{{ item.icon }}</span>
                <span>{{ PP.t('menu.' + item.route) }}</span>
              </router-link>
            </template>
          </nav>
        </aside>

        <div class="main">
          <header class="topbar">
            <button class="btn icon ghost sidebar-toggle" @click="PP.store.sidebarOpen = !PP.store.sidebarOpen">☰</button>
            <span class="page-title">{{ pageTitle }}</span>
            <span class="spacer"></span>
            <button class="topbar-btn" @click="PP.store.toggleTheme()" title="Theme">🌗</button>
            <button class="topbar-btn" @click="PP.store.setLang(PP.store.lang === 'id' ? 'en' : 'id')">
              {{ PP.store.lang.toUpperCase() }}
            </button>
            <div class="user-chip" @click="userMenuOpen = !userMenuOpen">
              <span class="avatar">{{ initials }}</span>
              <span class="small">{{ (PP.store.user || {}).username || '?' }}</span>
              <div class="user-menu" v-if="userMenuOpen" @click.stop>
                <router-link :to="{ name: 'settings' }">{{ PP.t('menu.settings') }}</router-link>
                <button @click="logout">Logout</button>
              </div>
            </div>
          </header>
          <main class="content">
            <router-view :key="route.fullPath"></router-view>
          </main>
        </div>

        <div class="toasts">
          <div v-for="t in PP.ui.toasts" :key="t.id" class="toast" :class="t.type"
               @click="PP.ui.dismiss(t.id)">
            <div class="t-title">{{ t.title }}</div>
            <div class="t-msg" v-if="t.message">{{ t.message }}</div>
          </div>
        </div>
        <p-confirm></p-confirm>
      </div>
    `,
  };

  const app = createApp(AppLayout);
  // make the PP namespace (t, ui, store, api, …) reachable from every template
  app.config.globalProperties.PP = PP;
  for (const [name, comp] of Object.entries(PP.components)) {
    app.component(name, comp);
  }
  app.use(router);
  app.mount('#app');
})();
