// Folio 2026 · home.js — behaviours that exist only on the cover sheet (loaded by main.js on the home page).
const d = document, html = d.documentElement, w = window;
const $ = (s, r = d) => r.querySelector(s), $$ = (s, r = d) => [...r.querySelectorAll(s)];
const motion = () => html.dataset.motion === 'full';
const raf = f => requestAnimationFrame(f);

/* ---------- ledger: an exclusive accordion that never throws the reader off-screen ---------- */
$$('details.ledger__row').forEach(dt => {
  const sm = $('summary', dt);
  if (!sm) return;
  const mark = () => { dt._y = sm.getBoundingClientRect().top; };
  sm.addEventListener('pointerdown', mark);
  sm.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') mark(); });
  sm.addEventListener('click', () => { if (dt._y == null) mark(); });
  dt.addEventListener('toggle', () => {
    if (!dt.open || dt._y == null) { dt._y = null; return; }
    const y0 = dt._y; dt._y = null;
    raf(() => { const dy = sm.getBoundingClientRect().top - y0; if (Math.abs(dy) > 1) w.scrollBy({ top: dy, behavior: 'instant' }); });
  });
});

/* ---------- plates (A-050): pinned two-row pan on desktop, swipe row on phones, contact sheet otherwise ---------- */
const plates = $('#plates');
if (plates) {
  const stage = $('.plates__stage', plates), vp = $('.plates__viewport', plates), track = $('.plates__track', plates), head = $('.plates__head', plates);
  const items = $$('.plate', track), links = items.map(li => $('a', li)), n = items.length;
  const cnt = $('[data-plates-count]', plates), tot = $('[data-plates-total]', plates), live = $('[data-plates-status]', plates);
  const rule = $('.plates__rule', plates), prev = $('[data-plates-prev]', plates), next = $('[data-plates-next]', plates);
  const pad2 = i => String(i).padStart(2, '0');
  if (!n) plates.hidden = true;
  else {
    plates.style.setProperty('--na', Math.ceil(n / 2)); plates.style.setProperty('--nb', Math.floor(n / 2));
    if (tot) tot.textContent = pad2(n);
    // the sheet's tint follows the projects in register order (paper: stage colour; blueprint: its dark twin)
    const seen = [], dark = [];
    items.forEach(li => { const c = li.style.getPropertyValue('--stage').trim(); if (c && !seen.includes(c)) { seen.push(c); dark.push(li.style.getPropertyValue('--stage-dark').trim()); } });
    for (let i = 0; i < 6; i++) { const k = Math.min(i, seen.length - 1); if (k >= 0) { plates.style.setProperty('--l' + (i + 1), seen[k]); plates.style.setProperty('--d' + (i + 1), dark[k] || seen[k]); } }
    const mode = () => getComputedStyle(stage).position === 'sticky' ? 'pin' : getComputedStyle(track).display === 'grid' ? 'sheet' : 'row';
    let cur = 0;
    const show = i => { cur = i; if (cnt) cnt.textContent = pad2(i + 1); rule?.style.setProperty('--pp', n > 1 ? i / (n - 1) : 1); if (prev) prev.disabled = i === 0; if (next) next.disabled = i === n - 1; };
    show(0);
    // pinned: where the page must be for plate i to sit mid-screen (rows pan in opposite directions)
    const geo = () => {
      const pw = items[0].offsetWidth, gap = n > 2 ? items[2].offsetLeft - items[0].offsetLeft - pw : 0, card = head.offsetWidth;
      const m = parseFloat(getComputedStyle(track).paddingLeft) || 0, W = stage.clientWidth;
      const na = Math.ceil(n / 2), nb = Math.floor(n / 2), wa = na * pw + (na - 1) * gap, wb = nb * pw + (nb - 1) * gap;
      return { pw, gap, m, W, A: [card + gap, W - 2 * m - wa], B: [W - 2 * m - wb, 0] };
    };
    const progressFor = i => {
      const g = geo(), [t0, t1] = i % 2 ? g.B : g.A, x0 = items[i].offsetLeft, want = g.W / 2 - g.pw / 2 - x0;
      return t1 === t0 ? 0 : Math.max(0, Math.min(1, (want - t0) / (t1 - t0)));
    };
    const pinTop = p => { const r = plates.getBoundingClientRect(); return Math.round(r.top + scrollY + p * (plates.offsetHeight - innerHeight)); };
    // keyboard: a focused plate is always brought on screen
    track.addEventListener('focusin', e => {
      const li = e.target.closest('.plate'), i = items.indexOf(li);
      if (i < 0) return;
      show(i);
      const md = mode();
      if (md === 'pin') w.scrollTo({ top: pinTop(progressFor(i)), behavior: 'instant' });
      else if (md === 'row') li.scrollIntoView({ block: 'nearest', inline: 'center', behavior: motion() ? 'smooth' : 'instant' });
    });
    track.addEventListener('keydown', e => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const i = items.indexOf(e.target.closest('.plate'));
      if (i < 0) return;
      const j = Math.max(0, Math.min(n - 1, i + (e.key === 'ArrowRight' ? 1 : -1)));
      if (j !== i) { e.preventDefault(); links[j]?.focus(); }
    });
    // swipe row: buttons, counter and a polite status only when a button moves it
    const go = (i, say) => {
      i = Math.max(0, Math.min(n - 1, i));
      vp.scrollTo({ left: items[i].offsetLeft - (vp.clientWidth - items[i].offsetWidth) / 2, behavior: motion() ? 'smooth' : 'instant' });
      show(i);
      if (say && live) { live.textContent = ''; setTimeout(() => (live.textContent = `Plate ${i + 1} of ${n}: ${$('.plate__title', items[i])?.textContent || ''}`), 60); }
    };
    prev?.addEventListener('click', () => go(cur - 1, true));
    next?.addEventListener('click', () => go(cur + 1, true));
    if ('IntersectionObserver' in w) {
      const rio = new IntersectionObserver(es => { if (mode() !== 'row') return; es.forEach(e => { if (e.isIntersecting) show(items.indexOf(e.target)); }); }, { root: vp, threshold: .6 });
      items.forEach(li => rio.observe(li));
      // pinned and contact-sheet plates sit outside lazy loading's reach (translated or far below): fetch them before they are needed
      // decode() keeps the bitmaps ready, so a plate panned in fast never shows as an empty frame
      const warm = new IntersectionObserver(([e]) => { if (e.isIntersecting && mode() !== 'row') { $$('img', track).forEach(i => { i.loading = 'eager'; i.decode?.().catch(() => {}); }); warm.disconnect(); } }, { rootMargin: '100% 0px' });
      warm.observe(plates);
    }
    // pinned counter: follows the pan, one step per plate
    let ticking = false, inview = false;
    const tick = () => {
      ticking = false;
      if (mode() !== 'pin') return;
      const r = plates.getBoundingClientRect(), p = Math.max(0, Math.min(1, -r.top / Math.max(1, r.height - innerHeight))), i = Math.round(p * (n - 1));
      if (i !== cur) show(i);
    };
    if ('IntersectionObserver' in w) new IntersectionObserver(([e]) => (inview = e.isIntersecting)).observe(plates);
    w.addEventListener('scroll', () => { if (inview && !ticking) { ticking = true; raf(tick); } }, { passive: true });
  }
}

/* ---------- studio: carousel + spotlight ---------- */
const gal = $('[data-carousel]');
if (gal) {
  const track = $('.gallery__track', gal), slides = $$('.slide', gal), count = $('[data-count]', gal), prev = $('[data-prev]', gal), next = $('[data-next]', gal);
  let idx = 0;
  const set = i => { idx = i; if (count) count.textContent = i + 1; if (prev) prev.disabled = i === 0; if (next) next.disabled = i === slides.length - 1; slides.forEach((s, k) => (s.inert = k !== i)); };
  const go = i => { i = Math.max(0, Math.min(slides.length - 1, i)); track.scrollTo({ left: slides[i].offsetLeft - slides[0].offsetLeft, behavior: motion() ? 'smooth' : 'auto' }); set(i); };
  prev?.addEventListener('click', () => go(idx - 1));
  next?.addEventListener('click', () => go(idx + 1));
  gal.addEventListener('keydown', e => { if (e.key === 'ArrowLeft') { e.preventDefault(); go(idx - 1); } else if (e.key === 'ArrowRight') { e.preventDefault(); go(idx + 1); } });
  if ('IntersectionObserver' in w) {
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) set(slides.indexOf(e.target)); }), { root: track, threshold: .6 });
    slides.forEach(s => io.observe(s));
  }
  set(0);
}
const studio = $('.studio');
if (studio) {
  let q = null;
  studio.addEventListener('pointermove', e => {
    if (e.pointerType !== 'mouse' || !motion()) return;
    const first = !q; q = e;
    if (!first) return;
    raf(() => {
      const r = studio.getBoundingClientRect();
      studio.style.setProperty('--spot-x', ((q.clientX - r.left) / r.width * 100).toFixed(1) + '%');
      studio.style.setProperty('--spot-y', ((q.clientY - r.top) / r.height * 100).toFixed(1) + '%');
      q = null;
    });
  }, { passive: true });
}
