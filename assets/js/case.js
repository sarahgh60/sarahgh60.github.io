// Folio 2026 · case.js · case pages only.
// Before/after compare (wipe and overlay), figure lightbox with zoom, key-screens reel, the title
// block's sheet data, metric method links, [ / ] sheet paging, and the next-sheet cards as
// view-transition sources. Global behaviour (theme, Index, draw-on-view, count-ups, dialogs,
// page reveal) lives in main.js.
const doc = document;
const html = doc.documentElement;
const $$ = (s, r = doc) => [...r.querySelectorAll(s)];
const motion = () => html.dataset.motion === 'full';
const mq = (q) => matchMedia(q);

// ---------- before / after ----------
for (const fig of $$('.compare')) {
  const range = fig.querySelector('.compare__range');
  const stage = fig.querySelector('.compare__stage');
  if (!range || !stage) continue;
  const set = () => {
    const v = +range.value;
    fig.style.setProperty('--pos', v);
    range.setAttribute('aria-valuetext', `${v}% before, ${100 - v}% after`);
  };
  range.addEventListener('input', set);
  const drag = (on) => () => fig.classList.toggle('is-dragging', on);
  stage.addEventListener('pointerdown', drag(true), { passive: true });
  for (const t of ['pointerup', 'pointercancel', 'pointerleave']) stage.addEventListener(t, drag(false), { passive: true });
  const sec = fig.closest('section') || doc;
  for (const r of $$('.compare__modes input', sec)) {
    r.addEventListener('change', () => {
      if (!r.checked) return;
      fig.dataset.mode = r.value;
      range.setAttribute('aria-label', r.value === 'overlay' ? 'Fade between before and after' : 'Compare before and after');
    });
  }
  set();
  fig.classList.add('is-ready');
}

// ---------- lightbox ----------
const box = doc.querySelector('.lightbox');
// one entry per distinct image, so the counter reflects real figures
const seenHref = new Set();
const figs = $$('[data-lightbox]').filter((f) => {
  const a = f.querySelector('a[data-avif]');
  if (!a || seenHref.has(a.href)) return false;
  seenHref.add(a.href);
  return true;
});
if (box && figs.length) {
  const img = box.querySelector('.lightbox__img');
  const cap = box.querySelector('.lightbox__cap');
  const count = box.querySelector('.lightbox__count');
  const zoomBtn = box.querySelector('.lightbox__zoom');
  const hint = box.querySelector('.lightbox__hint');
  const coarse = mq('(pointer:coarse)');
  let at = 0;
  let trigger = null;
  let hintT = 0;
  const zoomable = () => {
    const im = img.querySelector('img');
    if (!im) return false;
    const w = +im.getAttribute('width') || im.naturalWidth;
    return w > img.clientWidth * 1.25;
  };
  const setZoom = (on) => {
    const im = img.querySelector('img');
    if (!im) return;
    if (on) {
      const w = +im.getAttribute('width');
      // reading size: ~2.4× a phone's width; the plate's own pixels on a larger screen
      const small = coarse.matches || innerWidth < 600;
      const zw = Math.round(small ? Math.min(w, innerWidth * 2.4) : w);
      box.style.setProperty('--zw', `${zw}px`);
      box.dataset.zoom = '';
      requestAnimationFrame(() => {
        img.scrollLeft = (img.scrollWidth - img.clientWidth) / 2;
        img.scrollTop = (img.scrollHeight - img.clientHeight) / 2;
      });
      if (hint) {
        hint.classList.add('is-on');
        clearTimeout(hintT);
        hintT = setTimeout(() => hint.classList.remove('is-on'), 2200);
      }
    } else {
      delete box.dataset.zoom;
    }
    if (zoomBtn) zoomBtn.setAttribute('aria-pressed', String(on));
  };
  const show = (i) => {
    at = (i + figs.length) % figs.length;
    const fig = figs[at];
    const a = fig.querySelector('a[data-avif]');
    const src = fig.querySelector('img');
    const im = doc.createElement('img');
    im.width = +a.dataset.w;
    im.height = +a.dataset.h;
    im.alt = src ? src.alt : '';
    // always the full-size file here (the page may show a smaller variant)
    const pic = doc.createElement('picture');
    const s = doc.createElement('source');
    s.type = 'image/avif';
    s.srcset = a.dataset.avif;
    im.src = a.href;
    pic.append(s, im);
    img.replaceChildren(pic);
    const fc = fig.querySelector('figcaption');
    cap.textContent = fc ? fc.textContent.trim() : (src ? src.alt : '');
    count.textContent = `${String(at + 1).padStart(2, '0')} / ${String(figs.length).padStart(2, '0')}`;
    setZoom(false);
    requestAnimationFrame(() => {
      const can = zoomable();
      img.classList.toggle('can-zoom', can);
      if (zoomBtn) zoomBtn.hidden = !can;
      // phones open landscape plates at reading size: a 2000px screen shrunk to 360px is unreadable
      if (can && (coarse.matches || innerWidth < 600) && im.width > im.height) setZoom(true);
    });
  };
  const open = (i, from) => {
    trigger = from;
    if (!box.open) box.showModal();
    show(i);
  };
  figs.forEach((fig, i) => {
    const a = fig.querySelector('a[data-avif]');
    a.addEventListener('click', (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button) return;
      e.preventDefault();
      open(i, a);
    });
  });
  // a repeated figure opens its first occurrence
  for (const a of $$('[data-lightbox] a[data-avif]')) {
    if (figs.some((f) => f.contains(a))) continue;
    const i = figs.findIndex((f) => f.querySelector('a[data-avif]').href === a.href);
    a.addEventListener('click', (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button || i < 0) return;
      e.preventDefault();
      open(i, a);
    });
  }
  box.querySelector('.lightbox__prev').addEventListener('click', () => show(at - 1));
  box.querySelector('.lightbox__next').addEventListener('click', () => show(at + 1));
  box.querySelector('.lightbox__close').addEventListener('click', () => box.close());
  if (zoomBtn) zoomBtn.addEventListener('click', () => setZoom(!('zoom' in box.dataset)));
  img.addEventListener('dblclick', (e) => {
    if (!e.target.closest('img') || !zoomable()) return;
    e.preventDefault();
    setZoom(!('zoom' in box.dataset));
  });
  box.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' && !('zoom' in box.dataset)) { e.preventDefault(); show(at - 1); }
    else if (e.key === 'ArrowRight' && !('zoom' in box.dataset)) { e.preventDefault(); show(at + 1); }
    else if ((e.key === '+' || e.key === '=') && zoomable()) setZoom(true);
    else if (e.key === '-') setZoom(false);
  });
  // drag to pan with a mouse (touch pans natively)
  let pan = null;
  img.addEventListener('pointerdown', (e) => {
    if (!('zoom' in box.dataset) || e.pointerType !== 'mouse') return;
    pan = { x: e.clientX, y: e.clientY, l: img.scrollLeft, t: img.scrollTop, moved: false };
    img.setPointerCapture(e.pointerId);
  });
  img.addEventListener('pointermove', (e) => {
    if (!pan) return;
    const dx = e.clientX - pan.x;
    const dy = e.clientY - pan.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) pan.moved = true;
    img.scrollLeft = pan.l - dx;
    img.scrollTop = pan.t - dy;
  });
  const endPan = () => { pan = null; };
  img.addEventListener('pointerup', endPan);
  img.addEventListener('pointercancel', endPan);
  // Light dismiss: a click on the empty sheet around the picture closes it.
  box.addEventListener('click', (e) => {
    if ('zoom' in box.dataset) return;
    if (e.target === box || e.target === img || e.target.classList.contains('lightbox__fig')) box.close();
  });
  box.addEventListener('close', () => {
    setZoom(false);
    img.replaceChildren();
    if (trigger && trigger.isConnected) trigger.focus({ preventScroll: true });
    trigger = null;
  });
}

// ---------- key-screens reel ----------
for (const reel of $$('.reel')) {
  const track = reel.querySelector('.reel__track');
  const items = $$('.reel__item', reel);
  const sec = reel.closest('section') || doc;
  const prev = sec.querySelector('.reel__prev');
  const next = sec.querySelector('.reel__next');
  const cur = sec.querySelector('.reel__cur');
  if (!track || !items.length || !prev || !next) continue;
  let at = 0;
  const seen = new Map();
  const paint = () => {
    if (cur) cur.textContent = String(at + 1).padStart(2, '0');
    prev.setAttribute('aria-disabled', String(track.scrollLeft <= 2 && at === 0));
    next.setAttribute('aria-disabled', String(at >= items.length - 1));
  };
  const go = (i) => {
    const j = Math.max(0, Math.min(items.length - 1, i));
    const pad = parseFloat(getComputedStyle(track).scrollPaddingInlineStart) || 0;
    track.scrollTo({ left: items[j].offsetLeft - track.offsetLeft - pad, behavior: motion() ? 'smooth' : 'auto' });
    at = j;
    paint();
  };
  const io = new IntersectionObserver((entries) => {
    for (const en of entries) seen.set(en.target, en.intersectionRatio);
    let best = at;
    let max = 0;
    items.forEach((it, i) => { const r = seen.get(it) || 0; if (r > max + 0.01) { max = r; best = i; } });
    if (max > 0) { at = best; paint(); }
  }, { root: track, threshold: [0, 0.25, 0.5, 0.75, 1] });
  items.forEach((it) => io.observe(it));
  prev.addEventListener('click', () => go(at - 1));
  next.addEventListener('click', () => go(at + 1));
  // a Tab into a half-hidden screen brings the whole screen into view
  reel.addEventListener('focusin', (e) => {
    const i = items.indexOf(e.target.closest('.reel__item'));
    if (i >= 0 && i !== at) go(i);
  });
  reel.addEventListener('keydown', (e) => {
    if (e.target.closest('a,button') && e.target !== reel) return;
    if (e.key === 'ArrowLeft') { e.preventDefault(); go(at - 1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); go(at + 1); }
  });
  reel.classList.add('is-ready');
  paint();
}

// ---------- title block: sheet data collapses below the rail layout ----------
const data = doc.querySelector('.cs-strip__data');
if (data) {
  const wide = mq('(min-width:1280px)');
  const fit = () => { data.open = wide.matches; };
  fit();
  wide.addEventListener('change', fit);
  // the rail has no summary to reopen it, so it never closes there
  data.addEventListener('toggle', () => { if (wide.matches && !data.open) data.open = true; });
}

// ---------- "Method" links open the note they point at ----------
const openNote = (hash) => {
  const el = hash && hash.length > 1 ? doc.getElementById(decodeURIComponent(hash.slice(1))) : null;
  if (!el || el.tagName !== 'DETAILS') return;
  el.open = true;
  el.classList.add('is-hl');
  setTimeout(() => el.classList.remove('is-hl'), 1600);
};
doc.addEventListener('click', (e) => {
  const a = e.target.closest('a[href^="#detail-"]');
  if (a) openNote(a.hash);
});
addEventListener('hashchange', () => openNote(location.hash));
if (location.hash.startsWith('#detail-')) openNote(location.hash);

// ---------- [ and ] page through the set ----------
const strip = doc.querySelector('.cs-strip[data-next]');
if (strip) {
  addEventListener('keydown', (e) => {
    if (html.dataset.keys === 'off' || e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented) return;
    if (e.key !== '[' && e.key !== ']') return;
    const t = e.target;
    if (t.closest && t.closest('input,textarea,select,[contenteditable=""],[contenteditable=true],dialog[open]')) return;
    const href = e.key === ']' ? strip.dataset.next : strip.dataset.prev;
    if (!href) return;
    e.preventDefault();
    location.href = new URL(href, location.href).href;
  });
}

// ---------- next sheets as view-transition sources ----------
addEventListener('pageswap', (e) => {
  const vt = e.viewTransition;
  const url = e.activation && e.activation.entry && e.activation.entry.url;
  if (!vt || !url || !motion()) return;
  const card = $$('.cs-nextcard__a').find((a) => a.href === url);
  if (!card) return;
  for (const el of $$('.case-title, .cs-plate--hero')) el.style.viewTransitionName = 'none';
  const cover = card.querySelector('.cs-nextcard__cover');
  const title = card.querySelector('.cs-nextcard__t');
  if (cover) cover.style.viewTransitionName = 'sheet';
  if (title) title.style.viewTransitionName = 'sheet-title';
});

// ---------- keynote dock: mark the band under the 40% line (position-based, so a jump that skips
// bands still marks the right one, and nothing is marked above or below the bands) ----------
const keys = new Map($$('.cs-strip__keys a').map((a) => [a.hash.slice(1), a]));
const bands = [...keys.keys()].map((id) => doc.getElementById(id)).filter(Boolean);
if (bands.length) {
  let cur = null, rq = 0;
  const spy = () => {
    rq = 0;
    const line = innerHeight * 0.4;
    let on = null;
    for (const b of bands) { if (b.getBoundingClientRect().top <= line) on = b; else break; }
    if (on && on.getBoundingClientRect().bottom < line) on = null; // read past the last band
    if (on === cur) return;
    if (cur) keys.get(cur.id).removeAttribute('aria-current');
    if (on) keys.get(on.id).setAttribute('aria-current', 'location');
    cur = on;
  };
  const ask = () => { if (!rq) rq = requestAnimationFrame(spy); };
  addEventListener('scroll', ask, { passive: true });
  addEventListener('resize', ask, { passive: true });
  spy();
}
