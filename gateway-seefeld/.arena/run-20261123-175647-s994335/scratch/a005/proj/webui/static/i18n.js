/*
 * i18n.js: client side of the Web UI translations.
 *
 * The server renders every page already translated (webui/i18n.py, the
 * {{ t("…") }} calls in the templates). This file only:
 *
 *   1. provides T("testo italiano", {n: 3}) for text built in JavaScript,
 *      reading the catalog loaded from /i18n/<lang>.js (window.I18N);
 *   2. switches language through /lang/<code>, which stores a cookie, so the
 *      choice holds on every page and after a new login;
 *   3. as a TEMPORARY fallback, rewrites exact Italian text on pages that are
 *      not converted to t() yet. Remove once every page uses t()/T().
 */
(function () {
  "use strict";

  var DICT = window.I18N || {};
  var LANG = window.I18N_LANG || document.documentElement.getAttribute("lang") || "it";

  function fmt(s, vals) {
    if (!vals) return s;
    return s.replace(/\{(\w+)\}/g, function (m, k) {
      return Object.prototype.hasOwnProperty.call(vals, k) ? String(vals[k]) : m;
    });
  }

  // T("Funziona. {n} messaggi da rispedire.", {n: 4})
  window.T = function (text, vals) {
    var out = (LANG !== "it" && DICT[text]) ? DICT[text] : text;
    return fmt(out, vals);
  };
  window.I18N_LOCALE = window.I18N_LOCALE || "it-CH";

  window.setLang = function (lang) {
    var next = window.location.pathname + window.location.search + window.location.hash;
    window.location.href = "/lang/" + encodeURIComponent(lang) + "?next=" + encodeURIComponent(next);
  };

  // ── Legacy fallback for pages not yet converted ────────────────────────
  if (LANG === "it") return;

  function tr(txt) {
    if (!txt) return null;
    var key = txt.trim();
    if (!key || !Object.prototype.hasOwnProperty.call(DICT, key)) return null;
    var out = txt.replace(key, DICT[key]);
    return out === txt ? null : out;   // identical translation: nothing to do
  }

  function walk(root) {
    if (root.nodeType === 3) {
      var r0 = tr(root.nodeValue);
      if (r0 !== null) root.nodeValue = r0;
      return;
    }
    var it = document.createNodeIterator(root, NodeFilter.SHOW_TEXT);
    var n;
    while ((n = it.nextNode())) {
      var p = n.parentNode;
      if (!p || p.nodeName === "SCRIPT" || p.nodeName === "STYLE") continue;
      var r = tr(n.nodeValue);
      if (r !== null) n.nodeValue = r;
    }
    var els = root.querySelectorAll ? root.querySelectorAll("[placeholder],[title]") : [];
    for (var i = 0; i < els.length; i++) {
      ["placeholder", "title"].forEach(function (a) {
        if (!els[i].hasAttribute(a)) return;
        var v = tr(els[i].getAttribute(a));
        if (v !== null) els[i].setAttribute(a, v);
      });
    }
  }

  // The observer is switched off while we translate, so our own edits never
  // trigger it again. (Without this, a translation equal to its source, e.g.
  // "Gateway" -> "Gateway", re-triggered itself forever and froze the tab.)
  var OPTS = { childList: true, subtree: true, characterData: true };
  var observer = new MutationObserver(function (muts) {
    observer.disconnect();
    try {
      muts.forEach(function (m) {
        if (m.type === "characterData") { walk(m.target); return; }
        m.addedNodes.forEach(function (node) {
          if (node.nodeType === 1 || node.nodeType === 3) walk(node);
        });
      });
    } finally {
      observer.observe(document.body, OPTS);
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    walk(document.body);
    observer.observe(document.body, OPTS);
  });
})();
