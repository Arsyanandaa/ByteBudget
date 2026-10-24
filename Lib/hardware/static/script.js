/* =========================================================================
   ByteBudget · script.js
   Semua interaksi dan animasi halaman.
   Dimuat di template dengan:
   <script src="{% static 'script.js' %}" defer></script>
   ========================================================================= */

(() => {
  'use strict';

  // =====================================================================
  // KONFIGURASI & HELPER
  // =====================================================================

  const root = document.documentElement;
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const fancy = finePointer && !reduceMotion; // efek berbasis mouse hanya di desktop

  const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';
  const EASE_IN_OUT = 'cubic-bezier(0.76, 0, 0.24, 1)';
  const NAV_OFFSET = 72;
  const LENIS_SRC = 'https://unpkg.com/lenis@1.1.13/dist/lenis.min.js';

  const numberFmt = new Intl.NumberFormat('id-ID');
  const formatRupiah = (n) => `Rp ${numberFmt.format(n)}`;

  const storage = {
    get(store, key) {
      try { return window[store].getItem(key); } catch { return null; }
    },
    set(store, key, value) {
      try { window[store].setItem(key, value); } catch { /* mode privat, abaikan */ }
    },
  };

  // State yang dipakai bersama oleh loop animasi
  const state = {
    lenis: null,
    mouseX: window.innerWidth / 2,
    mouseY: window.innerHeight / 2,
    cursor: null,
  };

  /**
   * Animasi angka dari `from` ke `to`.
   * @returns {Function} fungsi untuk menghentikan animasi
   */
  function animateNumber(to, from, duration, onUpdate) {
    const start = performance.now();
    let raf;
    const step = (now) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - (1 - p) ** 3;
      onUpdate(p === 1 ? to : Math.round((from + (to - from) * eased) / 1000) * 1000);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }

  /** Scroll halus ke elemen (atau ke atas jika target null) */
  function scrollToTarget(target) {
    const y = target ? target.getBoundingClientRect().top + window.scrollY - NAV_OFFSET : 0;
    if (state.lenis) {
      state.lenis.scrollTo(y, { duration: 1.4, easing: (t) => 1 - (1 - t) ** 4 });
    } else {
      window.scrollTo({ top: y, behavior: reduceMotion ? 'auto' : 'smooth' });
    }
  }

  // =====================================================================
  // STYLE TAMBAHAN (untuk elemen yang dibuat lewat JS)
  // =====================================================================

  function injectStyles() {
    const css = `
      ::view-transition-old(root), ::view-transition-new(root) { animation: none; mix-blend-mode: normal; }

      html.lenis, html.lenis body { height: auto; }
      .lenis.lenis-smooth { scroll-behavior: auto !important; }
      .lenis.lenis-stopped { overflow: hidden; }

      .nav-pill {
        position: absolute; top: 50%; left: 0; z-index: 0;
        height: 34px; width: 0; border-radius: 999px;
        background: rgb(var(--fg) / .07);
        transform: translateY(-50%);
        opacity: 0; pointer-events: none;
        transition: left .55s ${EASE}, width .55s ${EASE}, opacity .3s;
      }
      .navlink.is-active { color: rgb(var(--fg)); }

      #pageCurtain {
        position: fixed; inset: 0; z-index: 94;
        display: flex; flex-direction: column; justify-content: flex-end;
        padding: clamp(1.25rem, 4vw, 3rem);
        background: rgb(var(--fg)); color: rgb(var(--base));
        transform: translateY(101%);
        transition: transform .75s ${EASE_IN_OUT};
        pointer-events: none;
      }
      #pageCurtain.show { transform: none; pointer-events: auto; }
      #pageCurtain .pc-label { overflow: hidden; font-size: clamp(2rem, 6vw, 4.5rem); font-weight: 600; letter-spacing: -.05em; line-height: 1.05; }
      #pageCurtain .pc-label span { display: inline-block; transform: translateY(110%); transition: transform .8s ${EASE} .35s; }
      #pageCurtain.show .pc-label span { transform: none; }
      #pageCurtain .pc-bar { position: absolute; left: 0; right: 0; bottom: 0; height: 2px; overflow: hidden; }
      #pageCurtain .pc-bar::after {
        content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 40%;
        background: currentColor;
        animation: pcBar 1.1s ${EASE_IN_OUT} infinite;
      }
      @keyframes pcBar { from { transform: translateX(-100%); } to { transform: translateX(260%); } }

      .split-word { display: inline-block; white-space: nowrap; }
      .split-char { display: inline-block; }

      .form-error {
        display: flex; align-items: center; gap: .6rem;
        margin-top: 2rem;
        font-size: .92rem; font-weight: 500;
        color: rgb(var(--fg));
      }
      .form-error::before {
        content: "!"; display: grid; place-items: center; flex-shrink: 0;
        width: 20px; height: 20px; border-radius: 50%;
        background: rgb(var(--fg)); color: rgb(var(--base));
        font-size: .75rem; font-weight: 700;
      }
    `;
    const style = document.createElement('style');
    style.id = 'bb-script-styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  // =====================================================================
  // TIRAI TRANSISI HALAMAN
  // =====================================================================

  const curtain = (() => {
    let el = null;
    const ensure = () => {
      if (el) return el;
      el = document.createElement('div');
      el.id = 'pageCurtain';
      el.setAttribute('aria-hidden', 'true');
      el.innerHTML = '<p class="pc-label"><span></span></p><span class="pc-bar"></span>';
      document.body.appendChild(el);
      return el;
    };
    return {
      show(label) {
        const c = ensure();
        c.querySelector('.pc-label span').textContent = label;
        void c.offsetWidth; // paksa reflow agar transisi berjalan
        c.classList.add('show');
      },
      hide() {
        el?.classList.remove('show');
      },
    };
  })();

  // =====================================================================
  // TEMA GELAP/TERANG (dengan transisi lingkaran)
  // =====================================================================

  function initTheme() {
    const toggles = $$('#themeToggle, #darkModeToggle, #mobileDarkModeToggle');
    const iconPairs = [
      [$('#sunIcon'), $('#moonIcon')],
      [$('#mobileSunIcon'), $('#mobileMoonIcon')],
    ];

    const sync = () => {
      const dark = root.classList.contains('dark');
      iconPairs.forEach(([sun, moon]) => {
        if (!sun || !moon) return;
        sun.classList.toggle('hidden', !dark);
        moon.classList.toggle('hidden', dark);
      });
      toggles.forEach((t) => t.setAttribute('aria-label', dark ? 'Pakai tema terang' : 'Pakai tema gelap'));
    };

    const apply = () => {
      const dark = root.classList.toggle('dark');
      storage.set('localStorage', 'theme', dark ? 'dark' : 'light');
      sync();
    };

    const toggle = (event) => {
      if (!document.startViewTransition || reduceMotion) { apply(); return; }

      // Titik pusat lingkaran: posisi klik, atau tengah tombol (keyboard)
      const btn = event?.currentTarget;
      const rect = btn?.getBoundingClientRect();
      const x = event?.clientX || (rect ? rect.left + rect.width / 2 : window.innerWidth / 2);
      const y = event?.clientY || (rect ? rect.top + rect.height / 2 : 0);
      const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));

      const transition = document.startViewTransition(apply);
      transition.ready.then(() => {
        root.animate(
          { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
          { duration: 750, easing: EASE_IN_OUT, pseudoElement: '::view-transition-new(root)' }
        );
      }).catch(() => {});
    };

    sync();
    toggles.forEach((t) => t.addEventListener('click', toggle));

    // Ikuti tema sistem selama user belum memilih sendiri
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', (e) => {
      if (storage.get('localStorage', 'theme')) return;
      root.classList.toggle('dark', e.matches);
      sync();
    });

    window.toggleDarkMode = () => toggle();
  }

  // =====================================================================
  // MENU MOBILE
  // =====================================================================

  function initMobileMenu() {
    const btn = $('#mobileMenuBtn');
    const menu = $('#mobileMenu');
    const nav = $('#nav');
    if (!btn || !menu) return null;

    const modern = menu.classList.contains('mmenu');
    const isOpen = () => (modern ? menu.classList.contains('open') : !menu.classList.contains('hidden'));
    const set = (open) => {
      if (modern) menu.classList.toggle('open', open);
      else menu.classList.toggle('hidden', !open);
      btn.classList.toggle('open', open);
      nav?.classList.toggle('menu-open', open);
      btn.setAttribute('aria-expanded', String(open));
      btn.setAttribute('aria-label', open ? 'Tutup menu' : 'Buka menu');
    };

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      set(!isOpen());
    });
    $$('a', menu).forEach((a, i) => {
      a.style.setProperty('--i', i);
      a.addEventListener('click', () => set(false));
    });
    document.addEventListener('click', (e) => {
      if (isOpen() && !menu.contains(e.target) && !btn.contains(e.target)) set(false);
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && isOpen()) { set(false); btn.focus(); }
    });

    // Menu kategori (halaman lama)
    const catBtn = $('#mobileCategoryBtn');
    const catMenu = $('#mobileCategoryMenu');
    catBtn?.addEventListener('click', () => {
      catMenu?.classList.toggle('hidden');
      $('#mobileCategoryIcon')?.classList.toggle('rotate-180');
    });

    return { isOpen, set };
  }

  // =====================================================================
  // NAVBAR: penanda section aktif yang bergeser
  // =====================================================================

  function initNavPill() {
    const navEl = $('#nav nav');
    if (!navEl) return null;
    const links = $$('.navlink', navEl).filter((a) => a.hash && document.getElementById(a.hash.slice(1)));
    if (!links.length) return null;

    navEl.style.position = 'relative';
    const pill = document.createElement('span');
    pill.className = 'nav-pill';
    pill.setAttribute('aria-hidden', 'true');
    navEl.prepend(pill);

    const sections = links.map((link) => ({ link, el: document.getElementById(link.hash.slice(1)) }));
    let current = null;

    const moveTo = (link) => {
      if (!link) { pill.style.opacity = '0'; return; }
      pill.style.left = `${link.offsetLeft}px`;
      pill.style.width = `${link.offsetWidth}px`;
      pill.style.opacity = '1';
    };

    links.forEach((a) => a.addEventListener('mouseenter', () => moveTo(a)));
    navEl.addEventListener('mouseleave', () => moveTo(current));
    window.addEventListener('resize', () => moveTo(current));

    // Dipanggil dari loop animasi
    return () => {
      const line = window.innerHeight * 0.35;
      let active = null;
      sections.forEach(({ link, el }) => {
        const r = el.getBoundingClientRect();
        if (r.top <= line && r.bottom > line) active = link;
      });
      if (active === current) return;
      current?.classList.remove('is-active');
      current?.removeAttribute('aria-current');
      current = active;
      current?.classList.add('is-active');
      current?.setAttribute('aria-current', 'true');
      if (!navEl.matches(':hover')) moveTo(current);
    };
  }

  // =====================================================================
  // INTRO LOADER & REVEAL SAAT SCROLL
  // =====================================================================

  function runCounters(scope) {
    $$('[data-count]', scope).forEach((el) => {
      const target = parseInt(el.dataset.count, 10);
      if (reduceMotion) { el.textContent = numberFmt.format(target); return; }
      el.textContent = '0';
      setTimeout(() => animateNumber(target, 0, 1500, (v) => { el.textContent = numberFmt.format(v); }), 850);
    });
  }

  function initIntroAndReveals() {
    const targets = [...$$('[data-rv]'), ...$$('.fade-in-on-scroll')];

    const reveal = (el) => {
      el.classList.add(el.hasAttribute('data-rv') ? 'in' : 'visible');
      if (el.hasAttribute('data-count-root')) runCounters(el);
    };

    const startReveals = () => {
      if (reduceMotion || !('IntersectionObserver' in window)) { targets.forEach(reveal); return; }
      const io = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          reveal(entry.target);
          io.unobserve(entry.target);
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
      targets.forEach((el) => io.observe(el));
    };

    const loader = $('#loader');
    if (!loader || !root.classList.contains('intro')) {
      loader?.remove();
      root.classList.remove('intro', 'lock');
      startReveals();
      return;
    }

    const count = $('#lcount', loader);
    let t0 = null;
    const tick = (t) => {
      t0 ??= t;
      const p = Math.min((t - t0) / 1300, 1);
      const eased = 1 - (1 - p) ** 2;
      if (count) count.textContent = Math.round(eased * 100);
      loader.style.setProperty('--p', eased);
      if (p < 1) { requestAnimationFrame(tick); return; }

      setTimeout(() => {
        loader.classList.add('done');
        root.classList.remove('lock');
        state.lenis?.start();
        storage.set('sessionStorage', 'bb-intro', '1');
        setTimeout(startReveals, 380);
        setTimeout(() => { loader.remove(); root.classList.remove('intro'); }, 1150);
      }, 200);
    };
    requestAnimationFrame(tick);
  }

  // =====================================================================
  // TICKER & STAGGER
  // =====================================================================

  function initTicker() {
    // Gandakan isi supaya bisa berputar tanpa celah
    $$('.ticker').forEach((ticker) => {
      const original = Array.from(ticker.children);
      for (let n = 0; n < 3; n++) {
        original.forEach((el) => {
          const clone = el.cloneNode(true);
          clone.setAttribute('aria-hidden', 'true');
          ticker.appendChild(clone);
        });
      }
    });
  }

  function initStagger() {
    $$('[data-stagger]').forEach((parent) => {
      Array.from(parent.children).forEach((child, i) => {
        if (!child.style.getPropertyValue('--i')) child.style.setProperty('--i', i % 8);
      });
    });
  }

  // =====================================================================
  // INPUT BUDGET: preview rupiah beranimasi + chip pilihan cepat
  // =====================================================================

  function initBudgetFields() {
    const update = (input, animate = false) => {
      const out = document.getElementById(input.dataset.preview);
      const value = parseInt(input.value, 10);
      const min = parseInt(input.min, 10);

      if (out) {
        out._stop?.();
        out.classList.remove('hint-warn');
        if (!value || value <= 0) {
          out.textContent = '';
          out._val = 0;
        } else if (min && value < min) {
          out.textContent = `Minimal ${formatRupiah(min)}`;
          out.classList.add('hint-warn');
          out._val = 0;
        } else if (animate && !reduceMotion) {
          out._stop = animateNumber(value, out._val || 0, 650, (n) => { out.textContent = formatRupiah(n); });
          out._val = value;
        } else {
          out.textContent = formatRupiah(value);
          out._val = value;
        }
      }

      $$(`[data-budget-for="${input.id}"]`).forEach((chip) => {
        const on = parseInt(chip.dataset.value, 10) === value;
        chip.classList.toggle('is-active', on);
        chip.setAttribute('aria-pressed', String(on));
      });
    };

    const setBudget = (id, value) => {
      const input = document.getElementById(id);
      if (!input) return;
      input.value = value;
      update(input, true);
      input.dispatchEvent(new Event('change', { bubbles: true }));
      if (!reduceMotion) {
        input.animate(
          [{ transform: 'translateY(16px)', opacity: 0, filter: 'blur(4px)' }, { transform: 'none', opacity: 1, filter: 'blur(0)' }],
          { duration: 550, easing: EASE }
        );
      }
    };

    $$('[data-preview]').forEach((input) => {
      input.addEventListener('input', () => update(input));
      update(input);
    });

    $$('[data-budget-for]').forEach((chip) => {
      chip.addEventListener('click', () => {
        setBudget(chip.dataset.budgetFor, chip.dataset.value);
        if (!reduceMotion) {
          chip.animate([{ transform: 'scale(.9)' }, { transform: 'scale(1)' }], { duration: 400, easing: EASE });
        }
      });
    });

    // Tetap tersedia untuk kode lama
    window.setBudgetPC = (n) => setBudget('budgetPC', n);
  }

  // =====================================================================
  // FORM: pesan error + guncangan, status loading, tirai saat dikirim
  // =====================================================================

  function validationMessage(field) {
    const v = field.validity;
    if (field.type === 'radio') return 'Pilih salah satu kebutuhan dulu.';
    if (field.name === 'budget') {
      if (v.valueMissing) return 'Isi budget dulu, contohnya 10000000.';
      if (v.rangeUnderflow) return `Budget minimal ${formatRupiah(Number(field.min))}.`;
      if (v.stepMismatch) return 'Budget harus kelipatan Rp 100.000.';
      if (v.badInput) return 'Budget hanya boleh berisi angka.';
    }
    return field.validationMessage || 'Periksa lagi isian form.';
  }

  function initForms() {
    $$('form[data-busy]').forEach((form) => {
      const submitBtn = $('[type="submit"]', form);
      if (submitBtn) submitBtn.dataset.original = submitBtn.innerHTML;

      let errorEl = null;
      let handlingInvalid = false;

      const showError = (message) => {
        if (!errorEl) {
          errorEl = document.createElement('p');
          errorEl.className = 'form-error';
          errorEl.setAttribute('role', 'alert');
          if (submitBtn) submitBtn.before(errorEl);
          else form.append(errorEl);
        }
        errorEl.textContent = message;
        if (!reduceMotion) {
          errorEl.animate([{ opacity: 0, transform: 'translateY(-8px)' }, { opacity: 1, transform: 'none' }], { duration: 400, easing: EASE });
        }
      };
      const hideError = () => {
        errorEl?.remove();
        errorEl = null;
      };

      // "invalid" tidak bubble, jadi ditangkap di fase capture
      form.addEventListener('invalid', (e) => {
        if (handlingInvalid) return; // cukup tangani field pertama yang salah
        handlingInvalid = true;
        setTimeout(() => { handlingInvalid = false; }, 500);

        showError(validationMessage(e.target));
        const box = e.target.closest('fieldset') || form;
        if (!reduceMotion) {
          box.animate(
            [
              { transform: 'translateX(0)' },
              { transform: 'translateX(-10px)' },
              { transform: 'translateX(9px)' },
              { transform: 'translateX(-6px)' },
              { transform: 'translateX(3px)' },
              { transform: 'translateX(0)' },
            ],
            { duration: 480, easing: 'ease-out' }
          );
        }
      }, true);

      form.addEventListener('input', hideError);
      form.addEventListener('change', hideError);

      form.addEventListener('submit', () => {
        hideError();
        const label = submitBtn?.dataset.busyText || 'Memuat…';
        if (submitBtn) {
          submitBtn.classList.add('is-busy');
          submitBtn.setAttribute('aria-busy', 'true');
          submitBtn.innerHTML = `<span class="spinner" aria-hidden="true"></span>${label}`;
        }
        if (!reduceMotion) curtain.show(label);
      });
    });
  }

  /** Kembalikan tombol & tirai saat user menekan Back */
  function resetAfterBack() {
    curtain.hide();
    $$('form[data-busy] [data-original]').forEach((btn) => {
      btn.classList.remove('is-busy');
      btn.removeAttribute('aria-busy');
      btn.innerHTML = btn.dataset.original;
    });
  }

  // =====================================================================
  // LINK: scroll halus ke section & transisi antar halaman
  // =====================================================================

  function initAnchors() {
    document.addEventListener('click', (e) => {
      if (e.defaultPrevented || e.button !== 0) return;
      const a = e.target.closest('a[href*="#"]');
      if (!a) return;
      const url = new URL(a.href, window.location.href);
      if (url.pathname !== window.location.pathname || url.search !== window.location.search || !url.hash) return;

      const id = decodeURIComponent(url.hash.slice(1));
      const target = id === 'top' ? null : document.getElementById(id);
      if (id !== 'top' && !target) return;

      e.preventDefault();
      scrollToTarget(target);
      history.pushState(null, '', url.hash);
      if (target) {
        if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
        target.focus({ preventScroll: true });
      }
    });
  }

  function initPageTransitions() {
    if (reduceMotion) return;
    document.addEventListener('click', (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target.closest('a[href]');
      if (!a || a.hasAttribute('download') || (a.target && a.target !== '_self')) return;

      const url = new URL(a.href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;

      e.preventDefault();
      curtain.show('Memuat halaman…');
      setTimeout(() => { window.location.href = url.href; }, 650);
    });
  }

  // =====================================================================
  // EFEK MOUSE (desktop saja)
  // =====================================================================

  function initCursor() {
    if (!fancy) return;
    const dot = document.createElement('div');
    const ring = document.createElement('div');
    dot.className = 'cursor-dot';
    ring.className = 'cursor';
    [dot, ring].forEach((el) => {
      el.style.opacity = '0';
      document.body.appendChild(el);
    });
    root.classList.add('has-cursor');
    state.cursor = { ring, x: state.mouseX, y: state.mouseY };

    let shown = false;
    window.addEventListener('mousemove', (e) => {
      state.mouseX = e.clientX;
      state.mouseY = e.clientY;
      if (!shown) {
        state.cursor.x = e.clientX;
        state.cursor.y = e.clientY;
        dot.style.opacity = ring.style.opacity = '1';
        shown = true;
      }
      dot.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0)`;
    }, { passive: true });

    document.addEventListener('mouseover', (e) => {
      ring.classList.toggle('is-hover', !!e.target.closest('a, button, label.opt, [data-cursor]'));
    });
    document.addEventListener('mousedown', () => ring.classList.add('is-down'));
    document.addEventListener('mouseup', () => ring.classList.remove('is-down'));
    document.addEventListener('mouseleave', () => {
      dot.style.opacity = ring.style.opacity = '0';
      shown = false;
    });
  }

  function initMagnetAndRipple() {
    if (fancy) {
      $$('.btn, .iconbtn, #toTop').forEach((el) => {
        el.addEventListener('mousemove', (e) => {
          const r = el.getBoundingClientRect();
          const x = clamp((e.clientX - r.left - r.width / 2) * 0.3, -14, 14);
          const y = clamp((e.clientY - r.top - r.height / 2) * 0.4, -10, 10);
          el.classList.add('magnet');
          el.style.transform = `translate(${x}px, ${y}px)`;
        });
        el.addEventListener('mouseleave', () => {
          el.classList.remove('magnet');
          el.style.transform = '';
        });
      });
    }

    if (reduceMotion) return;
    $$('.btn').forEach((btn) => {
      btn.addEventListener('pointerdown', (e) => {
        const r = btn.getBoundingClientRect();
        const size = Math.max(r.width, r.height) * 2.2;
        const ripple = document.createElement('span');
        ripple.className = 'ripple';
        ripple.style.width = ripple.style.height = `${size}px`;
        ripple.style.left = `${e.clientX - r.left - size / 2}px`;
        ripple.style.top = `${e.clientY - r.top - size / 2}px`;
        btn.appendChild(ripple);
        setTimeout(() => ripple.remove(), 760);
      });
    });
  }

  function initScramble() {
    if (reduceMotion) return;
    const glyphs = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&';
    $$('[data-scramble]').forEach((el) => {
      const final = el.textContent;
      const host = el.closest('a') || el;
      host.addEventListener('mouseenter', () => {
        let frame = 0;
        const total = final.length * 3;
        cancelAnimationFrame(el._raf);
        const step = () => {
          el.textContent = Array.from(final, (ch, i) => (i < frame / 3 ? ch : glyphs[Math.floor(Math.random() * glyphs.length)])).join('');
          frame++;
          if (frame <= total) el._raf = requestAnimationFrame(step);
          else el.textContent = final;
        };
        step();
      });
    });
  }

  function initHeroGrid() {
    const grid = $('.hero-grid');
    const hero = grid?.parentElement;
    if (!hero || !grid || !fancy) return;
    hero.addEventListener('mousemove', (e) => {
      const r = hero.getBoundingClientRect();
      grid.style.setProperty('--mx', `${e.clientX - r.left}px`);
      grid.style.setProperty('--my', `${e.clientY - r.top}px`);
    });
  }

  function initTilt() {
    if (!fancy) return;
    $$('[data-tilt]').forEach((card) => {
      card.addEventListener('mousemove', (e) => {
        const r = card.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width - 0.5;
        const py = (e.clientY - r.top) / r.height - 0.5;
        card.classList.add('tilting');
        card.style.transform = `perspective(1100px) rotateX(${-py * 8}deg) rotateY(${px * 10}deg) scale(1.015)`;
      });
      card.addEventListener('mouseleave', () => {
        card.classList.remove('tilting');
        card.style.transform = '';
      });
    });
  }

  function initSpotlight() {
    if (!fancy) return;
    $$('[data-spot]').forEach((el) => {
      el.addEventListener('mousemove', (e) => {
        const r = el.getBoundingClientRect();
        el.style.setProperty('--sx', `${e.clientX - r.left}px`);
        el.style.setProperty('--sy', `${e.clientY - r.top}px`);
      });
    });
  }

  /** Judul: gelombang huruf saat di-hover */
  function initHeadingWave() {
    if (!fancy) return;
    $$('.h1, .h2').forEach((heading) => {
      if (heading.closest('[aria-hidden="true"]')) return;
      const label = heading.textContent.replace(/\s+/g, ' ').trim();
      const chars = [];

      $$('.mask > span', heading).forEach((line) => {
        const words = line.textContent.trim().split(' ');
        line.textContent = '';
        words.forEach((word, wi) => {
          const wordEl = document.createElement('span');
          wordEl.className = 'split-word';
          Array.from(word).forEach((ch) => {
            const c = document.createElement('span');
            c.className = 'split-char';
            c.textContent = ch;
            wordEl.appendChild(c);
            chars.push(c);
          });
          line.appendChild(wordEl);
          if (wi < words.length - 1) line.appendChild(document.createTextNode(' '));
        });
      });
      if (!chars.length) return;

      heading.setAttribute('aria-label', label);
      let busy = false;
      heading.addEventListener('mouseenter', () => {
        if (busy) return;
        busy = true;
        chars.forEach((c, i) => {
          c.animate(
            [
              { opacity: 1, transform: 'translateY(0)' },
              { opacity: 0.18, transform: 'translateY(0.04em)', offset: 0.45 },
              { opacity: 1, transform: 'translateY(0)' },
            ],
            { duration: 650, delay: i * 16, easing: EASE }
          );
        });
        setTimeout(() => { busy = false; }, chars.length * 16 + 650);
      });
    });
  }

  // =====================================================================
  // TEKS MENYALA PER KATA SAAT SCROLL
  // =====================================================================

  function initScrub() {
    return $$('[data-scrub]').map((box) => {
      const words = [];
      $$('p', box).forEach((p) => {
        const parts = p.textContent.trim().split(/\s+/);
        p.textContent = '';
        parts.forEach((word, i) => {
          const span = document.createElement('span');
          span.className = 'w';
          span.textContent = word;
          p.appendChild(span);
          if (i < parts.length - 1) p.appendChild(document.createTextNode(' '));
          words.push(span);
        });
      });
      return { box, words, lit: -1 };
    });
  }

  // =====================================================================
  // TOMBOL KEMBALI KE ATAS
  // =====================================================================

  function initToTop() {
    $('#toTop')?.addEventListener('click', () => scrollToTarget(null));
  }

  // =====================================================================
  // SMOOTH SCROLL (Lenis, dimuat hanya di desktop)
  // =====================================================================

  function initSmoothScroll() {
    if (!fancy) return;
    const script = document.createElement('script');
    script.src = LENIS_SRC;
    script.async = true;
    script.onload = () => {
      if (typeof window.Lenis !== 'function') return;
      root.style.scrollBehavior = 'auto';
      state.lenis = new window.Lenis({ lerp: 0.09 });
      if (root.classList.contains('lock')) state.lenis.stop();
      const raf = (time) => {
        state.lenis.raf(time);
        requestAnimationFrame(raf);
      };
      requestAnimationFrame(raf);
    };
    document.head.appendChild(script);
  }

  // =====================================================================
  // FAQ / AKORDEON
  // =====================================================================

  function initAccordion() {
    $$('[data-accordion]').forEach((acc) => {
      const items = $$('.acc-item', acc);
      items.forEach((item) => {
        const btn = $('.acc-btn', item);
        btn?.addEventListener('click', () => {
          const willOpen = !item.classList.contains('open');
          items.forEach((other) => {
            other.classList.remove('open');
            $('.acc-btn', other)?.setAttribute('aria-expanded', 'false');
          });
          if (willOpen) {
            item.classList.add('open');
            btn.setAttribute('aria-expanded', 'true');
          }
        });
      });
    });
  }

  // =====================================================================
  // KARTU PEMBAGIAN BUDGET (tab Gaming / Editing / Office)
  // =====================================================================

  function initAllocation() {
    $$('[data-alloc]').forEach((box) => {
      const buttons = $$('[data-set]', box);
      const rows = $$('.alloc-row', box);
      const pill = $('.seg-pill', box);
      const note = $('[data-alloc-note]', box);
      if (!buttons.length) return;

      const placePill = (btn) => {
        if (!pill) return;
        pill.style.left = `${btn.offsetLeft}px`;
        pill.style.width = `${btn.offsetWidth}px`;
      };

      const select = (btn, animate = true) => {
        buttons.forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
        placePill(btn);
        const set = btn.dataset.set;

        rows.forEach((row) => {
          const to = parseFloat(row.dataset[set] || '0');
          const out = $('.alloc-val', row);
          const from = parseFloat(out?.textContent) || 0;
          row.style.setProperty('--v', `${to}%`);
          if (!out) return;
          if (!animate || reduceMotion) { out.textContent = `${to}%`; return; }
          const start = performance.now();
          const step = (now) => {
            const p = Math.min((now - start) / 700, 1);
            const eased = 1 - (1 - p) ** 3;
            out.textContent = `${Math.round(from + (to - from) * eased)}%`;
            if (p < 1) requestAnimationFrame(step);
          };
          requestAnimationFrame(step);
        });

        if (note && btn.dataset.note) {
          note.textContent = btn.dataset.note;
          if (animate && !reduceMotion) {
            note.animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: 450, easing: EASE });
          }
        }
      };

      buttons.forEach((b) => b.addEventListener('click', () => select(b)));
      select(buttons[0], false);
      window.addEventListener('resize', () => {
        const active = buttons.find((b) => b.getAttribute('aria-pressed') === 'true');
        if (active) placePill(active);
      });
      document.fonts?.ready.then(() => placePill(buttons.find((b) => b.getAttribute('aria-pressed') === 'true') || buttons[0]));
    });
  }

  // =====================================================================
  // SECTION SCROLL HORIZONTAL (di-pin)
  // =====================================================================

  function initHPin() {
    const pins = $$('[data-hpin]').map((sec) => ({
      sec,
      track: $('.hpin-track', sec),
      bar: $('[data-hpin-bar]', sec),
      count: $('[data-hpin-count]', sec),
      cards: $$('.hpin-track > *', sec),
      dist: 0,
    })).filter((p) => p.track);
    if (!pins.length) return null;

    const enabled = () => window.innerWidth >= 768 && !reduceMotion;
    const measure = () => {
      pins.forEach((p) => {
        if (!enabled()) {
          p.sec.style.height = '';
          p.track.style.transform = '';
          p.cards.forEach((c) => { c.style.transform = ''; });
          p.dist = 0;
          return;
        }
        p.dist = Math.max(0, p.track.offsetWidth - window.innerWidth);
        p.sec.style.height = `${p.dist + window.innerHeight}px`;
      });
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('load', measure);
    document.fonts?.ready.then(measure);

    // Dipanggil dari loop animasi
    return () => {
      if (!enabled()) return;
      const vw = window.innerWidth;
      pins.forEach((p) => {
        const r = p.sec.getBoundingClientRect();
        if (r.bottom < 0 || r.top > window.innerHeight) return;
        const prog = p.dist ? clamp(-r.top / p.dist, 0, 1) : 0;
        p.track.style.transform = `translate3d(${(-prog * p.dist).toFixed(1)}px, 0, 0)`;
        if (p.bar) p.bar.style.transform = `scaleX(${prog.toFixed(3)})`;
        if (p.count) {
          const n = Math.min(p.cards.length, Math.floor(prog * p.cards.length) + 1);
          p.count.textContent = String(n).padStart(2, '0');
        }
        // Kartu di tengah layar sedikit lebih besar
        p.cards.forEach((c) => {
          const cr = c.getBoundingClientRect();
          const d = Math.min(Math.abs(cr.left + cr.width / 2 - vw / 2) / vw, 0.6);
          c.style.transform = `scale(${(1 - d * 0.14).toFixed(3)})`;
        });
      });
    };
  }

  // =====================================================================
  // TIMELINE LANGKAH (garis terisi saat scroll)
  // =====================================================================

  function initTimeline() {
    return $$('[data-timeline]').map((tl) => ({
      tl,
      fill: $('.tl-fill', tl),
      steps: $$('.tl-step', tl),
    }));
  }

  // =====================================================================
  // LOOP ANIMASI UTAMA (scroll & kursor)
  // =====================================================================

  function startLoop({ menu, updateNavPill, scrubs, updateHPin, timelines }) {
    const nav = $('#nav');
    const progress = $('#progress');
    const toTop = $('#toTop');
    const ring = toTop?.querySelector('.ring-fg');
    const parallaxEls = $$('[data-parallax]');
    const expandEls = $$('[data-expand]');
    const hscrollEls = $$('[data-hscroll]');
    const tickerWraps = $$('.ticker-wrap');
    const tickerAnims = $$('.ticker').flatMap((t) => (t.getAnimations ? t.getAnimations() : []));

    nav?.addEventListener('focusin', () => nav.classList.remove('nav-hidden'));

    let lastNavY = window.scrollY;
    let prevY = window.scrollY;
    let velocity = 0;
    let skew = 0;
    let rate = 1;

    const frame = () => {
      const y = window.scrollY;
      const vh = window.innerHeight;
      const vw = window.innerWidth;
      const max = document.documentElement.scrollHeight - vh;
      const progressRatio = max > 0 ? y / max : 0;

      // Kursor cincin mengikuti dengan lembut
      if (state.cursor) {
        const c = state.cursor;
        c.x += (state.mouseX - c.x) * 0.17;
        c.y += (state.mouseY - c.y) * 0.17;
        c.ring.style.transform = `translate3d(${c.x}px, ${c.y}px, 0)`;
      }

      // Navbar: latar saat discroll, sembunyi saat scroll turun
      if (nav) {
        nav.classList.toggle('scrolled', y > 8);
        if (!menu?.isOpen() && Math.abs(y - lastNavY) > 4) {
          nav.classList.toggle('nav-hidden', y > lastNavY && y > 240);
          lastNavY = y;
        }
      }
      updateNavPill?.();

      if (progress) progress.style.transform = `scaleX(${progressRatio})`;
      if (toTop) {
        toTop.classList.toggle('show', y > vh * 0.8);
        if (ring) ring.style.strokeDashoffset = (145 * (1 - progressRatio)).toFixed(1);
      }

      if (!reduceMotion) {
        // Kecepatan scroll -> ticker miring dan berputar lebih cepat
        velocity += (y - prevY - velocity) * 0.2;
        prevY = y;
        skew += (clamp(velocity * 0.25, -9, 9) - skew) * 0.12;
        tickerWraps.forEach((w) => { w.style.transform = `skewX(${(-skew).toFixed(2)}deg)`; });
        rate += (1 + Math.min(Math.abs(velocity) * 0.18, 7) - rate) * 0.1;
        tickerAnims.forEach((a) => { a.playbackRate = rate; });

        // Parallax + memudar di hero
        if (y < vh * 1.4) {
          const fade = clamp(1 - y / (vh * 0.9), 0, 1).toFixed(3);
          parallaxEls.forEach((el) => {
            el.style.transform = `translate3d(0, ${(y * parseFloat(el.dataset.parallax)).toFixed(1)}px, 0)`;
            el.style.opacity = fade;
          });
        }

        // Section hitam melebar saat masuk layar
        expandEls.forEach((el) => {
          const r = el.getBoundingClientRect();
          if (r.top > vh || r.bottom < 0) return;
          const p = clamp((vh - r.top) / (vh * 0.75), 0, 1);
          const side = (1 - p) * (vw < 640 ? 3 : 5);
          el.style.clipPath = `inset(0 ${side.toFixed(2)}% round ${((1 - p) * 40).toFixed(1)}px)`;
        });

        // Wordmark footer bergeser horizontal
        hscrollEls.forEach((el) => {
          const r = el.getBoundingClientRect();
          if (r.top > vh || r.bottom < 0) return;
          const p = clamp((vh - r.top) / (vh + r.height), 0, 1);
          el.style.transform = `translate3d(${((1 - p) * -18).toFixed(2)}%, 0, 0)`;
        });
      }

      // Scroll horizontal di-pin
      updateHPin?.();

      // Timeline: garis terisi & langkah aktif
      timelines.forEach((t) => {
        const r = t.tl.getBoundingClientRect();
        if (r.top > vh || r.bottom < 0) return;
        const p = clamp((vh * 0.6 - r.top) / r.height, 0, 1);
        if (t.fill) t.fill.style.transform = `scaleY(${p.toFixed(3)})`;
        t.steps.forEach((step) => {
          step.classList.toggle('active', reduceMotion || step.getBoundingClientRect().top < vh * 0.6);
        });
      });

      // Teks menyala per kata
      scrubs.forEach((s) => {
        const r = s.box.getBoundingClientRect();
        const p = reduceMotion ? 1 : clamp((vh * 0.88 - r.top) / (r.height + vh * 0.3), 0, 1);
        const lit = Math.round(p * s.words.length);
        if (lit === s.lit) return;
        s.words.forEach((w, i) => w.classList.toggle('on', i < lit));
        s.lit = lit;
      });

      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

  // =====================================================================
  // INISIALISASI
  // =====================================================================

  function init() {
    injectStyles();
    initTheme();
    const menu = initMobileMenu();
    const updateNavPill = initNavPill();

    initTicker();
    initStagger();
    initHeadingWave();
    const scrubs = initScrub();
    initIntroAndReveals();

    initBudgetFields();
    initForms();
    initAnchors();
    initPageTransitions();

    initCursor();
    initMagnetAndRipple();
    initScramble();
    initHeroGrid();
    initTilt();
    initSpotlight();
    initToTop();
    initAccordion();
    initAllocation();
    const updateHPin = initHPin();
    const timelines = initTimeline();
    initSmoothScroll();

    startLoop({ menu, updateNavPill, scrubs, updateHPin, timelines });
    window.addEventListener('pageshow', resetAfterBack);

    // Dipakai halaman lama
    window.scrollToSearch = () => scrollToTarget($('#search-section') || $('#pccomponentfinder'));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();