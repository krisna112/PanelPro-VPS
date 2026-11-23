/* PanelPro shared Vue components (registered globally by app.js).
   All templates are plain strings — no build step. */
(function () {
  const { ref, computed } = Vue;

  PP.components = {};

  PP.components['p-badge'] = {
    props: { kind: { type: String, default: 'gray' } },
    template: `<span class="badge" :class="kind"><slot /></span>`,
  };

  PP.components['p-switch'] = {
    props: { modelValue: Boolean },
    emits: ['update:modelValue'],
    template: `
      <label class="switch">
        <input type="checkbox" :checked="modelValue" @change="$emit('update:modelValue', $event.target.checked)">
        <span class="track"><span class="thumb"></span></span>
      </label>`,
  };

  PP.components['p-modal'] = {
    props: { open: Boolean, title: String, size: { type: String, default: '' } },
    emits: ['close'],
    template: `
      <transition name="fade">
        <div v-if="open" class="modal-mask" @mousedown.self="$emit('close')">
          <div class="modal" :class="size">
            <div class="modal-head">
              <h3>{{ title }}</h3>
              <button class="btn icon ghost close" @click="$emit('close')">✕</button>
            </div>
            <slot />
            <div class="modal-foot" v-if="$slots.foot"><slot name="foot" /></div>
          </div>
        </div>
      </transition>`,
  };

  PP.components['p-tabs'] = {
    props: { tabs: Array, modelValue: String },
    emits: ['update:modelValue'],
    template: `
      <div class="tabs">
        <button v-for="t in tabs" :key="t.key" class="tab"
                :class="{ active: modelValue === t.key }"
                @click="$emit('update:modelValue', t.key)">{{ t.label }}</button>
      </div>`,
  };

  PP.components['p-progress'] = {
    props: { value: { type: Number, default: 0 } },
    computed: {
      cls() {
        if (this.value >= 90) return 'danger';
        if (this.value >= 75) return 'warn';
        return '';
      },
    },
    template: `
      <div class="progress"><div class="fill" :class="cls" :style="{ width: Math.min(100, value) + '%' }"></div></div>`,
  };

  PP.components['p-stat'] = {
    props: { label: String, value: [String, Number], hint: String },
    template: `
      <div class="card stat-card">
        <div class="label">{{ label }}</div>
        <div class="value">{{ value }}</div>
        <div class="hint" v-if="hint">{{ hint }}</div>
        <slot />
      </div>`,
  };

  /* Generic table: cols = [{key, label, width?}], rows = [{}].
     Column cells render slot `col-<key>` (with row) when provided. */
  PP.components['p-table'] = {
    props: { cols: Array, rows: { type: Array, default: () => [] }, empty: String },
    template: `
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th v-for="c in cols" :key="c.key" :style="c.width ? { width: c.width } : {}">{{ c.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in rows" :key="i">
              <td v-for="c in cols" :key="c.key" :class="c.cls">
                <slot :name="'col-' + c.key" :row="row" :index="i">
                  {{ row[c.key] !== undefined && row[c.key] !== null ? row[c.key] : '-' }}
                </slot>
              </td>
            </tr>
            <tr v-if="!rows.length"><td :colspan="cols.length"><div class="table-empty">{{ empty || '—' }}</div></td></tr>
          </tbody>
        </table>
      </div>`,
  };

  PP.components['p-confirm'] = {
    computed: {
      state() { return PP.ui.confirmState; },
    },
    template: `
      <transition name="fade">
        <div v-if="state.open" class="modal-mask" @mousedown.self="PP.ui.confirmAnswer(false)">
          <div class="modal sm">
            <div class="modal-head"><h3>{{ state.title || PP.t('common.confirm') }}</h3></div>
            <p class="muted">{{ state.message }}</p>
            <div class="modal-foot">
              <button class="btn" @click="PP.ui.confirmAnswer(false)">{{ PP.t('common.cancel') }}</button>
              <button class="btn" :class="state.danger ? 'danger' : 'primary'" @click="PP.ui.confirmAnswer(true)">
                {{ PP.t('common.yes') }}
              </button>
            </div>
          </div>
        </div>
      </transition>`,
  };
})();
