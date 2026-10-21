// Folio 2026 · main.js — shared behaviours for every page. Each feature is guarded by element presence.
const d = document, html = d.documentElement, w = window;
const $ = (s, r = d) => r.querySelector(s), $$ = (s, r = d) => [...r.querySelectorAll(s)];
const mq = q => w.matchMedia(q).matches;
const fine = () => mq('(hover:hover) and (pointer:fine)');
const motion = () => html.dataset.motion === 'full';
const raf = f => requestAnimationFrame(f);
const store = { get(k) { try { return JSON.parse(localStorage.getItem(k)) || {}; } catch { return {}; } }, set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };
const isHome = html.dataset.page === 'home';

/* ---------- images that fail to load leave their frame (stage colour) instead of a broken icon ---------- */
d.addEventListener('error', e => { if (e.target.tagName === 'IMG') e.target.dataset.broken = ''; }, true);
d.addEventListener('load', e => { if (e.target.tagName === 'IMG') delete e.target.dataset.broken; }, true);
$$('img').forEach(i => { if (i.complete && !i.naturalWidth && i.getAttribute('src')) i.dataset.broken = ''; });

/* ---------- live status region ---------- */
const status = d.createElement('p');
status.className = 'sr-only'; status.setAttribute('aria-live', 'polite'); status.setAttribute('role', 'status');
d.body.append(status);
const say = t => { status.textContent = ''; setTimeout(() => (status.textContent = t), 60); };

/* ---------- preferences: theme, contrast, motion, keys, grid ---------- */
const PREFS = 'folio.prefs';
const state = () => ({
  theme: html.dataset.theme === 'blueprint' ? 'blueprint' : 'paper',
  contrast: html.dataset.contrast === 'more' ? 'more' : 'standard',
  motion: motion() ? 'on' : 'off',
  keys: html.dataset.keys === 'off' ? 'off' : 'on',
  grid: 'grid' in html.dataset
});
const LABEL = {
  theme: s => s.theme === 'blueprint' ? 'Blueprint' : 'Paper',
  contrast: s => s.contrast === 'more' ? 'More' : 'Standard',
  motion: s => s.motion === 'on' ? 'On' : 'Off',
  keys: s => s.keys === 'on' ? 'On' : 'Off',
  grid: s => s.grid ? 'On' : 'Off'
};
const PRESSED = { theme: s => s.theme === 'blueprint', contrast: s => s.contrast === 'more', motion: s => s.motion === 'on', keys: s => s.keys === 'on', grid: s => s.grid };
function sync() {
  const s = state();
  $$('[data-toggle]').forEach(b => {
    const k = b.dataset.toggle;
    if (!PRESSED[k]) return;
    b.setAttribute('aria-pressed', PRESSED[k](s));
    const st = $('[data-state]', b); if (st) st.textContent = LABEL[k](s);
  });
  const ix = { 'ix-act-contrast': s.contrast === 'more' ? 'Standard contrast' : 'More contrast', 'ix-act-motion': s.motion === 'on' ? 'Motion off' : 'Motion on', 'ix-act-grid': s.grid ? 'Hide grid' : 'Show grid', 'ix-act-theme': s.theme === 'blueprint' ? 'Switch to Paper' : 'Switch to Blueprint' };
  for (const id in ix) { const t = $('#' + id + ' .ix__title'); if (t) t.textContent = ix[id]; }
}
function persist(key) {
  const s = state();
  if (key && key !== 'grid') store.set(PREFS, { ...store.get(PREFS), [key]: s[key] });
  sync();
  d.dispatchEvent(new CustomEvent('folio:prefs', { detail: s }));
}
const ACT = {
  theme() {
    const next = html.dataset.theme === 'blueprint' ? 'paper' : 'blueprint';
    const apply = () => { html.dataset.theme = next; persist('theme'); };
    if (motion() && d.startViewTransition && !mq('(prefers-reduced-motion: reduce)')) {
      html.dataset.vt = 'theme';
      const t = d.startViewTransition(apply);
      t.finished.finally(() => delete html.dataset.vt);
    } else apply();
    say(next === 'blueprint' ? 'Blueprint theme' : 'Paper theme');
  },
  contrast() { html.dataset.contrast = html.dataset.contrast === 'more' ? 'standard' : 'more'; persist('contrast'); say(html.dataset.contrast === 'more' ? 'More contrast on' : 'Standard contrast'); },
  motion() {
    if (motion()) { delete html.dataset.motion; delete html.dataset.intro; if (html.dataset.plot !== 'done') html.dataset.plot = 'done'; }
    else html.dataset.motion = 'full';
    persist('motion'); say(motion() ? 'Motion on' : 'Motion off');
  },
  keys() { if (html.dataset.keys === 'off') delete html.dataset.keys; else html.dataset.keys = 'off'; persist('keys'); say(html.dataset.keys === 'off' ? 'Single-key shortcuts off' : 'Single-key shortcuts on'); },
  grid() { toggleGrid(); }
};
d.addEventListener('click', e => {
  const b = e.target.closest('[data-toggle]');
  if (b && ACT[b.dataset.toggle]) ACT[b.dataset.toggle]();
});
sync();

/* ---------- nav tooltips: Esc hides them (WCAG 1.4.13) ---------- */
const tgls = $$('.tgl');
d.addEventListener('keydown', e => { if (e.key === 'Escape') tgls.forEach(t => t.classList.add('tip-off')); });
tgls.forEach(t => ['pointerleave', 'focusout'].forEach(ev => t.addEventListener(ev, () => t.classList.remove('tip-off'))));

/* ---------- keyboard hint: ⌘K or Ctrl K ---------- */
const mac = /mac|iphone|ipad/i.test(navigator.userAgentData?.platform || navigator.platform || '');
$$('[data-kbd]').forEach(k => (k.textContent = mac ? '⌘K' : 'Ctrl K'));

/* ---------- clock (Pacific Time) ---------- */
const clocks = $$('time[data-clock]');
if (clocks.length) {
  const fmt = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Vancouver', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const tick = () => {
    const t = fmt.format(new Date());
    clocks.forEach(c => { c.textContent = t + ' PT'; c.dateTime = t; });
    setTimeout(tick, 60000 - (Date.now() % 60000) + 40);
  };
  tick();
}

/* ---------- nav: active section, wide pill once the title block has scrolled away ---------- */
const nav = $('.nav');
if (nav) {
  const links = new Map($$('.nav__links a[href*="#"]').map(a => [a.hash.slice(1), a]));
  const secs = $$('main section[id]').filter(s => links.has(s.id) || s.id === 'top');
  if (secs.length && 'IntersectionObserver' in w) {
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (!e.isIntersecting) return;
      links.forEach(a => a.removeAttribute('aria-current'));
      links.get(e.target.id)?.setAttribute('aria-current', 'true');
    }), { rootMargin: '-45% 0px -50% 0px' });
    secs.forEach(s => io.observe(s));
  }
  const tb = $('.hero .titleblock');
  if (tb && 'IntersectionObserver' in w) new IntersectionObserver(([e]) => e.isIntersecting ? delete nav.dataset.wide : (nav.dataset.wide = '')).observe(tb);
  else nav.dataset.wide = '';
}

/* ---------- dialogs: [data-dialog-open], [data-close], backdrop, focus return ---------- */
function openDialog(dlg, opener) {
  if (!dlg || dlg.open) return;
  dlg._opener = opener || d.activeElement;
  dlg.showModal();
}
d.addEventListener('click', e => {
  const o = e.target.closest('[data-dialog-open]');
  if (o) { const dl = d.getElementById(o.dataset.dialogOpen); if (o.hasAttribute('commandfor') && 'command' in HTMLButtonElement.prototype) { if (dl) dl._opener = o; } else openDialog(dl, o); return; }
  const c = e.target.closest('dialog [data-close]');
  if (c) { c.closest('dialog').close(); return; }
  if (e.target.tagName === 'DIALOG' && e.target.open) {
    const r = e.target.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) e.target.close();
  }
});
d.addEventListener('close', e => {
  const dlg = e.target;
  if (dlg._opener && !dlg._skipReturn) dlg._opener.focus?.({ preventScroll: true });
  dlg._skipReturn = false;
}, true);

/* ---------- copy email ---------- */
async function copyEmail(btn) {
  const email = btn?.dataset.email || $('[data-copy-email]')?.dataset.email || $('a[href^="mailto:"]')?.href.slice(7).split('?')[0];
  if (!email) return;
  const label = btn && $('[data-copy-label]', btn);
  try {
    await navigator.clipboard.writeText(email);
    if (label) { const was = label.textContent; label.textContent = 'Copied ✓'; clearTimeout(btn._t); btn._t = setTimeout(() => (label.textContent = was === 'Copied ✓' ? 'Copy email' : was), 2400); }
    else say('Email address copied');
  } catch {
    const t = $('[data-email-text]');
    if (t) { const r = d.createRange(); r.selectNodeContents(t); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
    say('Copy failed. The address is selected: ' + email);
  }
}
d.addEventListener('click', e => { const b = e.target.closest('[data-copy-email]'); if (b) copyEmail(b); });

/* ---------- in-page jumps: land on the target even if layout settles during the scroll ---------- */
const padTop = () => parseFloat(getComputedStyle(html).scrollPaddingTop) || 0;
let userScrolled = false;
['wheel', 'touchstart', 'keydown'].forEach(ev => w.addEventListener(ev, () => (userScrolled = true), { passive: true, once: true }));
function settle(t) {
  let done = false;
  const fix = () => {
    if (done) return; done = true;
    if (Math.abs(t.getBoundingClientRect().top - padTop()) > 8) t.scrollIntoView({ behavior: 'instant', block: 'start' });
  };
  if ('onscrollend' in w) w.addEventListener('scrollend', fix, { once: true });
  setTimeout(fix, motion() ? 1800 : 400);
}
function jump(t) { t.scrollIntoView({ behavior: motion() ? 'smooth' : 'auto', block: 'start' }); settle(t); }
d.addEventListener('click', e => {
  const a = e.target.closest?.('a[href*="#"]');
  if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const u = new URL(a.getAttribute('href'), d.baseURI);
  if (u.pathname !== location.pathname || u.search !== location.search || !u.hash) return;
  const t = d.getElementById(decodeURIComponent(u.hash.slice(1)));
  if (t) settle(t);
});
// arriving at #hash: land now, and again whenever fonts or images move the target (until the reader scrolls)
if (location.hash.length > 1) {
  const t = d.getElementById(decodeURIComponent(location.hash.slice(1)));
  const land = () => raf(() => { if (!userScrolled && Math.abs(t.getBoundingClientRect().top - padTop()) > 8) t.scrollIntoView({ behavior: 'instant', block: 'start' }); });
  if (t) { raf(land); d.fonts?.ready.then(land); w.addEventListener('load', land, { once: true }); }
}

/* ---------- Index palette (combobox + listbox) ---------- */
const ix = $('dialog.index');
if (ix) {
  const input = $('.ix__input', ix), items = $$('.ix__item', ix), live = $('[data-ix-status]', ix);
  let active = null, liveT;
  items.forEach((it, i) => { it._i = i; it.setAttribute('aria-selected', 'false'); it._hay = (($('.ix__title', it)?.textContent || '') + ' ' + ($('.ix__no', it)?.textContent || '') + ' ' + (it.dataset.keywords || '')).toLowerCase(); });
  const score = (q, h) => {
    if (!q) return 1;
    const at = h.indexOf(q);
    if (at >= 0) return 100 - Math.min(at, 60) + (at === 0 || h[at - 1] === ' ' ? 40 : 0);
    let s = 0, j = 0, gaps = 0;
    for (const ch of q.replace(/\s+/g, '')) {
      const k = h.indexOf(ch, j);
      if (k < 0) return 0;
      gaps += k - j; s += k === 0 || h[k - 1] === ' ' ? 4 : 1; j = k + 1;
    }
    return gaps > q.length * 2 ? 0 : s + 10 - gaps;
  };
  const visible = () => items.filter(i => !i.hidden);
  const setActive = it => {
    if (active) active.setAttribute('aria-selected', 'false');
    active = it || null;
    if (active) { active.setAttribute('aria-selected', 'true'); input.setAttribute('aria-activedescendant', active.id); active.scrollIntoView({ block: 'nearest' }); }
    else input.setAttribute('aria-activedescendant', '');
  };
  const filter = () => {
    const q = input.value.trim().toLowerCase();
    $$('ul[role=group]', ix).forEach(g => {
      const its = $$('.ix__item', g).map(i => [i, score(q, i._hay)]);
      its.forEach(([i, s]) => (i.hidden = !s));
      if (q) its.filter(x => x[1]).sort((a, b) => b[1] - a[1]).forEach(([i]) => g.append(i));
      else its.sort((a, b) => a[0]._i - b[0]._i).forEach(([i]) => g.append(i));
    });
    const v = visible();
    setActive(q ? v.reduce((b, i) => (score(q, i._hay) > score(q, b._hay) ? i : b), v[0]) : v[0]);
    clearTimeout(liveT);
    liveT = setTimeout(() => (live.textContent = v.length ? `${v.length} result${v.length === 1 ? '' : 's'}` : 'No results'), 250);
  };
  const open = opener => { if (ix.open) return; sync(); input.value = ''; filter(); openDialog(ix, opener); input.focus(); };
  const run = it => {
    if (!it) return;
    const a = it.dataset.action;
    if (a) { ix.close(); a === 'copy-email' ? copyEmail(it.dataset.email ? it : null) : ACT[a]?.(); return; }
    const href = it.dataset.href; if (!href) return;
    const url = new URL(href, d.baseURI);
    ix._skipReturn = true; ix.close();
    if (url.pathname === location.pathname && url.hash) {
      const t = d.getElementById(url.hash.slice(1));
      if (t) { history.pushState(null, '', url.hash); jump(t); t.setAttribute('tabindex', '-1'); t.focus({ preventScroll: true }); return; }
    }
    location.href = url.href;
  };
  input.addEventListener('input', filter);
  input.addEventListener('keydown', e => {
    const v = visible(), i = v.indexOf(active);
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(v[(i + 1) % v.length]); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(v[(i - 1 + v.length) % v.length]); }
    else if (e.key === 'Home' && e.ctrlKey) { e.preventDefault(); setActive(v[0]); }
    else if (e.key === 'End' && e.ctrlKey) { e.preventDefault(); setActive(v[v.length - 1]); }
    else if (e.key === 'Enter') { e.preventDefault(); run(active); }
  });
  ix.addEventListener('pointermove', e => { const it = e.target.closest('.ix__item'); if (it && it !== active) setActive(it); }, { passive: true });
  ix.addEventListener('click', e => { const it = e.target.closest('.ix__item'); if (it) run(it); });
  d.addEventListener('click', e => { const o = e.target.closest('[data-index-open]'); if (o) open(o); });
  w.__folioIndex = open;
}

/* ---------- global keys: ⌘K / Ctrl K, "/", "g" ---------- */
const typing = t => t.closest?.('input,textarea,select,[contenteditable]:not([contenteditable=false])');
d.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === 'k') {
    if (!ix) return;
    e.preventDefault();
    ix.open ? ix.close() : w.__folioIndex(d.activeElement);
    return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey || html.dataset.keys === 'off' || typing(e.target) || d.querySelector('dialog[open]')) return;
  if (e.key === '/' && ix) { e.preventDefault(); w.__folioIndex(d.activeElement); }
  else if (e.key === 'g' || e.key === 'G') toggleGrid();
});

/* ---------- Press G: grid overlay + live dimensions ---------- */
let overlay, dims;
function ensureGrid() {
  if (overlay) return;
  overlay = d.createElement('div'); overlay.className = 'grid-overlay'; overlay.setAttribute('aria-hidden', 'true');
  overlay.innerHTML = '<i></i>'.repeat(12);
  dims = d.createElementNS('http://www.w3.org/2000/svg', 'svg'); dims.setAttribute('class', 'dims'); dims.setAttribute('aria-hidden', 'true');
  d.body.append(overlay, dims);
}
function cols() {
  ensureGrid();
  return $$('i', overlay).map(i => i.getBoundingClientRect()).filter(r => r.width > 0);
}
function toggleGrid(force) {
  ensureGrid();
  const on = force ?? !('grid' in html.dataset);
  if (on) html.dataset.grid = ''; else { delete html.dataset.grid; dims.innerHTML = ''; }
  persist('grid');
  if (on) { const c = cols(); say(`Grid on · ${c.length} col · ${c.length > 1 ? Math.round(c[1].left - c[0].right) : 0} gutter`); }
  else say('Grid off');
}
if ('grid' in html.dataset) ensureGrid();
const MEASURE = '[data-measure],.sec__head,.register__row,.ledger__row,.floor,.legend tr,.portrait,.slide,.hinge,.contact__actions,.tbf__cell,section>*';
function measure(el) {
  if (!('grid' in html.dataset) || !el) return;
  const t = el.closest?.(MEASURE); if (!t) return;
  const r = t.getBoundingClientRect(), x = Math.round(r.left + scrollX), y = Math.round(r.top + scrollY), W = Math.round(r.width), H = Math.round(r.height);
  const c = cols(), first = c.findIndex(k => k.right > r.left + 2), last = c.length - 1 - [...c].reverse().findIndex(k => k.left < r.right - 2);
  const span = first >= 0 && last >= first ? `col ${first + 1} → ${last + 1}` : '';
  const ty = Math.max(y - 16, 8), lx = Math.max(x - 16, 8);
  dims.innerHTML = `<rect x="${x + .5}" y="${y + .5}" width="${W - 1}" height="${H - 1}"/>` +
    `<path d="M${x} ${ty}H${x + W}M${x} ${ty - 6}V${ty + 6}M${x + W} ${ty - 6}V${ty + 6}M${x - 4} ${ty + 4}l8 -8M${x + W - 4} ${ty + 4}l8 -8"/>` +
    `<path d="M${lx} ${y}V${y + H}M${lx - 6} ${y}H${lx + 6}M${lx - 6} ${y + H}H${lx + 6}M${lx - 4} ${y + 4}l8 -8M${lx - 4} ${y + H + 4}l8 -8"/>` +
    `<text x="${x + W / 2}" y="${ty - 8}" text-anchor="middle">${W} × ${H}</text>` +
    (span ? `<text x="${x + W}" y="${ty - 8}" text-anchor="end">${span}</text>` : '');
}
d.addEventListener('pointerover', e => { if (e.pointerType === 'mouse') measure(e.target); }, { passive: true });
d.addEventListener('focusin', e => measure(e.target));

/* ---------- [data-draw] → data-in once the top edge passes 75% of the viewport (any height) ---------- */
if ('IntersectionObserver' in w) {
  html.dataset.io = '';
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting || e.boundingClientRect.bottom < 0) { e.target.dataset.in = ''; io.unobserve(e.target); }
  }), { threshold: 0, rootMargin: '0px 0px -25% 0px' });
  $$('[data-draw]').forEach(el => io.observe(el));
  w.__folioDraw = el => io.observe(el);
}

/* ---------- count-ups: never blank or 0 while waiting. On-screen figures (hero included) keep their value;
   below-the-fold figures are armed off-screen and count the moment they appear ---------- */
const nf = new Intl.NumberFormat('en-CA');
const countEls = $$('data[data-countup]');
const figOf = el => el.closest('.ledger__fig,.scope__fig,.cs-metric__fig') || el;
// the figure's own "from" (ledger "2 → 6", case "212 → 48"), else 0
const fromOf = el => { const f = figOf(el), c = $('.cs-metric__from', f), t = parseFloat((c ? c.textContent : f.firstChild?.nodeType === 3 ? f.firstChild.textContent : '').replace(/,/g, '')); return (c || $('.fig-arrow', f)) && isFinite(t) ? t : 0; };
function countUp(el) {
  const fig = figOf(el), out = $('[aria-hidden]', el) || el, to = +el.value, from = fromOf(el), dur = 900;
  delete fig.dataset.armed; el.dataset.counting = '';
  let t0;
  const step = now => {
    t0 ??= now;
    const p = Math.max(0, Math.min(1, (now - t0) / dur)), v = Math.round(from + (to - from) * (1 - Math.pow(1 - p, 3)));
    out.textContent = nf.format(v);
    if (p < 1) raf(step); else { out.textContent = nf.format(to); delete el.dataset.counting; }
  };
  raf(step);
}
if (countEls.length && motion() && 'IntersectionObserver' in w) {
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { io.unobserve(e.target); countUp(e.target); } }), { threshold: 0 });
  const vh = innerHeight;
  // all reads, then all writes
  const boxes = countEls.map(el => [el, el.closest('.hero') ? null : el.getBoundingClientRect()]);
  boxes.forEach(([el, r]) => {
    if (!r || (r.top < vh && r.bottom > 0) || r.width === 0) return;
    const out = $('[aria-hidden]', el) || el;
    el.style.minWidth = r.width + 'px';
    out.textContent = nf.format(fromOf(el)); figOf(el).dataset.armed = '';
    io.observe(el);
  });
}
/* print or save as PDF: everything in its final state */
w.addEventListener('beforeprint', () => {
  $$('[data-draw]').forEach(el => (el.dataset.in = ''));
  $$('[data-armed]').forEach(f => delete f.dataset.armed);
  countEls.forEach(el => { const o = $('[aria-hidden]', el); if (o) o.textContent = nf.format(+el.value); });
});

/* ---------- hero: T-square, intro clean-up, the plot and the WebGL wash ---------- */
const hero = $('.hero');
if (hero) {
  const tsq = $('.tsquare', hero), rx = tsq && $('.tsquare__rx', tsq), ry = tsq && $('.tsquare__ry', tsq);
  let pend = null, queued = false;
  if (tsq) {
    hero.addEventListener('pointermove', e => {
      if (e.pointerType !== 'mouse' || !motion() || !fine() || /pending|playing/.test(html.dataset.plot || '')) return;
      pend = e;
      if (queued) return;
      queued = true;
      raf(() => {
        queued = false;
        const r = tsq.getBoundingClientRect(), x = Math.round(pend.clientX - r.left), y = Math.round(pend.clientY - r.top);
        if (x < 0 || y < 0 || x > r.width || y > r.height) { delete hero.dataset.tsq; return; }
        tsq.style.setProperty('--tx', x + 'px'); tsq.style.setProperty('--ty', y + 'px');
        rx.textContent = 'X ' + x; ry.textContent = 'Y ' + y;
        hero.dataset.tsq = '';
      });
    }, { passive: true });
    hero.addEventListener('pointerleave', () => delete hero.dataset.tsq, { passive: true });
  }
  if ('intro' in html.dataset) {
    setTimeout(() => {
      if (html.dataset.plot === 'pending') { html.dataset.plot = 'done'; try { sessionStorage.setItem('plotted', '1'); } catch {} }
    }, 2700);
    setTimeout(() => { if (html.dataset.plot === 'playing') html.dataset.plot = 'done'; }, 6000);
    setTimeout(() => delete html.dataset.intro, 3400);
  }
  if (isHome) {
    const save = navigator.connection?.saveData === true;
    if (!motion() || save || html.dataset.contrast === 'more') { if (html.dataset.plot === 'pending') html.dataset.plot = 'done'; }
    else {
      import(new URL('./hero-gl.js', import.meta.url)).then(m => {
        const r = hero.getBoundingClientRect(), inView = r.bottom > 0 && r.top < innerHeight, late = performance.now() > 2000;
        try { if (inView && m.init) m.init({ plot: html.dataset.plot === 'pending' && !late }); else if (html.dataset.plot === 'pending') html.dataset.plot = 'done'; } catch { if (html.dataset.plot !== 'done') html.dataset.plot = 'done'; }
        const hinge = $('.hinge');
        try { if (hinge && m.initHinge) m.initHinge(hinge); } catch {}
      }).catch(() => { if (html.dataset.plot === 'pending') html.dataset.plot = 'done'; });
    }
  }
}

/* ---------- register: preview + filter live region (home) ---------- */
const reg = $('.register'), preview = $('.preview'), room = $('#work');
if (reg && preview) {
  const stage = $('.preview__stage', preview), img = $('.preview__img', preview), no = $('[data-preview-no]', preview), cap = $('[data-preview-cap]', preview);
  const idle = [no?.textContent, cap?.textContent];
  let warmed = false, cur = null, leaveT;
  const warm = () => { if (warmed) return; warmed = true; $$('img', reg).forEach(i => (i.loading = 'eager')); };
  const show = row => {
    if (!row || row === cur || getComputedStyle(preview).display === 'none') return;
    clearTimeout(leaveT); cur = row;
    const sheet = $('.register__no', row)?.textContent.replace('Sheet', '').trim();
    preview.style.setProperty('--p-stage', row.style.getPropertyValue('--stage'));
    preview.style.setProperty('--p-pigment', row.style.getPropertyValue('--stage-pigment'));
    preview.dataset.active = row.dataset.slug;
    if (room) { room.style.setProperty('--room', row.style.getPropertyValue('--stage')); room.style.setProperty('--room-dark', row.style.getPropertyValue('--stage-dark')); room.dataset.room = ''; }
    $$('[data-plot]', preview).forEach(p => p.toggleAttribute('data-on', p.dataset.plot === sheet));
    if (no) no.textContent = sheet; if (cap) cap.textContent = $('.register__sector', row)?.textContent.replace('Sector:', '').trim() || '';
    const src = $('.register__cover img', row);
    const url = src && (src.currentSrc || src.src);
    delete preview.dataset.shown; delete preview.dataset.wipe;
    if (!url) return;
    const go = () => { if (cur !== row) return; void stage.offsetWidth; preview.dataset.shown = ''; preview.dataset.wipe = ''; };
    if (img.src !== url) { img.src = url; img.decode().then(go, () => {}); } else go();
  };
  const reset = () => {
    cur = null;
    ['active', 'shown', 'wipe'].forEach(k => delete preview.dataset[k]);
    if (room) delete room.dataset.room;
    $$('[data-plot]', preview).forEach(p => p.removeAttribute('data-on'));
    if (no) no.textContent = idle[0]; if (cap) cap.textContent = idle[1];
  };
  reg.addEventListener('pointerenter', warm, { passive: true });
  reg.addEventListener('focusin', e => { warm(); show(e.target.closest('.register__row')); });
  reg.addEventListener('pointerover', e => { if (e.pointerType === 'mouse') show(e.target.closest('.register__row')); }, { passive: true });
  reg.addEventListener('pointerleave', () => { clearTimeout(leaveT); leaveT = setTimeout(() => { if (!reg.contains(d.activeElement)) reset(); }, 500); }, { passive: true });
  reg.addEventListener('focusout', e => { if (!reg.contains(e.relatedTarget)) { clearTimeout(leaveT); leaveT = setTimeout(reset, 300); } });
  w.__folioPreview = show;
}
const filterStatus = $('[data-filter-status]');
if (reg && filterStatus) {
  d.addEventListener('change', e => {
    if (e.target.name !== 'sector') return;
    const rows = $$('.register__row', reg), n = rows.filter(r => getComputedStyle(r).display !== 'none').length;
    filterStatus.textContent = n === rows.length ? `Showing all ${n} sheets` : `Showing ${n} of ${rows.length} sheets`;
  });
}

/* ---------- footer: page weight on the wire (LCP only when it is good, ≤ 2.5 s) ---------- */
const wt = $('[data-weight]');
if (wt && w.PerformanceObserver) {
  let lcp = 0;
  try { new PerformanceObserver(l => { const e = l.getEntries().pop(); if (e) lcp = e.startTime; }).observe({ type: 'largest-contentful-paint', buffered: true }); } catch {}
  w.addEventListener('load', () => setTimeout(() => {
    const b = performance.getEntriesByType('navigation').concat(performance.getEntriesByType('resource')).reduce((a, e) => a + (e.transferSize || 0), 0);
    if (b > 2048) { wt.textContent = `${nf.format(Math.round(b / 1024))} KB${lcp && lcp <= 2500 ? ` · LCP ${(lcp / 1000).toFixed(1)} s` : ''}`; wt.hidden = false; }
  }, 3000), { once: true });
}

/* ---------- 404: a mini register, and a guess at the sheet that was meant ---------- */
const nfReg = $('[data-nf-reg]');
if (nfReg) fetch('./').then(r => r.ok ? r.text() : Promise.reject()).then(t => {
  const rows = $$('.register__row', new DOMParser().parseFromString(t, 'text/html')), list = $('ol', nfReg);
  const words = location.pathname.toLowerCase().split(/[^a-z0-9]+/).filter(x => x.length > 2);
  let best = null, top = 0;
  rows.forEach(r => {
    const a = $('a', r), no = $('.register__no', r)?.textContent.replace('Sheet', '').trim(), ti = $('.register__title', r)?.textContent.replace('Project:', '').trim();
    const li = d.createElement('li'), l = d.createElement('a');
    l.href = a.getAttribute('href'); l.className = 'nf__row'; l.style.cssText = r.getAttribute('style') || '';
    l.innerHTML = '<span class="nf__rno"><i></i></span><span class="nf__rt"></span><span class="nf__rs"></span>';
    l.firstChild.append(no); l.children[1].textContent = ti; l.children[2].textContent = $('.register__sector', r)?.textContent.replace('Sector:', '').trim() || '';
    li.append(l); list.append(li);
    const hay = (r.dataset.slug + ' ' + ti + ' ' + no).toLowerCase(), sc = words.filter(x => hay.includes(x)).length;
    if (sc > top) { top = sc; best = [l, no, ti]; }
  });
  if (rows.length) nfReg.hidden = false;
  const g = $('[data-nf-guess]');
  if (g && best) { const a = $('a', g); a.href = best[0].getAttribute('href'); a.textContent = `${best[1]} · ${best[2]}`; g.hidden = false; best[0].dataset.guess = ''; }
}).catch(() => {});

/* ---------- home-only behaviours (ledger, plates, studio) ---------- */
if (isHome) import(new URL('./home.js', import.meta.url)).catch(() => {});

/* ---------- view transitions: sheet slide (home ⇄ case) ---------- */
const clearNames = () => $$('[style*="view-transition-name"]').forEach(el => (el.style.viewTransitionName = ''));
const rowFor = path => reg && $$('.register__row', reg).find(r => { const a = $('a', r); return a && new URL(a.getAttribute('href'), d.baseURI).pathname === path; });
const nameRow = row => {
  const desktop = preview && getComputedStyle(preview).display !== 'none';
  if (desktop && w.__folioPreview) { w.__folioPreview(row); delete preview.dataset.wipe; preview.dataset.shown = ''; }
  const thumb = desktop ? $('.preview__stage', preview) : $('.register__cover', row);
  if (thumb) thumb.style.viewTransitionName = 'sheet';
  const t = $('.register__title', row); if (t) t.style.viewTransitionName = 'sheet-title';
};
let lastLink = null;
d.addEventListener('click', e => { lastLink = e.target.closest?.('a[href]') || null; }, true);
const VT = 'folio.vt';
const plateFig = li => li && $('.plate__fig picture', li);
if (isHome) {
  w.addEventListener('pageswap', e => {
    if (!e.viewTransition) return;
    clearNames();
    const plate = lastLink?.closest('.plate');
    if (plate && motion()) {
      const f = plateFig(plate);
      if (f) { f.style.viewTransitionName = 'sheet'; try { sessionStorage.setItem(VT, 'plate:' + $$('.plate').indexOf(plate)); } catch {} return; }
    }
    try { sessionStorage.removeItem(VT); } catch {}
    let row = null;
    try { row = rowFor(new URL(e.activation.entry.url).pathname); } catch {}
    if (!motion() || !row) { e.viewTransition.skipTransition(); return; }
    nameRow(row);
  });
  w.addEventListener('pagereveal', e => {
    clearNames();
    if (!e.viewTransition) return;
    if (!motion()) { e.viewTransition.skipTransition(); return; }
    let row = null, from = '';
    try { from = sessionStorage.getItem(VT) || ''; sessionStorage.removeItem(VT); } catch {}
    if (from.startsWith('plate:')) {
      const f = plateFig($$('.plate')[+from.slice(6)]), r = f?.getBoundingClientRect();
      if (r && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth) f.style.viewTransitionName = 'sheet';
      e.viewTransition.finished.then(clearNames, clearNames);
      return;
    }
    try { row = rowFor(new URL(navigation.activation.from.url).pathname); } catch {}
    if (row) { const r = row.getBoundingClientRect(); if (r.bottom > 0 && r.top < innerHeight) nameRow(row); }
    e.viewTransition.finished.then(clearNames, clearNames);
  });
} else {
  w.addEventListener('pagereveal', e => { if (e.viewTransition) html.dataset.arrived = 'vt'; });
}
