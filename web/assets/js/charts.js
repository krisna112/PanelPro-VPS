/* PanelPro original canvas charts — line/area charts, no libraries.
   API: PP.charts.line(canvasEl, {
          series: [{ data: [{x, y}], color, fill, width }],
          yFormat: fn(value) -> string,
          grid: true, minX, maxX (optional)
        }) */
(function () {
  function prepare(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(rect.width, 10), h = Math.max(rect.height, 10);
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h };
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function niceMax(value) {
    if (value <= 0) return 1;
    const exp = Math.floor(Math.log10(value));
    const base = Math.pow(10, exp);
    const n = value / base;
    const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
    return nice * base;
  }

  function line(canvas, opts) {
    if (!canvas) return;
    const { ctx, w, h } = prepare(canvas);
    const pad = { l: 44, r: 10, t: 10, b: 22 };
    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
    const series = (opts.series || []).filter(s => s.data && s.data.length);
    if (!series.length) {
      ctx.fillStyle = cssVar('--faint');
      ctx.font = '12px ' + cssVar('--font');
      ctx.textAlign = 'center';
      ctx.fillText('—', w / 2, h / 2);
      return;
    }

    let minX = opts.minX !== undefined ? opts.minX : Infinity;
    let maxX = opts.maxX !== undefined ? opts.maxX : -Infinity;
    let maxY = 0, minY = Infinity;
    for (const s of series) {
      for (const p of s.data) {
        if (opts.minX === undefined) { minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); }
        maxY = Math.max(maxY, p.y);
        minY = Math.min(minY, p.y);
      }
    }
    if (maxX === minX) maxX = minX + 1;
    if (minY > 0 && !opts.zeroMin) minY = 0;
    const yTop = niceMax(maxY - minY || 1) + minY;

    const X = x => pad.l + ((x - minX) / (maxX - minX)) * iw;
    const Y = y => pad.t + ih - ((y - minY) / (yTop - minY || 1)) * ih;

    // grid + y labels
    if (opts.grid !== false) {
      ctx.strokeStyle = cssVar('--border-soft');
      ctx.fillStyle = cssVar('--faint');
      ctx.font = '10px ' + cssVar('--font');
      ctx.textAlign = 'right';
      const steps = 4;
      for (let i = 0; i <= steps; i++) {
        const v = minY + ((yTop - minY) * i) / steps;
        const y = Y(v);
        ctx.beginPath();
        ctx.moveTo(pad.l, y);
        ctx.lineTo(w - pad.r, y);
        ctx.stroke();
        const label = opts.yFormat ? opts.yFormat(v) : Math.round(v * 10) / 10;
        ctx.fillText(String(label), pad.l - 6, y + 3);
      }
    }

    // x labels (first / middle / last)
    ctx.fillStyle = cssVar('--faint');
    ctx.font = '10px ' + cssVar('--font');
    ctx.textAlign = 'center';
    const timeLabel = v => {
      const d = new Date(v * 1000);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };
    [minX, (minX + maxX) / 2, maxX].forEach(x => ctx.fillText(timeLabel(x), X(x), h - 6));

    // series
    for (const s of series) {
      const pts = s.data.map(p => [X(p.x), Y(p.y)]);
      ctx.lineWidth = s.width || 2;
      ctx.strokeStyle = s.color || cssVar('--accent');
      ctx.beginPath();
      pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
      ctx.stroke();
      if (s.fill) {
        ctx.lineTo(pts[pts.length - 1][0], Y(minY));
        ctx.lineTo(pts[0][0], Y(minY));
        ctx.closePath();
        const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + ih);
        grad.addColorStop(0, (s.color || cssVar('--accent')) + '55');
        grad.addColorStop(1, (s.color || cssVar('--accent')) + '00');
        ctx.fillStyle = grad;
        ctx.fill();
      }
    }
  }

  PP.charts = { line, niceMax };
})();
