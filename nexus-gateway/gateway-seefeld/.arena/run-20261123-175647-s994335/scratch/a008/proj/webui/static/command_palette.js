/*
 * Command Palette — Cmd+K / Ctrl+K to open a fuzzy-search action menu.
 * Zero external deps, works with the existing base.html.
 *
 * Actions are auto-collected from nav links + a static list of ops.
 */
(function() {
  'use strict';

  const ACTIONS = [
    { label: 'Dashboard',              hint: 'Vai al pannello principale',    href: '/'          },
    { label: 'Analizzatori',           hint: 'Lista device connessi',         href: '/analyzers' },
    { label: 'Configurazione',         hint: 'gateway.yaml editor',           href: '/config'    },
    { label: 'Log di sistema',         hint: 'Tail journalctl',               href: '/logs'      },
    { label: 'Trace protocollo',       hint: 'Byte grezzi dai device',        href: '/trace'     },
    { label: 'Dead-letter queue',      hint: 'Messaggi non consegnati',       href: '/dlq'       },
    { label: 'Frame Inspector',        hint: 'Ispezione trasformazioni',      href: '/inspect'   },
    { label: 'Topology live',          hint: 'Mappa flusso animata',          href: '/topology'  },
    { label: 'Utenti',                 hint: 'RBAC + TOTP',                   href: '/users'     },
    { label: 'Licenza',                hint: 'Chiave e stato licenza',        href: '/license'   },
    { label: 'Setup Wizard',           hint: 'Riavvia setup guidato',         href: '/wizard/1'  },
    { label: 'Retry tutti DLQ',        hint: 'Ritenta ogni messaggio bloccato', action: 'retryAllDlq' },
    { label: 'Esci',                   hint: 'Chiudi sessione',               href: '/logout'    },
  ];

  const overlay = document.createElement('div');
  overlay.id = 'cmdk-overlay';
  overlay.innerHTML = `
    <style>
      #cmdk-overlay { position: fixed; inset: 0; background: rgba(15,23,42,0.65);
                      z-index: 9999; display: none; align-items: flex-start;
                      justify-content: center; padding-top: 15vh; }
      #cmdk-overlay.visible { display: flex; }
      #cmdk-box { width: min(560px, 90vw); background: #fff; border-radius: 12px;
                  box-shadow: 0 20px 40px rgba(0,0,0,0.3); overflow: hidden; }
      #cmdk-input { width: 100%; padding: 16px 20px; border: none; outline: none;
                    font-size: 1rem; border-bottom: 1px solid #e2e8f0; }
      #cmdk-list { list-style: none; margin: 0; padding: 4px 0; max-height: 60vh;
                   overflow-y: auto; }
      #cmdk-list li { padding: 10px 20px; display: flex; justify-content: space-between;
                      cursor: pointer; font-size: 0.9rem; }
      #cmdk-list li.active { background: #0891b2; color: #fff; }
      #cmdk-list li.active .hint { color: #cbd5e1; }
      .cmdk-hint { color: #94a3b8; font-size: 0.8rem; }
      #cmdk-hint-footer { padding: 8px 20px; font-size: 0.75rem;
                          background: #f8fafc; color: #64748b; border-top: 1px solid #e2e8f0; }
    </style>
    <div id="cmdk-box">
      <input id="cmdk-input" type="text" placeholder="Digita per cercare azioni..." autofocus>
      <ul id="cmdk-list"></ul>
      <div id="cmdk-hint-footer">↑↓ per navigare · Invio per eseguire · Esc per chiudere</div>
    </div>
  `;
  document.body.appendChild(overlay);
  const input = document.getElementById('cmdk-input');
  const list  = document.getElementById('cmdk-list');
  let filtered = ACTIONS.slice();
  let cursor = 0;

  function fuzzyMatch(text, query) {
    if (!query) return true;
    const t = text.toLowerCase(), q = query.toLowerCase();
    let i = 0;
    for (const ch of q) {
      i = t.indexOf(ch, i);
      if (i === -1) return false;
      i++;
    }
    return true;
  }
  function render() {
    list.innerHTML = filtered.map((a, i) => `
      <li class="${i === cursor ? 'active' : ''}" data-i="${i}">
        <span>${a.label}</span>
        <span class="cmdk-hint">${a.hint || ''}</span>
      </li>
    `).join('');
    Array.from(list.children).forEach(li => {
      li.onclick = () => execute(parseInt(li.dataset.i));
    });
  }
  function filter() {
    const q = input.value.trim();
    filtered = ACTIONS.filter(a => fuzzyMatch(a.label + ' ' + (a.hint||''), q));
    cursor = 0;
    render();
  }
  function execute(i) {
    const a = filtered[i];
    if (!a) return;
    close();
    if (a.href) location.href = a.href;
    else if (a.action === 'retryAllDlq') {
      fetch('/api/dlq/replay-all', {method: 'POST'})
        .then(r => r.json())
        .then(d => alert('Retry: ' + JSON.stringify(d)))
        .catch(e => alert('Errore: ' + e));
    }
  }
  function open() {
    overlay.classList.add('visible');
    input.value = '';
    filter();
    setTimeout(() => input.focus(), 10);
  }
  function close() { overlay.classList.remove('visible'); }

  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      open();
    }
    if (!overlay.classList.contains('visible')) return;
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown') {
      e.preventDefault();
      cursor = Math.min(cursor + 1, filtered.length - 1);
      render();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      cursor = Math.max(0, cursor - 1);
      render();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      execute(cursor);
    }
  });
  input.addEventListener('input', filter);
})();
