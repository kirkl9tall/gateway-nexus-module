/*
 * Dark mode toggle — swaps CSS variables + persists in localStorage.
 * Puts the toggle in the top bar (#theme-toggle-slot) when present,
 * otherwise falls back to a small fixed button bottom-left.
 */
(function() {
  'use strict';

  const KEY = 'jerumednexus-theme';
  const stored = localStorage.getItem(KEY);
  if (stored === 'dark' || (!stored && matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }

  const style = document.createElement('style');
  style.textContent = `
    /* Dark palette for the design tokens in base.html. Only the NEW names are
       set: the old names (--bg, --text, --accent…) are aliases of these in
       base.html, so every page follows. All text pairs are >= 4.5:1 (WCAG AA). */
    :root[data-theme="dark"] {
      color-scheme: dark;
      --page: #12161A; --surface: #1A2026; --bg3: #222A31;
      --ink: #E8ECEF; --ink-2: #C2CAD1; --ink-3: #9AA5AF; --line: #33404A;
      --brand: #8DBBE3; --brand-2: #A9CDEC; --brand-tint: #1F3346;
      --good: #5FD39A; --good-tint: #173326;
      --warn: #F2C14E; --warn-fill: #E9A820; --warn-tint: #3A2E12;
      --crit: #FF9A8F; --crit-tint: #3D1E1B;
      --neutral: #AEB8C1; --neutral-tint: #262E35;
    }
    :root[data-theme="dark"] .btn-primary, :root[data-theme="dark"] .btn-success { color: #0E1A24; }
    :root[data-theme="dark"] .btn-primary:hover, :root[data-theme="dark"] .btn-success:hover { color: #0E1A24; }
    :root[data-theme="dark"] .nav-link.active { color: #CFE3F5; }
    :root[data-theme="dark"] .brand img { filter: brightness(1.8) saturate(0.8); }
    :root[data-theme="dark"] .ov-bar .b { background: #4A6A88; }
    :root[data-theme="dark"] .ov-bar.today .b { background: var(--brand); }
    :root[data-theme="dark"] .ov-ring .track { stroke: #2C3640; }
    :root[data-theme="dark"] .mc-icon { background: #262E35; }
    :root[data-theme="dark"] .ov-link i { background: #12161A; }
    :root[data-theme="dark"] .chip.good svg path, :root[data-theme="dark"] .ov-dest-mini .good svg path,
    :root[data-theme="dark"] .ck li.good svg path { stroke: #12161A; }
    :root[data-theme="dark"] #toast { background: var(--ink) !important; color: var(--page) !important; }
    :root[data-theme="dark"] input, :root[data-theme="dark"] select, :root[data-theme="dark"] textarea {
      background: var(--bg3); color: var(--ink); border-color: var(--line);
    }
    :root[data-theme="dark"] table td, :root[data-theme="dark"] table th { color: var(--ink); border-color: var(--line); }
    #theme-toggle {
      width: 44px; height: 44px; border: 1px solid var(--line, #D5DCE1);
      background: var(--surface, #fff); color: var(--ink-2, #4B5763); cursor: pointer;
      display: flex; align-items: center; justify-content: center; border-radius: 10px;
    }
    #theme-toggle:hover { border-color: var(--accent, #4f7599); color: var(--accent, #4f7599); }
    #theme-toggle.floating {
      position: fixed; bottom: 16px; left: 16px; z-index: 9998; background: var(--bg, #f2f2f3);
    }
  `;
  document.head.appendChild(style);

  const MOON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>';
  const SUN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>';

  function mount() {
    const btn = document.createElement('button');
    btn.id = 'theme-toggle';
    btn.type = 'button';
    btn.title = (window.T ? T('Tema chiaro / scuro') : 'Tema chiaro / scuro');
    btn.setAttribute('aria-label', btn.title);
    const update = () => {
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      btn.innerHTML = isDark ? SUN : MOON;
    };
    btn.onclick = () => {
      const cur = document.documentElement.getAttribute('data-theme');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem(KEY, next);
      update();
      if (typeof drawTrend === 'function') drawTrend();
    };
    const slot = document.getElementById('theme-toggle-slot');
    if (slot) slot.appendChild(btn);
    else { btn.classList.add('floating'); document.body.appendChild(btn); }
    update();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
