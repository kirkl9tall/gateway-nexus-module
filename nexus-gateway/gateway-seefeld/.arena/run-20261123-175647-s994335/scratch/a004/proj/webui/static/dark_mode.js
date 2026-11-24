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
    :root[data-theme="dark"] {
      --bg: #141719 !important;
      --bg2: #141719 !important;
      --bg3: #1c2023 !important;
      --border: #3a3e42 !important;
      --accent: #7fa6cc !important;
      --accent2: #94bce3 !important;
      --accent-ink: #94bce3 !important;
      --accent-tint: rgba(127,166,204,0.14) !important;
      --green: #7fa6cc !important;
      --red: #e38a80 !important;
      --yellow: #d9a54c !important;
      --text: #e3e5e7 !important;
      --text2: #b9bcc0 !important;
      --text3: #8d9196 !important;
      /* wizard + legacy pages */
      --card-bg: #141719 !important;
      --card-side: #1c2023 !important;
      --surface: #1c2023 !important;
      --surface-alt: #25292c !important;
      --primary: #7fa6cc !important;
      --primary-hover: #94bce3 !important;
      --fg: #e3e5e7 !important;
      --muted: #8d9196 !important;
    }
    :root[data-theme="dark"] body { background: var(--bg); color: var(--text); }
    :root[data-theme="dark"] .target-type { background: #25292c; }
    :root[data-theme="dark"] .license-badge.active { background: #1d2d3d; color: #d6ebff; }
    :root[data-theme="dark"] input, :root[data-theme="dark"] select, :root[data-theme="dark"] textarea {
      background: var(--bg3); color: var(--text); border-color: var(--border);
    }
    :root[data-theme="dark"] table { background: transparent; }
    :root[data-theme="dark"] table td, :root[data-theme="dark"] table th {
      color: var(--text); border-color: var(--border);
    }
    #theme-toggle {
      width: 32px; height: 32px; border: 1px solid var(--border, #cfd0d3);
      background: transparent; color: var(--text2, #4a4c4f); cursor: pointer;
      display: flex; align-items: center; justify-content: center; border-radius: 0;
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
    btn.title = 'Tema chiaro / scuro';
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
