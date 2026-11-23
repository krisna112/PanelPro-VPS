/* PanelPro global client state (no Pinia — a small reactive store). */
(function () {
  const savedLang = localStorage.getItem('pp_lang') || 'id';
  const savedTheme = localStorage.getItem('pp_theme') || 'dark';

  PP.store = Vue.reactive({
    user: null,
    authed: null,       // null = unknown, true / false after first check
    lang: PP.langs.includes(savedLang) ? savedLang : 'id',
    theme: savedTheme === 'light' ? 'light' : 'dark',
    sidebarOpen: false,
    pendingAuth: null,  // shared promise for the login guard
  });

  PP.store.applyTheme = function () {
    document.documentElement.dataset.theme = PP.store.theme;
    localStorage.setItem('pp_theme', PP.store.theme);
  };
  PP.store.toggleTheme = function () {
    PP.store.theme = PP.store.theme === 'dark' ? 'light' : 'dark';
    PP.store.applyTheme();
  };
  PP.store.setLang = function (lang) {
    if (PP.langs.includes(lang)) {
      PP.store.lang = lang;
      localStorage.setItem('pp_lang', lang);
    }
  };
  PP.store.applyTheme();

  /* Resolve the current session once and reuse the result in guards. */
  PP.store.resolveAuth = async function () {
    if (PP.store.pendingAuth) return PP.store.pendingAuth;
    PP.store.pendingAuth = (async () => {
      try {
        const me = await PP.api('auth/me');
        PP.store.user = me;
        PP.store.authed = true;
        return true;
      } catch (e) {
        PP.store.user = null;
        PP.store.authed = false;
        return false;
      } finally {
        PP.store.pendingAuth = null;
      }
    })();
    return PP.store.pendingAuth;
  };
})();
