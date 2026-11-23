/* Login page */
PP.pages = PP.pages || {};
PP.pages.login = {
  data: () => ({ username: '', password: '', otp: '', needOtp: false, busy: false }),
  methods: {
    async submit() {
      this.busy = true;
      try {
        const data = await PP.api('auth/login', {
          method: 'POST',
          body: { username: this.username, password: this.password, otp: this.otp || null },
        });
        PP.store.user = data;
        PP.store.authed = true;
        this.$router.push({ name: 'dashboard' });
      } catch (e) {
        const msg = String(e.message || '');
        if (/2FA/i.test(msg)) {
          this.needOtp = true;
          PP.ui.warn(msg);
        } else {
          PP.ui.error(PP.t('login.submit'), msg);
        }
      } finally {
        this.busy = false;
      }
    },
  },
  template: `
  <div class="login-wrap">
    <div class="login-card">
      <div class="login-logo">
        <img src="/favicon.svg" alt="logo">
        <div class="name">PanelPro</div>
      </div>
      <div class="login-sub">{{ PP.t('login.subtitle') }}</div>
      <form @submit.prevent="submit">
        <div class="field">
          <label>{{ PP.t('common.username') }}</label>
          <input class="input" v-model="username" autocomplete="username" required autofocus>
        </div>
        <div class="field">
          <label>{{ PP.t('common.password') }}</label>
          <input class="input" type="password" v-model="password" autocomplete="current-password" required>
        </div>
        <div class="field" v-if="needOtp">
          <label>{{ PP.t('login.otp') }}</label>
          <input class="input" v-model="otp" :placeholder="PP.t('login.otpHint')" inputmode="numeric">
        </div>
        <button class="btn primary" style="width:100%; justify-content:center"
                :disabled="busy">{{ busy ? '…' : PP.t('login.submit') }}</button>
      </form>
    </div>
  </div>`,
};
