# Baseline: the current implementation the user was not satisfied with

Complaint: not responsive in the browser, some things not well rendered in their places (e.g. the gateway pill in the header covered the brand name).

## webui/templates/base.html
```
<!DOCTYPE html>
<html lang="{{ current_lang() }}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}JerumedNexus{% endblock %}</title>
  <style>
    /* Fonts are served by the Pi: practices are often offline. */
    @font-face { font-family: "Atkinson Hyperlegible"; font-style: normal; font-weight: 400; font-display: swap;
      src: url("/static/fonts/AtkinsonHyperlegible-Regular.woff2") format("woff2"); }
    @font-face { font-family: "Atkinson Hyperlegible"; font-style: normal; font-weight: 700; font-display: swap;
      src: url("/static/fonts/AtkinsonHyperlegible-Bold.woff2") format("woff2"); }

    /* ── Design tokens (docs/UI-DESIGN-ARENA.md). Old variable names are kept
          so pages not redesigned yet still pick up the new look. ── */
    :root {
      --page:      #F3F6F7;
      --surface:   #FFFFFF;
      --ink:       #17202A;
      --ink-2:     #4B5763;
      --ink-3:     #5F6B77;
      --line:      #D5DCE1;
      --brand:     #2C5F8A;
      --brand-2:   #234C6F;
      --brand-tint:#E6EEF5;
      --good:      #1E7A46;  --good-tint: #E3F2E9;
      --warn:      #8A5A00;  --warn-fill: #E9A820; --warn-tint: #FBF1DA;
      --crit:      #B42318;  --crit-tint: #FBE6E3;
      --neutral:   #5F6B77;  --neutral-tint: #ECEFF2;
      --radius:    10px;

      /* legacy names → new tokens */
      --bg: var(--page); --bg2: var(--surface); --bg3: #EEF2F4; --card: var(--surface);
      --border: var(--line); --accent: var(--brand); --accent2: var(--brand-2);
      --accent-ink: var(--brand); --accent-tint: var(--brand-tint);
      --green: var(--good); --red: var(--crit); --yellow: var(--warn);
      --text: var(--ink); --text2: var(--ink-2); --text3: var(--ink-3);
      --mono:    ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
      --sans:    "Atkinson Hyperlegible", system-ui, sans-serif;
      --display: "Atkinson Hyperlegible", system-ui, sans-serif;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { font-size: 18px; -webkit-text-size-adjust: 100%; }
    body {
      background: var(--page); color: var(--ink); font-family: var(--sans);
      font-weight: 400; line-height: 1.5; min-height: 100vh;
      font-variant-numeric: tabular-nums;
    }
    a { color: var(--brand); }
    a:hover { color: var(--brand-2); }
    :focus { outline: none; }
    :focus-visible { outline: 3px solid var(--brand); outline-offset: 3px; border-radius: 4px; }
    ::selection { background: var(--brand-tint); }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }

    /* ── Header ── */
    .topbar {
      height: 68px; background: var(--surface); border-bottom: 1px solid var(--line);
      display: flex; align-items: center; gap: 18px; padding: 0 24px;
      position: sticky; top: 0; z-index: 20;
    }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 1.05rem;
      color: var(--ink); text-decoration: none; white-space: nowrap; min-width: 232px; flex: none; }
    .brand img { height: 30px; width: auto; }
    .brand span { color: var(--ink-3); font-weight: 400; }
    .hdr-pill { display: flex; align-items: center; gap: 10px; font-size: 0.95rem; white-space: nowrap; }
    .hdr-pill > * { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px;
      border-radius: 999px; text-decoration: none; color: var(--ink); background: var(--neutral-tint); }
    .hdr-pill > a { background: var(--warn-tint); color: var(--warn); font-weight: 700; }
    .hdr-pill .on  { background: var(--good-tint); color: var(--good); }
    .hdr-pill .off { background: var(--crit-tint); color: var(--crit); }
    .topbar-spacer { flex: 1; min-width: 0; }
    .hdr-user { display: flex; align-items: center; gap: 10px; font-size: 0.95rem; white-space: nowrap; color: var(--ink-2); }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none; }
    .dot.green { background: var(--good); } .dot.red { background: var(--crit); } .dot.grey { background: var(--neutral); }
    .btn-icon {
      width: 44px; height: 44px; border: 1px solid var(--line); border-radius: var(--radius);
      background: var(--surface); color: var(--ink-2); cursor: pointer;
      display: flex; align-items: center; justify-content: center; text-decoration: none;
    }
    .btn-icon:hover { border-color: var(--brand); color: var(--brand); }

    /* ── Sidebar ── */
    .shell { display: flex; min-height: calc(100vh - 68px); }
    .sidebar {
      width: 256px; background: var(--surface); border-right: 1px solid var(--line);
      display: flex; flex-direction: column; flex-shrink: 0;
      position: sticky; top: 68px; height: calc(100vh - 68px); overflow-y: auto;
    }
    .sidebar nav { padding: 16px 12px; flex: 1; display: flex; flex-direction: column; gap: 4px; }
    .nav-section { font-size: 0.85rem; color: var(--ink-3); padding: 18px 12px 6px; }
    .nav-link {
      display: flex; align-items: center; gap: 14px; min-height: 52px;
      padding: 10px 14px; border-radius: var(--radius);
      color: var(--ink); text-decoration: none; font-size: 1.05rem;
    }
    .nav-link:hover { background: var(--page); color: var(--ink); }
    .nav-link.active { background: var(--brand-tint); color: var(--brand-2); font-weight: 700; }
    .nav-link svg { flex-shrink: 0; width: 24px; height: 24px; }
    .tech-nav .nav-link { min-height: 40px; font-size: 0.92rem; color: var(--ink-2); }
    .tech-nav .nav-link svg { width: 18px; height: 18px; }
    .nav-badge { margin-left: auto; font-size: 0.8rem; font-weight: 700; padding: 1px 9px;
      border-radius: 999px; color: #fff; display: none; }
    .sidebar-footer { padding: 14px 24px; border-top: 1px solid var(--line); }
    .device-info { font-size: 0.8rem; color: var(--ink-3); line-height: 1.6; }
    body[data-view="studio"] .tech-only { display: none !important; }
    body[data-view="tech"]   .studio-only { display: none !important; }

    /* ── Main ── */
    .main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
    .content { padding: 32px 40px 64px; flex: 1; max-width: 1280px; width: 100%; }
    .page-kicker { font-size: 0.9rem; color: var(--ink-3); }
    .page-h1 { font-weight: 700; font-size: 2rem; line-height: 1.15; margin: 2px 0 18px; }
    .page-desc { color: var(--ink-2); max-width: 68ch; margin-top: -8px; margin-bottom: 20px; }

    /* ── Cards ── */
    .card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
      padding: 22px 24px; margin-bottom: 24px; }
    .card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px;
      margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
    .card-title { font-size: 1.15rem; font-weight: 700; color: var(--ink); display: flex; align-items: center; gap: 8px; }
    .card-title svg { color: var(--brand); }
    .grid-4 { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 16px; margin-bottom: 24px; }
    .grid-2 { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 24px; }
    @media (max-width: 900px) { .grid-4 { grid-template-columns: repeat(2, minmax(0,1fr)); } .grid-2 { grid-template-columns: 1fr; } }
    .stat { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px 18px; }
    .stat-label { font-size: 0.85rem; color: var(--ink-3); margin-bottom: 6px; }
    .stat-value { font-size: 2rem; font-weight: 700; color: var(--ink); line-height: 1.1; }
    .stat-value.red { color: var(--crit); }
    .stat-sub { font-size: 0.85rem; color: var(--ink-3); margin-top: 4px; }

    /* ── Buttons ── */
    .btn {
      display: inline-flex; align-items: center; justify-content: center; gap: 8px;
      min-height: 48px; padding: 10px 20px; font: inherit; font-size: 1rem; font-weight: 700;
      border-radius: var(--radius); border: 2px solid var(--line); cursor: pointer;
      text-decoration: none; white-space: nowrap; background: var(--surface); color: var(--ink);
    }
    .btn:hover { border-color: var(--brand); color: var(--brand); }
    .btn-primary, .btn-success { background: var(--brand); border-color: var(--brand); color: #fff; }
    .btn-primary:hover, .btn-success:hover { background: var(--brand-2); border-color: var(--brand-2); color: #fff; }
    .btn-danger { border-color: var(--crit); color: var(--crit); }
    .btn-danger:hover { background: var(--crit-tint); color: var(--crit); }
    .btn-ghost { background: transparent; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }

    /* ── Forms ── */
    .form-group { margin-bottom: 16px; }
    .form-label { display: block; font-size: 0.9rem; color: var(--ink-2); margin-bottom: 6px; }
    .form-control, .form-input {
      width: 100%; background: var(--surface); border: 2px solid var(--line); border-radius: 8px;
      color: var(--ink); padding: 8px 12px; min-height: 44px; font: inherit; font-size: 1rem;
    }
    .form-control:focus, .form-input:focus { border-color: var(--brand); }
    .form-control.mono { font-family: var(--mono); font-size: 0.9rem; }

    /* ── Legacy blocks used by technician pages ── */
    .target-row { display: flex; align-items: center; gap: 12px; padding: 12px 4px; border-bottom: 1px solid var(--line); }
    .target-row.disabled { opacity: 0.55; }
    .target-name { font-weight: 700; flex: 1; }
    .target-type { font-size: 0.8rem; color: var(--ink-2); background: var(--page); padding: 2px 8px; border-radius: 6px; }
    .target-status { font-size: 0.9rem; white-space: nowrap; }
    .target-status.ok { color: var(--good); } .target-status.err { color: var(--crit); } .target-status.off { color: var(--ink-3); }
    .service-badge { display: flex; align-items: center; gap: 8px; font-size: 0.9rem; padding: 4px 12px;
      border: 1px solid var(--line); border-radius: 999px; }
    .log-viewer { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
      padding: 12px 16px; font-family: var(--mono); font-size: 0.8rem; line-height: 1.75; max-height: 520px; overflow-y: auto; }
    .log-line { border-bottom: 1px solid var(--page); }
    .log-line.error { color: var(--crit); background: var(--crit-tint); }
    .log-line.warn { color: var(--warn); } .log-line.ok { color: var(--good); }
    .toggle { position: relative; display: inline-block; width: 44px; height: 24px; flex-shrink: 0; }
    .toggle input { opacity: 0; width: 0; height: 0; }
    .toggle-slider { position: absolute; inset: 0; background: var(--line); border-radius: 999px; cursor: pointer; transition: 0.15s; }
    .toggle-slider:before { content: ""; position: absolute; width: 18px; height: 18px; left: 3px; top: 3px; background: #fff; border-radius: 50%; transition: 0.15s; }
    input:checked + .toggle-slider { background: var(--brand); }
    input:checked + .toggle-slider:before { transform: translateX(20px); }
    .alert { padding: 14px 18px; border-radius: var(--radius); font-size: 1rem; margin-bottom: 18px;
      display: flex; align-items: center; gap: 12px; background: var(--brand-tint); color: var(--ink); }
    .alert-success { background: var(--good-tint); }
    .alert-error { background: var(--crit-tint); color: var(--crit); }
    .alert-info { background: var(--brand-tint); }
    .alert-warn { background: var(--warn-tint); }
    .license-badge { display: inline-flex; align-items: center; gap: 5px; font-size: 0.8rem; padding: 2px 10px; border-radius: 999px; }
    .license-badge.active { background: var(--good-tint); color: var(--good); }
    .license-badge.inactive { background: var(--crit-tint); color: var(--crit); }
    #yaml-editor { width: 100%; min-height: 440px; background: var(--surface); border: 2px solid var(--line);
      border-radius: var(--radius); color: var(--ink); padding: 16px; font-family: var(--mono); font-size: 0.85rem; line-height: 1.7; }
    .conn-cards { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; margin-bottom: 20px; }
    .conn-card { border: 2px solid var(--line); border-radius: var(--radius); padding: 16px; cursor: pointer; text-align: left; background: var(--surface); font: inherit; }
    .conn-card.selected { border-color: var(--brand); background: var(--brand-tint); }
    .conn-card .icon { display: none; }
    .conn-card .label { font-size: 1.05rem; font-weight: 700; }
    .conn-card .desc { font-size: 0.85rem; color: var(--ink-3); margin-top: 3px; }
    #toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); max-width: min(560px, 92vw);
      padding: 14px 20px; border-radius: var(--radius); font-size: 1rem; font-weight: 700; z-index: 9999; display: none;
      box-shadow: 0 10px 30px rgba(23,32,42,0.25); }

    /* ── Status chip: colour + icon shape + word, never colour alone ── */
    .chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px 6px 10px;
      border-radius: 999px; font-weight: 700; font-size: 0.95rem; white-space: nowrap; }
    .chip svg { width: 20px; height: 20px; flex: none; }
    .chip.good { background: var(--good-tint); color: var(--good); }
    .chip.warning { background: var(--warn-tint); color: var(--warn); }
    .chip.critical { background: var(--crit-tint); color: var(--crit); }
    .chip.neutral { background: var(--neutral-tint); color: var(--neutral); }

    /* ── Technician zone: always at the bottom, closed by default ── */
    .tech-zone { margin-top: 48px; border-top: 2px dashed var(--line); padding-top: 20px; }
    .tech-zone > summary { cursor: pointer; list-style: none; display: flex; align-items: center; gap: 10px;
      color: var(--ink-2); font-weight: 700; min-height: 48px; }
    .tech-zone > summary::-webkit-details-marker { display: none; }
    .tech-zone > summary::before { content: "▸"; font-size: 1.1rem; }
    .tech-zone[open] > summary::before { content: "▾"; }
    .tech-zone > summary small { font-weight: 400; color: var(--ink-3); }
    .tech-zone-body { margin-top: 20px; }

    /* ── Smaller screens: the menu becomes a scrollable row under the header ── */
    .hdr-name { white-space: nowrap; }
    @media (max-width: 900px) {
      .topbar { height: 60px; padding: 0 12px; gap: 10px; }
      .brand { min-width: 0; }
      .brand span, .hdr-user > span, #theme-toggle-slot { display: none; }
      .shell { flex-direction: column; min-height: calc(100vh - 60px); }
      .sidebar { position: sticky; top: 60px; z-index: 15; width: 100%; height: auto;
        border-right: 0; border-bottom: 1px solid var(--line); overflow-x: auto; overflow-y: hidden; }
      .sidebar nav { flex-direction: row; padding: 6px 8px; gap: 4px; }
      .nav-link, .tech-nav .nav-link { flex: none; min-height: 48px; white-space: nowrap; padding: 8px 14px; font-size: 1rem; }
      .tech-nav { display: contents; }
      .nav-section, .sidebar-footer { display: none; }
      .content { padding: 20px 16px 48px; }
    }
    @media (max-width: 560px) {
      .brand { font-size: 0; gap: 0; }          /* logo only */
      .hdr-pill { font-size: 0.85rem; }
      .hdr-pill > * { padding: 6px 10px; }
      .lang-picker svg { display: none; }
      .lang-picker select { font-size: 0.9rem; max-width: 110px; }
      .btn-icon { width: 40px; height: 40px; }
    }
  </style>
  <meta name="csrf-token" content="{{ csrf_token() }}">
  {% include "_i18n_head.html" %}
  <link rel="stylesheet" href="/static/ui.css?v=2">
  {% block head %}{% endblock %}
</head>
<body data-view="{{ 'tech' if current_role == 'admin' else 'studio' }}" data-role="{{ current_role }}">


<header class="topbar">
  <a href="/" class="brand"><img src="/static/logo.png" alt="">JerumedNexus <span>Gateway</span></a>
  <div class="hdr-pill">
    {# Gateway on/off: refreshed by pollStatus() below #}
    <span id="svc-badge"><span class="dot grey" id="svc-dot"></span><span id="svc-text">{{ t("Verifico…") }}</span></span>
    <a href="/dlq" id="hdr-dlq" style="display:none;"><span id="hdr-dlq-text"></span></a>
  </div>
  <div class="topbar-spacer"></div>
  {% include "_lang_select.html" %}
  <span id="theme-toggle-slot"></span>
  <div class="hdr-user">
    <span>{{ current_user or '' }}</span>
    <a href="/logout" class="btn-icon" title="{{ t('Esci') }}" aria-label="{{ t('Esci') }}" onclick="return confirm(T('Uscire dalla sessione?'))">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
    </a>
  </div>
</header>

<div class="shell">
<aside class="sidebar">
  <nav aria-label="{{ t('Menu') }}">
    {# For everybody: the four questions a practice actually has. #}
    <a href="/" class="nav-link {% if request.endpoint == 'dashboard' %}active{% endif %}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>
      {{ t("Panoramica") }}
    </a>
    <a href="/analyzers" class="nav-link {% if request.endpoint == 'analyzers' %}active{% endif %}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 3h6"/><path d="M10 3v6.5L4.5 19a1.5 1.5 0 0 0 1.3 2.2h12.4a1.5 1.5 0 0 0 1.3-2.2L14 9.5V3"/><path d="M7 15h10"/></svg>
      {{ t("Apparecchi") }}
      <span id="pending-devices-badge" class="nav-badge" style="background:var(--brand);"></span>
    </a>
    <a href="/verifica" class="nav-link {% if request.endpoint and request.endpoint.startswith('verifica.') %}active{% endif %}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      {{ t("Verifica impianto") }}
    </a>
    <a href="/results" class="nav-link {% if request.endpoint == 'results_page' %}active{% endif %}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>
      {{ t("Risultati") }}
    </a>

    {# Technician only: hidden for doctors (data-view="studio"). #}
    <div class="tech-only tech-nav">
      <div class="nav-section">{{ t("Per il tecnico") }}</div>
      <a href="/dlq" class="nav-link {% if request.endpoint == 'dlq_page' %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
        {{ t("Da rispedire") }}
        <span id="dlq-badge" class="nav-badge" style="background:var(--warn);"></span>
      </a>
      <a href="/logs" class="nav-link {% if request.endpoint in ('logs_page', 'trace_page') %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
        {{ t("Log e trace") }}
      </a>
      <a href="/inspect" class="nav-link {% if request.endpoint and request.endpoint.startswith('inspect.') %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        Frame Inspector
      </a>
      <a href="/config" class="nav-link {% if request.endpoint == 'config_page' %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        {{ t("Configurazione") }}
      </a>
      <a href="/users" class="nav-link {% if request.endpoint == 'users_page' %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
        {{ t("Utenti") }}
      </a>
      <a href="/license" class="nav-link {% if request.endpoint == 'license_page' %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        {{ t("Licenza") }}
      </a>
      <a href="/topology" class="nav-link {% if request.endpoint and request.endpoint.startswith('topology.') %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M8.5 8.5l7 7"/></svg>
        {{ t("Topologia") }}
      </a>
      <a href="/replay" class="nav-link {% if request.endpoint and request.endpoint.startswith('wire_replay.') %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        Wire Replay
      </a>
    </div>
  </nav>
  <div class="sidebar-footer">
    <div class="device-info">
      <div>{{ hostname or '' }}</div>
      <div>v{{ gateway_version }}{% if serial %} · S/N {{ serial[:16] }}{% endif %}</div>
    </div>
  </div>
</aside>

<!-- Main -->
<div class="main">
  <div class="content">
    {% block page_header %}<h1 class="page-h1">{% block page_title %}{% endblock %}</h1>{% endblock %}
    {% if demo_mode %}
    <div class="alert" style="border-left-color:var(--yellow);background:rgba(154,100,16,0.08);font-weight:500;">
      {{ t("DEMO MODE — dati simulati, non usare in produzione") }}
    </div>
    {% endif %}
    {% if warn_placeholder %}
    <div class="alert alert-error">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="flex-shrink:0"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      <span><strong>{{ t("Configurazione incompleta:") }}</strong>
      {{ t("Il nome dello studio non è ancora stato inserito.") }}
      <a href="/config">{{ t("Inseriscilo in Configurazione") }}</a> {{ t("prima di usare il gateway.") }}</span>
    </div>
    {% endif %}
    {% block content %}{% endblock %}
  </div>
</div>
</div>

<!-- Toast notification -->
<div id="toast"></div>

<script>
// ── CSRF: auto-inject X-CSRF-Token on non-GET /api/ fetches ────────
(function() {
  const _tokEl = document.querySelector('meta[name="csrf-token"]');
  const CSRF_TOKEN = _tokEl ? _tokEl.getAttribute('content') : '';
  window.CSRF_TOKEN = CSRF_TOKEN;
  const _origFetch = window.fetch.bind(window);
  window.fetch = function(input, init) {
    init = init || {};
    const raw = (typeof input === 'string') ? input : (input && input.url) || '';
    const method = (init.method || (input && input.method) || 'GET').toUpperCase();
    // Resolve the URL so this works for relative ("/api/x"), absolute
    // ("http://host/api/x") and reverse-proxy subpath ("/gateway/api/x")
    // forms alike — the old `indexOf('/api/') === 0` check silently dropped
    // the token for anything that wasn't a bare relative path, which the
    // server then rejected as "CSRF token invalido".
    let path = raw, sameOrigin = true;
    try {
      const u = new URL(raw, window.location.origin);
      path = u.pathname;
      sameOrigin = (u.origin === window.location.origin);
    } catch (e) { /* keep raw string on parse failure */ }
    if (CSRF_TOKEN && method !== 'GET' && sameOrigin && path.indexOf('/api/') !== -1) {
      init.headers = Object.assign({}, init.headers || {}, {'X-CSRF-Token': CSRF_TOKEN});
    }
    return _origFetch(input, init);
  };
})();

// ── Service status polling ─────────────────────────────────────────
async function pollStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    const dot  = document.getElementById('svc-dot');
    const text = document.getElementById('svc-text');
    const svc  = d.service_systemd || 'unknown';
    // systemd answer, or (no systemd, e.g. a dev PC) the freshness of status.json
    var on = svc === 'active' || (svc !== 'inactive' && svc !== 'failed' && d.running &&
             d.updated_at && (Date.now() - new Date(d.updated_at).getTime()) < 660000);
    var badge = document.getElementById('svc-badge');
    badge.className = on ? 'on' : 'off';
    dot.className  = 'dot ' + (on ? 'green' : 'red');
    text.textContent = on ? T('Gateway acceso') : T('Gateway spento');
    if (window._onStatusUpdate) window._onStatusUpdate(d);
  } catch(e) {}
}
pollStatus();
setInterval(pollStatus, 5000);

// ── Pending devices badge polling ──────────────────────────────────
async function pollPendingDevices() {
  try {
    const r = await fetch('/api/devices/discovered');
    const d = await r.json();
    const el = document.getElementById('pending-devices-badge');
    if (!el) return;
    const n = (d.pending || []).length;
    if (n > 0) {
      el.textContent = n;
      el.style.display = 'inline-block';
      el.title = T('{n} nuovi apparecchi trovati — apri Analizzatori per attivarli', {n: n});
    } else {
      el.style.display = 'none';
    }
  } catch(e) {}
}
pollPendingDevices();
setInterval(pollPendingDevices, 15000);

// ── PWA + command palette ─────────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/service_worker.js').catch(() => {});
}
(function() {
  const s = document.createElement('script');
  s.src = '/static/command_palette.js';
  s.defer = true;
  document.head.appendChild(s);
  const dm = document.createElement('script');
  dm.src = '/static/dark_mode.js';
  dm.defer = true;
  document.head.appendChild(dm);
  const link = document.createElement('link');
  link.rel = 'manifest';
  link.href = '/static/manifest.webmanifest';
  document.head.appendChild(link);
})();

// ── DLQ badge polling ──────────────────────────────────────────────
async function pollDlq() {
  try {
    const r = await fetch('/api/dlq?limit=1');
    if (r.status === 403) return;   // viewer can't see DLQ
    const d = await r.json();
    const el = document.getElementById('dlq-badge');
    if (!el) return;
    const n = (d.entries || []).length > 0
      ? await fetch('/api/dlq?limit=200').then(x => x.json()).then(x => (x.entries||[]).length)
      : 0;
    const hd = document.getElementById('hdr-dlq');
    if (hd) {
      hd.style.display = n > 0 ? '' : 'none';
      document.getElementById('hdr-dlq-text').textContent = T('{n} risultati in attesa', {n: n});
    }
    if (n > 0) {
      el.textContent = n; el.style.display = 'inline-block';
      el.title = T('{n} messaggi da rispedire', {n: n});
    } else {
      el.style.display = 'none';
    }
    if (window._onDlqCount) window._onDlqCount(n);
  } catch(e) {}
}
pollDlq();
setInterval(pollDlq, 30000);


// ── Toast ──────────────────────────────────────────────────────────
function toast(msg, type='info') {
  const el = document.getElementById('toast');
  const styles = getComputedStyle(document.documentElement);
  const bg = type === 'error' ? styles.getPropertyValue('--red') : styles.getPropertyValue('--text');
  el.style.background = bg.trim() || '#1d1f20';
  el.style.border = '0';
  el.style.color = styles.getPropertyValue('--bg').trim() || '#f2f2f3';
  el.textContent = msg;
  el.style.display = 'block';
  clearTimeout(el._t);
  el._t = setTimeout(() => el.style.display = 'none', 3800);
}
</script>
{% block scripts %}{% endblock %}
</body>
</html>
```

## webui/templates/dashboard.html
```
{% extends "base.html" %}
{% block title %}{{ t("Panoramica") }} — JerumedNexus{% endblock %}
{% block page_header %}{% endblock %}

{% block content %}
{% set dl = days_left if days_left is defined else none %}
{% if dl is not none and dl <= 30 %}
<div class="alert alert-warn">
  <span>
  {% if dl <= 0 %}
    <strong>{{ t("Licenza scaduta") }}</strong> — {{ t("il gateway continua a funzionare ma non riceve aggiornamenti. Contattare il rivenditore.") }}
  {% else %}
    <strong>{{ t("Licenza in scadenza") }}</strong> — <strong>{{ t("mancano {n} giorni", n=dl) }}</strong>.
    <a href="/license" style="margin-left:8px;">{{ t("Vai al rinnovo") }}</a>
  {% endif %}
  </span>
</div>
{% endif %}

{# For everybody: rendered here and refreshed every 15 s from /overview/live #}
<div id="ov-live">{% include "_overview_live.html" %}</div>

{# ── For the technician: always at the bottom, closed by default ── #}
<details class="tech-zone tech-only" id="tech-zone">
  <summary>{{ t("Dettagli per il tecnico") }} <small>{{ t("errori, tempi, eventi, servizio, aggiornamenti") }}</small></summary>
  <div class="tech-zone-body">

    <div class="grid-4">
      <div class="stat"><div class="stat-label">{{ t("Errori oggi") }}</div>
        <div class="stat-value {% if status.errors_today > 0 %}red{% endif %}" id="stat-errors">{{ status.errors_today }}</div>
        <div class="stat-sub">{{ t("trasmissioni fallite") }}</div></div>
      <div class="stat"><div class="stat-label">{{ t("Totale storico") }}</div>
        <div class="stat-value" id="stat-total">{{ status.results_total }}</div>
        <div class="stat-sub">{{ t("dall'installazione") }}</div></div>
      <div class="stat"><div class="stat-label">{{ t("Uptime") }}</div>
        <div class="stat-value" id="stat-uptime">—</div>
        <div class="stat-sub">{{ t("ore operative") }}</div></div>
      <div class="stat"><div class="stat-label">{{ t("Latenza P95") }}</div>
        <div class="stat-value" id="stat-p95">{% if status.latency_p95_ms %}{{ status.latency_p95_ms|round|int }} ms{% else %}—{% endif %}</div>
        <div class="stat-sub">{{ t("analizzatore") }} &rarr; {{ t("gestionale") }}</div></div>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-header">
          <div class="card-title">{{ t("Ultime 24 ore") }}</div>
          <div style="display:flex;gap:14px;font-size:0.85rem;color:var(--ink-3);">
            <span><span class="dot" style="background:var(--brand);"></span> {{ t("OK") }}</span>
            <span><span class="dot" style="background:var(--warn-fill);"></span> {{ t("Parziali") }}</span>
            <span><span class="dot" style="background:var(--crit);"></span> {{ t("Errori") }}</span>
          </div>
        </div>
        <svg id="trend-svg" viewBox="0 0 720 160" style="width:100%;height:190px;display:block;"></svg>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title">{{ t("Eventi recenti") }}</div>
          <a href="/logs" style="font-size:0.9rem;">{{ t("Tutti i log") }}</a>
        </div>
        <div id="eventi-recenti" style="display:flex;flex-direction:column;">
          <div style="color:var(--ink-3);padding:14px 0;">{{ t("Carico…") }}</div>
        </div>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-header"><div class="card-title">{{ t("Controllo servizio") }}</div></div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="serviceAction('start')">{{ t("Avvia") }}</button>
          <button class="btn" onclick="serviceAction('restart')">{{ t("Riavvia") }}</button>
          <button class="btn btn-danger" onclick="if(confirm(T('Fermare il gateway? Finché è fermo nessun risultato arriva al gestionale.'))) serviceAction('stop')">{{ t("Ferma") }}</button>
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title">{{ t("Aggiornamenti software") }}</div>
          <span id="update-status" style="font-size:0.9rem;color:var(--ink-3);">—</span>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <button class="btn" onclick="checkUpdate()">{{ t("Verifica") }}</button>
          <button class="btn btn-primary" style="display:none;" id="btn-update" onclick="applyUpdate()">{{ t("Aggiorna ora") }}</button>
        </div>
      </div>
    </div>

    <div class="card" id="discovered-card" style="display:none;">
      <div class="card-header">
        <div class="card-title">{{ t("Device rilevati — da assegnare") }}</div>
        <span id="discovered-count" style="font-size:0.9rem;color:var(--ink-3);"></span>
      </div>
      <p style="color:var(--ink-2);margin-bottom:12px;">
        {{ t("Il gateway ha rilevato questi cavi USB. Scegli a quale analizzatore corrispondono e clicca «Assegna». La configurazione viene salvata da sola.") }}
      </p>
      <div id="discovered-list" style="display:flex;flex-direction:column;"></div>
    </div>

  </div>
</details>
{% endblock %}

{% block scripts %}
<script>
// ── Live area: re-rendered by the server, already translated ─────────────
async function ovRefresh() {
  try {
    var r = await fetch('/overview/live', {credentials: 'same-origin'});
    if (!r.ok) return;
    var html = await r.text();
    var box = document.getElementById('ov-live');
    if (box && box.innerHTML.trim() !== html.trim()) box.innerHTML = html;
  } catch (e) { /* network hiccup: keep showing the last state */ }
}
setInterval(ovRefresh, 15000);

async function ovStartGateway(btn) {
  btn.disabled = true;
  toast(T('Avvio…'));
  try {
    var r = await fetch('/api/service/start', {method: 'POST'});
    var d = await r.json();
    if (d.ok) toast(T('Gateway acceso'), 'info');
    else {
      // The technical reason (e.g. "sudo: a terminal is required") means
      // nothing to a doctor: say what to do, keep the detail in the console.
      console.warn('service start failed:', d.error);
      toast(T("Non è stato possibile accendere il gateway. Spegni e riaccendi la scatola grigia, oppure chiama l'assistenza."), 'error');
    }
  } catch (e) {
    toast(T('Errore di rete: {msg}', {msg: e.message}), 'error');
  }
  btn.disabled = false;
  setTimeout(ovRefresh, 2500);
}

// ── Technician zone: loads its data only when opened ─────────────────────
var techZone = document.getElementById('tech-zone');
var techLoaded = false;
if (techZone) {
  techZone.addEventListener('toggle', function () {
    if (techZone.open && !techLoaded) {
      techLoaded = true;
      drawTrend(); caricaEventi(); refreshDiscovered();
      setInterval(drawTrend, 60000); setInterval(caricaEventi, 30000); setInterval(refreshDiscovered, 15000);
    }
  });
}

window._onStatusUpdate = function (d) {
  var el = document.getElementById('stat-errors');
  if (!el) return;
  el.textContent = d.errors_today || 0;
  el.className = 'stat-value ' + ((d.errors_today || 0) > 0 ? 'red' : '');
  document.getElementById('stat-total').textContent = d.results_total || 0;
  var up = d.uptime_seconds || 0;
  document.getElementById('stat-uptime').textContent = Math.floor(up / 3600) + 'h ' + Math.floor((up % 3600) / 60) + 'm';
};

async function serviceAction(action) {
  var labels = {start: T('Avvio…'), stop: T('Arresto…'), restart: T('Riavvio…')};
  toast(labels[action] || T('Eseguo…'), 'info');
  var r = await fetch('/api/service/' + action, {method: 'POST'});
  var d = await r.json();
  if (d.ok) toast(T('Fatto. Stato del servizio: {stato}', {stato: d.status}), 'success');
  else toast(T('Errore: {msg}', {msg: d.error || T('sconosciuto')}), 'error');
  setTimeout(ovRefresh, 2500);
}

async function checkUpdate() {
  var st = document.getElementById('update-status');
  st.textContent = T('Controllo…');
  var r = await fetch('/api/update/check', {method: 'POST'});
  var d = await r.json();
  if (d.ok) {
    st.textContent = d.update_available ? T('Aggiornamento disponibile') : T('Software aggiornato');
    if (d.update_available) document.getElementById('btn-update').style.display = '';
  } else {
    st.textContent = T('Errore di rete');
  }
}

async function applyUpdate() {
  toast(T('Aggiornamento in corso…'), 'info');
  document.getElementById('btn-update').disabled = true;
  var r = await fetch('/api/update/apply', {method: 'POST'});
  var d = await r.json();
  if (d.ok) toast(d.message, 'success');
  else toast(T('Errore: {msg}', {msg: d.error}), 'error');
  document.getElementById('btn-update').disabled = false;
}

async function drawTrend() {
  var svg = document.getElementById('trend-svg');
  if (!svg) return;
  var cs = getComputedStyle(document.documentElement);
  var c = function (n, f) { return cs.getPropertyValue(n).trim() || f; };
  var cGrid = c('--line', '#D5DCE1'), cText = c('--ink-3', '#5F6B77');
  var cOk = c('--brand', '#2C5F8A'), cPart = c('--warn-fill', '#E9A820'), cErr = c('--crit', '#B42318');
  try {
    var d = await (await fetch('/api/history/trend?hours=24')).json();
    var rows = d.hours || [];
    if (!rows.length) {
      svg.innerHTML = '<text x="360" y="80" text-anchor="middle" fill="' + cText + '" font-size="14">' + T('nessun dato nelle ultime 24 ore') + '</text>';
      return;
    }
    var W = 720, H = 160, L = 36, R = 6, TOP = 8, B = 22, CW = W - L - R, CH = H - TOP - B;
    var maxV = Math.max.apply(null, [1].concat(rows.map(function (x) { return x.ok + x.partial + x.err; })));
    var bw = CW / rows.length * 0.78, gap = CW / rows.length * 0.22, out = '';
    for (var i = 0; i <= 4; i++) {
      var y = TOP + CH * i / 4;
      out += '<line x1="' + L + '" y1="' + y + '" x2="' + (W - R) + '" y2="' + y + '" stroke="' + cGrid + '"/>';
      out += '<text x="' + (L - 6) + '" y="' + (y + 4) + '" text-anchor="end" fill="' + cText + '" font-size="11">' + Math.round(maxV * (1 - i / 4)) + '</text>';
    }
    rows.forEach(function (row, i) {
      var x = L + i * (bw + gap) + gap / 2, y = TOP + CH;
      [['err', cErr], ['partial', cPart], ['ok', cOk]].forEach(function (p) {
        var h = row[p[0]] / maxV * CH;
        if (h > 0.5) { out += '<rect x="' + x + '" y="' + (y - h) + '" width="' + bw + '" height="' + h + '" fill="' + p[1] + '"><title>' + row.hour + ': ' + row[p[0]] + '</title></rect>'; y -= h + 1; }
      });
      if (i % 3 === 0) out += '<text x="' + (x + bw / 2) + '" y="' + (H - 5) + '" text-anchor="middle" fill="' + cText + '" font-size="11">' + (row.hour.split('T')[1] || '') + '</text>';
    });
    svg.innerHTML = out;
  } catch (e) {}
}

// Recent events: built with textContent (log lines can contain patient ids).
var RE_LOG = /^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}):\d{2}\s+\[(\w+)\s*\]\s+[\w.]+:\s*(.*)$/;
function rigaEvento(ora, livello, testo) {
  var riga = document.createElement('div');
  riga.style.cssText = 'display:grid;grid-template-columns:52px 12px minmax(0,1fr);gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--line);';
  var o = document.createElement('span'); o.style.cssText = 'font-family:var(--mono);font-size:0.85rem;color:var(--ink-3);'; o.textContent = ora;
  var p = document.createElement('span'); p.className = 'dot';
  p.style.background = (livello === 'ERROR' || livello === 'CRITICAL') ? 'var(--crit)' : livello === 'WARNING' ? 'var(--warn-fill)' : 'var(--brand)';
  var m = document.createElement('span'); m.style.cssText = 'font-size:0.9rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'; m.textContent = testo; m.title = testo;
  riga.append(o, p, m);
  return riga;
}
function messaggioVuoto(testo) {
  var d = document.createElement('div'); d.style.cssText = 'color:var(--ink-3);padding:14px 0;'; d.textContent = testo; return d;
}
async function caricaEventi() {
  var box = document.getElementById('eventi-recenti');
  if (!box) return;
  try {
    var d = await (await fetch('/api/logs?n=80')).json();
    var righe = (d.lines || []).slice().reverse(), n = 0;
    box.textContent = '';
    for (var i = 0; i < righe.length && n < 8; i++) {
      var m = RE_LOG.exec(righe[i]);
      if (!m || m[3].indexOf('USB probe') === 0) continue;
      box.appendChild(rigaEvento(m[1], m[2], m[3])); n++;
    }
    if (!n) box.appendChild(messaggioVuoto(T('Nessun evento registrato.')));
  } catch (e) {
    box.textContent = ''; box.appendChild(messaggioVuoto(T('Log non disponibili.')));
  }
}

var DEVICE_TYPE_OPTIONS = [
  {value: "loc200_serial",    label: "LOC-200 (RS-232)"},
  {value: "sysmex_astm",      label: "Sysmex XP-300 / pocH-100i (RS-232)"},
  {value: "uc1000_serial",    label: "Menarini UC-1000"},
  {value: "reflotron_serial", label: "Roche Reflotron Plus"},
  {value: "cobas_poct",       label: "Roche cobas b101"},
  {value: "mllp_hl7",         label: "HL7 v2 MLLP"},
];
function _esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
async function refreshDiscovered() {
  try {
    var r = await fetch("/api/devices/discovered", {credentials: "same-origin"});
    if (!r.ok) return;
    var data = await r.json();
    var pending = (data.pending || []).filter(function (d) { return !d.activated; });
    var card = document.getElementById("discovered-card");
    if (!pending.length) { card.style.display = "none"; return; }
    card.style.display = "block";
    document.getElementById("discovered-count").textContent = T("{n} da assegnare", {n: pending.length});
    document.getElementById("discovered-list").innerHTML = pending.map(function (d, i) {
      var key = d.key || (d.source + ":" + d.location);
      var opts = DEVICE_TYPE_OPTIONS.map(function (o) {
        return '<option value="' + o.value + '"' + (o.value === d.device_type ? ' selected' : '') + '>' + _esc(o.label) + '</option>';
      }).join('');
      return '<div style="border-top:1px solid var(--line);padding:12px 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap;justify-content:space-between;">' +
        '<div><strong>' + _esc(d.display_name || d.vendor || d.chip || T("dispositivo generico")) + '</strong><br>' +
        '<span style="color:var(--ink-3);font-size:0.9rem;">' + _esc(d.location) + ' ' + _esc(d.usb_id || '') + '</span></div>' +
        '<div style="display:flex;gap:8px;"><select id="dt-' + i + '" class="form-input" style="width:260px;">' + opts + '</select>' +
        '<button class="btn btn-primary" data-key="' + _esc(key) + '" onclick="assignDiscovered(this.dataset.key, \'dt-' + i + '\')">' + T("Assegna") + '</button></div></div>';
    }).join('');
  } catch (e) {}
}
async function assignDiscovered(key, selectId) {
  var sel = document.getElementById(selectId);
  if (!sel || !sel.value) { toast(T("Scegli un tipo di analizzatore."), "error"); return; }
  try {
    var r = await fetch("/api/devices/activate", {method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({key: key, device_type: sel.value})});
    var data = await r.json();
    if (data.ok) { toast(T("Assegnato. Riavvia il gateway (Controllo servizio → Riavvia) per attivare il nuovo device."), "success"); refreshDiscovered(); }
    else toast(T("Errore: {msg}", {msg: data.error || T("operazione non riuscita")}), "error");
  } catch (e) { toast(T("Errore di rete: {msg}", {msg: e.message}), "error"); }
}
</script>
{% endblock %}
```

## webui/templates/_overview_live.html
```
{# Live part of the Overview. Rendered by the server (translated) on page load
   and every 15 s by /overview/live. `ov` comes from webui/overview.py. #}
{% from "_ui.html" import status_icon, chip, machine_icon, link_label, machine_state_text, machine_hint, product_label, dest_state_text %}
{% set h = ov.headline %}
{% set can_act = current_role in ('operator', 'admin') %}

{# ── 1. One sentence: the answer to "is it working?" ── #}
<section class="ov-head {{ h.level }}" aria-live="polite">
  <div class="ov-head-icon">{{ status_icon(h.level) }}</div>
  <div class="ov-head-text">
    <h1>
      {%- if h.key == 'gateway_off' -%}{{ t("Il gateway è spento. I risultati non arrivano allo studio.") }}
      {%- elif h.key == 'no_destination' -%}{{ t("Nessun software dello studio è collegato.") }}
      {%- elif h.key == 'destination_down' -%}{{ t("{name} non riceve i risultati.", name=h.name) }}
      {%- elif h.key == 'waiting' -%}{{ t("Funziona. {n} risultati aspettano di essere inviati.", n=h.n) }}
      {%- elif h.key == 'machine_offline' -%}{{ t("{name}: il cavo non è collegato.", name=h.name) }}
      {%- elif h.key == 'no_machine' -%}{{ t("Nessun apparecchio è ancora collegato.") }}
      {%- else -%}{{ t("Tutto funziona.") }}{%- endif -%}
    </h1>
    <p>
      {%- if h.key == 'gateway_off' -%}{{ t("Gli apparecchi non possono inviare finché il gateway è spento.") }}
      {%- elif h.key == 'no_destination' -%}{{ t("I risultati non vanno da nessuna parte. Il tecnico deve collegare il software dello studio.") }}
      {%- elif h.key == 'destination_down' -%}{{ t("I risultati restano nel gateway e partono appena {name} risponde di nuovo.", name=h.name) }}
      {%- elif h.key == 'waiting' -%}{{ t("Sono conservati nel gateway. Inviali di nuovo quando il software dello studio è raggiungibile.") }}
      {%- elif h.key == 'machine_offline' -%}{{ t("Controlla che il cavo USB sia inserito e che l'apparecchio sia acceso.") }}
      {%- elif h.key == 'no_machine' -%}{{ t("Collega il primo apparecchio per iniziare a ricevere i risultati.") }}
      {%- elif ov.last.ts -%}{{ t("I risultati arrivano a {dest}. Ultimo risultato {quando} da {apparecchio}.", dest=h.dest, quando=ov.last.ts|when, apparecchio=ov.last.device) }}
      {%- else -%}{{ t("I risultati arrivano a {dest}. Nessun risultato ancora oggi.", dest=h.dest) }}{%- endif -%}
    </p>
  </div>
  <div class="ov-head-action">
    {%- if h.key == 'gateway_off' and can_act -%}
      <button class="btn btn-primary btn-lg" onclick="ovStartGateway(this)">{{ t("Accendi il gateway") }}</button>
    {%- elif h.key == 'waiting' and current_role == 'admin' -%}
      <a class="btn btn-primary btn-lg" href="/dlq">{{ t("Invia di nuovo") }}</a>
    {%- elif h.key in ('destination_down', 'machine_offline', 'waiting', 'gateway_off') -%}
      <a class="btn btn-primary btn-lg" href="/verifica">{{ t("Cerca il problema") }}</a>
    {%- elif h.key == 'no_machine' -%}
      <a class="btn btn-primary btn-lg" href="/analyzers">{{ t("Collega un apparecchio") }}</a>
    {%- endif -%}
  </div>
</section>

{# ── 2. The path a result takes: machines → gateway → practice software ── #}
{% set dest_level = 'neutral' if not ov.destinations else
     ('critical' if ov.destinations|selectattr('level', 'equalto', 'critical')|list else
      ('warning' if ov.destinations|selectattr('level', 'equalto', 'warning')|list else
       ('good' if ov.destinations|selectattr('level', 'equalto', 'good')|list else 'neutral'))) %}
{% set n_m = ov.machines|length %}
{% set mach_level = 'neutral' if (not n_m or not ov.gateway.on) else
     ('critical' if ov.machines|selectattr('level', 'equalto', 'critical')|list else
      ('good' if ov.machines_up == n_m else 'warning')) %}
{% set gw_level = 'good' if ov.gateway.on else 'critical' %}
<section class="ov-path {{ 'flowing' if ov.flowing }}" aria-label="{{ t('Percorso dei risultati') }}">
  <a class="ov-station" href="/analyzers">
    <span class="ov-station-label">{{ t("Apparecchi") }}</span>
    <span class="ov-station-value">{{ t("{up} di {n} attivi", up=ov.machines_up, n=n_m) if n_m else "—" }}</span>
    <span class="ov-meter" aria-hidden="true">
      {%- for m in ov.machines %}<i class="{{ m.level }}" title="{{ m.name }}"></i>{% endfor -%}
    </span>
    {%- set n_bad = n_m - ov.machines_up -%}
    {%- if not n_m -%}{%- set mtext = t("Nessuno collegato") -%}
    {%- elif not ov.gateway.on -%}{%- set mtext = t("Gateway spento") -%}
    {%- elif n_bad == 0 -%}{%- set mtext = t("Tutti funzionano") -%}
    {%- elif n_bad == 1 -%}{%- set mtext = t("1 da controllare") -%}
    {%- else -%}{%- set mtext = t("{n} da controllare", n=n_bad) -%}{%- endif %}
    {{ chip(mach_level, mtext) }}
  </a>
  <span class="ov-link {{ 'broken' if not ov.gateway.on }}" aria-hidden="true"><i></i><i></i><i></i></span>
  <div class="ov-station">
    <span class="ov-station-label">{{ t("Gateway") }}</span>
    <span class="ov-station-value">{{ t("Acceso") if ov.gateway.on else t("Spento") }}</span>
    <span class="ov-station-sub">{{ t("{n} risultati oggi", n=ov.today.total) }}</span>
    {{ chip(gw_level, t("Funziona") if ov.gateway.on else t("Fermo")) }}
  </div>
  <span class="ov-link {{ 'broken' if (not ov.gateway.on or dest_level == 'critical') }}" aria-hidden="true"><i></i><i></i><i></i></span>
  <div class="ov-station">
    <span class="ov-station-label">{{ t("Software dello studio") }}</span>
    {% if ov.destinations %}
    <ul class="ov-dest-mini">
      {% for d in ov.destinations %}
      <li class="{{ d.level }}">{{ status_icon(d.level) }}<span><b>{{ d.name }}</b><small>{{ dest_state_text(d) }}</small></span></li>
      {% endfor %}
    </ul>
    <span class="ov-station-sub">{{ t("{n} recapitati oggi", n=ov.today.ok) }}</span>
    {% else %}
    <span class="ov-station-value">—</span>
    {{ chip('warning', t("Non collegato")) }}
    {% endif %}
  </div>
</section>

{# ── 3. Numbers: today (gauge) and the last 7 days ── #}
<section class="ov-numbers">
  <div class="ov-card ov-today">
    <h2>{{ t("Oggi") }}</h2>
    {% set tot = ov.today.total %}
    {% set share = (ov.today.ok / tot) if tot else 0 %}
    {% set C = 2 * 3.14159 * 52 %}
    <div class="ov-today-body">
      <svg class="ov-ring" viewBox="0 0 128 128" role="img"
           aria-label="{{ t('{ok} di {n} risultati recapitati', ok=ov.today.ok, n=tot) }}">
        <circle cx="64" cy="64" r="52" class="track"/>
        {% if tot %}<circle cx="64" cy="64" r="52" class="value {{ 'full' if ov.today.ok == tot }}"
          stroke-dasharray="{{ '%.1f'|format(C * share) }} {{ '%.1f'|format(C) }}" transform="rotate(-90 64 64)"/>{% endif %}
        <text x="64" y="66" class="num">{{ tot }}</text>
        <text x="64" y="88" class="lbl">{{ t("analisi") }}</text>
      </svg>
      <ul class="ov-today-list">
        <li class="ov-today-caption">{{ t("Il cerchio mostra quanti risultati di oggi sono arrivati al software dello studio.") }}</li>
        <li>{{ chip('good', t("{n} recapitati", n=ov.today.ok)) }}</li>
        {% if ov.today.not_ok %}<li>{{ chip('critical', t("{n} non recapitati", n=ov.today.not_ok)) }}</li>{% endif %}
        {% if ov.today.waiting %}<li>{{ chip('warning', t("{n} in attesa di invio", n=ov.today.waiting)) }}</li>{% endif %}
      </ul>
    </div>
  </div>

  <div class="ov-card ov-week">
    <h2>{{ t("Analisi per giorno") }}</h2>
    {% set maxv = (ov.week|map(attribute='total')|max) if ov.week else 0 %}
    {% set maxv = maxv if maxv > 0 else 1 %}
    <div class="ov-bars" role="table" aria-label="{{ t('Analisi per giorno, ultimi 7 giorni') }}">
      {% for d in ov.week %}
      {% set is_today = loop.last %}
      <div class="ov-bar {{ 'today' if is_today }}" role="row" tabindex="0"
           title="{{ d.date|weekday }} {{ d.date[8:10] }}.{{ d.date[5:7] }}.: {{ t('{n} analisi', n=d.total) }}">
        <span class="v" role="cell">{{ d.total }}</span>
        <span class="b" style="height: {{ (d.total / maxv * 100)|round(1) }}%;"></span>
        <span class="d" role="rowheader">{{ t("Oggi") if is_today else (d.date|weekday) }}</span>
      </div>
      {% endfor %}
    </div>
  </div>
</section>

{# ── 4. The machines ── #}
<section class="ov-section">
  <div class="ov-section-head">
    <h2>{{ t("I tuoi apparecchi") }}</h2>
    <a class="btn" href="/analyzers">{{ t("Tutti gli apparecchi") }}</a>
  </div>
  {% if ov.machines %}
  <div class="mc-grid">
    {% for m in ov.machines %}{% include "_machine_card.html" %}{% endfor %}
  </div>
  {% else %}
  <p class="ov-empty">{{ t("Nessun apparecchio è ancora collegato.") }}
    <a href="/analyzers">{{ t("Collega un apparecchio") }}</a></p>
  {% endif %}
</section>

{# ── 5. Where results go ── #}
<section class="ov-section">
  <div class="ov-section-head"><h2>{{ t("Dove vanno i risultati") }}</h2></div>
  {% if ov.destinations %}
  <div class="dc-list">
    {% for d in ov.destinations %}
    <div class="dc {{ d.level }}">
      <div class="dc-name"><strong>{{ d.name }}</strong><span>{{ product_label(d) }}</span></div>
      <div class="dc-stat"><b>{{ d.delivered }}</b><span>{{ t("recapitati oggi") }}</span></div>
      <div class="dc-stat"><b>{{ d.last_ok|when if d.last_ok else "—" }}</b><span>{{ t("ultimo invio") }}</span></div>
      <div class="dc-state">{{ chip(d.level, dest_state_text(d)) }}</div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <p class="ov-empty">{{ t("Nessun software dello studio è collegato.") }}</p>
  {% endif %}
</section>
```

## webui/templates/_machine_card.html
```
{# One analyzer, as the doctor sees it. Expects `m` from webui/overview.py. #}
{% from "_ui.html" import chip, machine_icon, link_label, machine_state_text, machine_hint %}
<article class="mc {{ m.level }}">
  <div class="mc-top">
    <span class="mc-icon">{{ machine_icon() }}</span>
    <div class="mc-title">
      <h3>{{ m.name }}</h3>
      <span>{{ t(m.kind) }}</span>
      <span>{{ link_label(m.link) }}</span>
    </div>
  </div>
  {{ chip(m.level, machine_state_text(m)) }}
  <div class="mc-numbers">
    <div><b>{{ m.today }}</b><span>{{ t("analisi oggi") }}</span></div>
  </div>
  <p class="mc-hint">{{ machine_hint(m) }}</p>
</article>
```

## webui/templates/_ui.html
```
{# Shared UI pieces. Status = colour + icon SHAPE + word, never colour alone
   (docs/UI-DESIGN-ARENA.md). #}

{% macro status_icon(level) -%}
{%- if level == 'good' -%}
<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="currentColor"/><path d="M7 12.5l3.2 3.2L17 9" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
{%- elif level == 'warning' -%}
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 1.8L23 21.5H1z" fill="var(--warn-fill)" stroke="var(--warn)" stroke-width="1.2" stroke-linejoin="round"/><path d="M12 8.5v6" stroke="#17202A" stroke-width="2.6" stroke-linecap="round"/><circle cx="12" cy="18" r="1.5" fill="#17202A"/></svg>
{%- elif level == 'critical' -%}
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.4 1h9.2L23 7.4v9.2L16.6 23H7.4L1 16.6V7.4z" fill="currentColor"/><path d="M8.2 8.2l7.6 7.6M15.8 8.2l-7.6 7.6" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/></svg>
{%- else -%}
<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2.4"/><path d="M9.5 8v8M14.5 8v8" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>
{%- endif -%}
{%- endmacro %}

{% macro chip(level, text) -%}
<span class="chip {{ level }}">{{ status_icon(level) }}{{ text }}</span>
{%- endmacro %}

{# Tube glyph: identifies "a lab machine" without colour coding #}
{% macro machine_icon() -%}
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M9 2.5h6"/><path d="M10 2.5v15a2 2 0 0 0 4 0v-15"/><path d="M10 11h4"/></svg>
{%- endmacro %}

{% macro link_label(link) -%}
{%- if link == 'usb' -%}{{ t("Cavo USB") }}{%- elif link == 'network' -%}{{ t("Cavo di rete") }}{%- elif link == 'folder' -%}{{ t("Cartella condivisa") }}{%- else -%}{{ t("Collegamento da completare") }}{%- endif -%}
{%- endmacro %}

{% macro machine_state_text(m) -%}
{%- if m.state == 'online' -%}{{ t("Collegato") }}
{%- elif m.state == 'idle' -%}{{ t("In attesa di analisi") }}
{%- elif m.state == 'waiting' -%}{{ t("Mai sentito") }}
{%- elif m.state == 'offline' -%}{{ t("Cavo non rilevato") }}
{%- else -%}{{ t("Gateway spento") }}{%- endif -%}
{%- endmacro %}

{% macro machine_hint(m) -%}
{%- if m.state == 'offline' -%}{{ t("Controlla che il cavo USB sia inserito e che l'apparecchio sia acceso.") }}
{%- elif m.state == 'waiting' -%}{{ t("Non ha ancora inviato nessun risultato. Invia un risultato di prova dall'apparecchio.") }}
{%- elif m.last_result -%}{{ t("Ultimo risultato {quando}", quando=m.last_result|when) }}
{%- elif m.last_connect -%}{{ t("Ultimo contatto {quando}", quando=m.last_connect|when) }}
{%- else -%}{{ t("Nessun risultato finora.") }}{%- endif -%}
{%- endmacro %}

{% macro product_label(d) -%}
{%- if d.product == 'folder' -%}{{ t("Cartella condivisa") }}{%- elif d.product == 'software' -%}{{ t("Software dello studio") }}{%- else -%}{{ d.product }}{%- endif -%}
{%- endmacro %}

{% macro dest_state_text(d) -%}
{%- if d.state == 'receiving' -%}{{ t("Riceve i risultati") }}
{%- elif d.state == 'waiting' -%}{{ t("{n} in attesa", n=d.waiting) }}
{%- elif d.state == 'unreachable' -%}{{ t("Non raggiungibile") }}
{%- elif d.state == 'paused' -%}{{ t("Gateway spento") }}
{%- else -%}{{ t("Pronto") }}{%- endif -%}
{%- endmacro %}
```

## webui/static/ui.css
```
/* Doctor-facing pages: Overview, Machines, Check. Tokens live in base.html.
   Design notes: docs/UI-DESIGN-ARENA.md */

/* ── Headline ─────────────────────────────────────────────── */
.ov-head {
  display: grid; grid-template-columns: 64px minmax(0, 1fr) auto; gap: 20px; align-items: center;
  background: var(--surface); border: 1px solid var(--line); border-left-width: 8px;
  border-radius: var(--radius); padding: 24px 28px; margin-bottom: 24px;
}
.ov-head.good     { border-left-color: var(--good); }
.ov-head.warning  { border-left-color: var(--warn-fill); }
.ov-head.critical { border-left-color: var(--crit); }
.ov-head.neutral  { border-left-color: var(--neutral); }
.ov-head-icon svg { width: 64px; height: 64px; display: block; }
.ov-head.good .ov-head-icon { color: var(--good); }
.ov-head.critical .ov-head-icon { color: var(--crit); }
.ov-head.neutral .ov-head-icon { color: var(--neutral); }
.ov-head h1 { font-size: 2.2rem; line-height: 1.15; font-weight: 700; text-wrap: balance; }
.ov-head p { color: var(--ink-2); font-size: 1.1rem; margin-top: 6px; max-width: 70ch; }
.btn-lg { min-height: 56px; padding: 12px 26px; font-size: 1.1rem; }

/* ── The path: machines → gateway → practice software ─────── */
.ov-path {
  display: grid; grid-template-columns: minmax(0,1fr) 72px minmax(0,1fr) 72px minmax(0,1fr);
  align-items: stretch; margin-bottom: 24px;
}
.ov-station {
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 20px 22px; display: flex; flex-direction: column; gap: 8px; align-items: flex-start;
  color: var(--ink); text-decoration: none; min-width: 0;
}
a.ov-station:hover { border-color: var(--brand); color: var(--ink); }
.ov-station-label { color: var(--ink-3); font-size: 0.95rem; }
.ov-station-value { font-size: 1.75rem; font-weight: 700; line-height: 1.15; overflow-wrap: break-word; hyphens: auto; }
.ov-station-sub { color: var(--ink-2); font-size: 0.95rem; }
.ov-station .chip { margin-top: auto; }
.ov-meter { display: flex; gap: 4px; width: 100%; max-width: 220px; }
.ov-meter i { flex: 1; height: 10px; border-radius: 3px; background: var(--neutral-tint); }
.ov-meter i.good { background: var(--good); }
.ov-meter i.warning { background: var(--warn-fill); }
.ov-meter i.critical { background: var(--crit); }
.ov-meter i.neutral { background: var(--line); }

/* the link between two stations: a line; dots travel along it while data flows */
.ov-link { position: relative; align-self: center; height: 8px; margin: 0 16px 0 8px;
  background: var(--brand); border-radius: 4px; }
.ov-link:not(.broken)::after { /* arrow head: results travel left → right */
  content: ""; position: absolute; right: -14px; top: 50%; transform: translateY(-50%);
  border-left: 16px solid var(--brand); border-top: 11px solid transparent; border-bottom: 11px solid transparent; }
.ov-link i { position: absolute; top: 1px; left: -10px; width: 6px; height: 6px; border-radius: 50%;
  background: #fff; opacity: 0; }
.ov-path.flowing .ov-link:not(.broken) i { opacity: 1; animation: ov-flow 1.8s linear infinite; }
.ov-path.flowing .ov-link:not(.broken) i:nth-child(2) { animation-delay: 0.6s; }
.ov-path.flowing .ov-link:not(.broken) i:nth-child(3) { animation-delay: 1.2s; }
@keyframes ov-flow { from { left: -10px; } to { left: calc(100% + 4px); } }
.ov-link.broken { background: repeating-linear-gradient(90deg, var(--crit) 0 10px, transparent 10px 18px); overflow: visible; }
.ov-link.broken::after { /* the break mark */
  content: ""; position: absolute; left: 50%; top: 50%; width: 22px; height: 22px;
  transform: translate(-50%, -50%) rotate(45deg); border-radius: 4px;
  background: var(--crit) linear-gradient(#fff, #fff) center / 12px 3px no-repeat;
}

/* ── Numbers ───────────────────────────────────────────────── */
.ov-numbers { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 24px; margin-bottom: 32px; }
.ov-card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 20px 24px; }
.ov-card h2, .ov-section h2 { font-size: 1.3rem; font-weight: 700; }
.ov-today-body { display: flex; align-items: center; gap: 24px; margin-top: 12px; flex-wrap: wrap; }
.ov-ring { width: 160px; height: 160px; flex: none; }
.ov-ring .track { fill: none; stroke: var(--neutral-tint); stroke-width: 14; }
.ov-ring .value { fill: none; stroke: var(--warn-fill); stroke-width: 14; stroke-linecap: round; }
.ov-ring .value.full { stroke: var(--good); }
.ov-ring .num { font: 700 38px var(--sans); fill: var(--ink); text-anchor: middle; }
.ov-ring .lbl { font: 400 15px var(--sans); fill: var(--ink-3); text-anchor: middle; }
.ov-today-list { list-style: none; display: flex; flex-direction: column; gap: 10px; align-items: flex-start; flex: 1; min-width: 200px; }
.ov-today-caption { color: var(--ink-2); font-size: 0.95rem; max-width: 34ch; }

.ov-bars { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 10px;
  height: 200px; margin-top: 12px; align-items: end; }
.ov-bar { display: grid; grid-template-rows: auto 1fr auto; height: 100%; text-align: center; gap: 6px;
  border-radius: 6px; outline-offset: 2px; }
.ov-bar .v { font-weight: 700; font-size: 1rem; color: var(--ink-2); }
.ov-bar .b { align-self: end; width: 100%; max-width: 56px; justify-self: center; min-height: 3px;
  background: #A9C0D4; border-radius: 4px 4px 0 0; }
.ov-bar.today .b { background: var(--brand); }
.ov-bar.today .v, .ov-bar.today .d { color: var(--ink); font-weight: 700; }
.ov-bar .d { font-size: 0.9rem; color: var(--ink-3); border-top: 1px solid var(--line); padding-top: 6px; }
.ov-bar:hover .b, .ov-bar:focus .b { background: var(--brand-2); }

/* ── Sections ──────────────────────────────────────────────── */
.ov-section { margin-bottom: 32px; }
.ov-section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-bottom: 14px; flex-wrap: wrap; }
.ov-empty { color: var(--ink-2); background: var(--surface); border: 1px dashed var(--line);
  border-radius: var(--radius); padding: 24px; }

/* ── Machine cards ─────────────────────────────────────────── */
.mc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.mc { background: var(--surface); border: 1px solid var(--line); border-top: 6px solid var(--neutral);
  border-radius: var(--radius); padding: 18px 20px; display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
.mc.good { border-top-color: var(--good); }
.mc.warning { border-top-color: var(--warn-fill); }
.mc.critical { border-top-color: var(--crit); }
.mc-top { display: flex; gap: 12px; align-items: flex-start; }
.mc-icon { width: 44px; height: 44px; border-radius: 50%; background: var(--page); color: var(--ink-2);
  display: grid; place-items: center; flex: none; }
.mc-icon svg { width: 26px; height: 26px; }
.mc-title h3 { font-size: 1.2rem; line-height: 1.2; overflow-wrap: break-word; }
.mc-title span { display: block; color: var(--ink-3); font-size: 0.92rem; }
.mc-numbers b { font-size: 1.8rem; line-height: 1; display: block; }
.mc-numbers span { color: var(--ink-3); font-size: 0.92rem; }
.mc-hint { color: var(--ink-2); font-size: 0.95rem; }
.mc-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: auto; }

/* ── Destinations ──────────────────────────────────────────── */
.dc-list { display: flex; flex-direction: column; gap: 12px; }
.dc { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1.3fr) auto; gap: 16px;
  align-items: center; background: var(--surface); border: 1px solid var(--line); border-left: 6px solid var(--neutral);
  border-radius: var(--radius); padding: 16px 20px; }
.dc.good { border-left-color: var(--good); }
.dc.warning { border-left-color: var(--warn-fill); }
.dc.critical { border-left-color: var(--crit); }
.dc-name strong { display: block; font-size: 1.2rem; }
.dc-name span, .dc-stat span { color: var(--ink-3); font-size: 0.92rem; display: block; }
.dc-stat b { font-size: 1.15rem; display: block; }

/* ── Check page ────────────────────────────────────────────── */
.ck-groups { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin-bottom: 24px; }
.ck { background: var(--surface); border: 1px solid var(--line); border-top: 6px solid var(--neutral);
  border-radius: var(--radius); padding: 18px 20px; display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
.ck.good { border-top-color: var(--good); }
.ck.warning { border-top-color: var(--warn-fill); }
.ck.critical { border-top-color: var(--crit); }
.ck h3 { font-size: 1.2rem; }
.ck ul { list-style: none; display: flex; flex-direction: column; gap: 8px; width: 100%; }
.ck li { display: flex; gap: 10px; align-items: flex-start; }
.ck li svg { width: 22px; height: 22px; flex: none; margin-top: 2px; }
.ck li.good svg { color: var(--good); } .ck li.critical svg { color: var(--crit); } .ck li.neutral svg { color: var(--neutral); }
.ck .todo { background: var(--page); border-radius: 8px; padding: 10px 12px; color: var(--ink); width: 100%; }
.ck .todo b { display: block; margin-bottom: 2px; }
.ck-running { display: flex; align-items: center; gap: 14px; color: var(--ink-2); font-size: 1.1rem; padding: 24px 0; }
.ck-spinner { width: 28px; height: 28px; border-radius: 50%; border: 4px solid var(--line); border-top-color: var(--brand);
  animation: ck-spin 0.9s linear infinite; }
@keyframes ck-spin { to { transform: rotate(360deg); } }

/* ── Small screens / tablet ────────────────────────────────── */
/* Headline: the button moves under the sentence before the sentence gets squeezed */
@media (max-width: 1280px) {
  .ov-head { grid-template-columns: 56px minmax(0, 1fr); }
  .ov-head-icon svg { width: 56px; height: 56px; }
  .ov-head-action { grid-column: 2; }
  .ov-head h1 { font-size: 1.9rem; }
}
@media (max-width: 1100px) {
  .ov-numbers { grid-template-columns: 1fr; }
  .dc { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
}
/* The path turns vertical as soon as three stations no longer fit side by side.
   Stations then become one compact row each. */
@media (max-width: 1180px) {
  .ov-path { grid-template-columns: 1fr; max-width: 640px; }
  .ov-station { display: grid; grid-template-columns: minmax(0, 1fr) auto; column-gap: 16px; align-items: center; }
  .ov-station > * { grid-column: 1; }
  .ov-station > .chip { grid-column: 2; grid-row: 1 / span 3; margin: 0; }
  .ov-link { width: 8px; height: 30px; justify-self: center; margin: 2px 0 16px; }
  .ov-link i { display: none; }
  .ov-link:not(.broken)::after { right: auto; left: 50%; top: auto; bottom: -14px; transform: translateX(-50%);
    border-left: 11px solid transparent; border-right: 11px solid transparent; border-top: 16px solid var(--brand); border-bottom: 0; }
}
@media (max-width: 900px) {
  .ov-head { grid-template-columns: 44px minmax(0, 1fr); padding: 18px; gap: 14px; }
  .ov-head-icon svg { width: 44px; height: 44px; }
  .ov-head h1 { font-size: 1.45rem; }
  .ov-head p { font-size: 1rem; }
  .ov-head-action { grid-column: 1 / -1; }
  .ov-head-action .btn { width: 100%; }
  .ov-path { max-width: none; }
}
@media (max-width: 560px) {
  .ov-station { grid-template-columns: 1fr; }
  .ov-station > .chip { grid-column: 1; grid-row: auto; justify-self: start; }
  .ov-bars { gap: 4px; height: 170px; }
  .ov-bar .d { font-size: 0.8rem; }
  .ov-ring { width: 130px; height: 130px; }
  .dc { grid-template-columns: 1fr; gap: 8px; }
  .mc-grid, .ck-groups { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .ov-path.flowing .ov-link i { animation: none; opacity: 0; }
}

/* ── Machines page ─────────────────────────────────────────── */
.az-summary { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
.az-usb-new { background: var(--brand-tint); border-radius: var(--radius); padding: 16px 20px;
  margin-bottom: 20px; display: flex; flex-direction: column; gap: 4px; }
.az-usb-new[hidden] { display: none; }
.mc-add { border-top-color: var(--brand); border-style: dashed; border-top-style: solid; background: transparent; }
.mc-add h3 { font-size: 1.2rem; }
.mc-add ol { padding-left: 1.3em; display: flex; flex-direction: column; gap: 8px; color: var(--ink-2); }
.mc-add ol b { color: var(--ink); }

/* practice software list inside the third station */
.ov-dest-mini { list-style: none; display: flex; flex-direction: column; gap: 10px; width: 100%; }
.ov-dest-mini li { display: flex; gap: 10px; align-items: center; }
.ov-dest-mini svg { width: 28px; height: 28px; flex: none; }
.ov-dest-mini li.good svg { color: var(--good); }
.ov-dest-mini li.critical svg { color: var(--crit); }
.ov-dest-mini li.neutral svg { color: var(--neutral); }
.ov-dest-mini b { display: block; font-size: 1.3rem; line-height: 1.15; overflow-wrap: break-word; hyphens: auto; }
.ov-dest-mini small { display: block; color: var(--ink-2); font-size: 0.92rem; }
```
