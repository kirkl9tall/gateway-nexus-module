(function () {
  var Q = new URLSearchParams(location.hash.slice(1));
  function vis(el) {
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function desc(el) {
    var s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    if (el.className && typeof el.className === 'string') s += '.' + el.className.trim().split(/\s+/).join('.');
    var t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    return s + (t ? ' "' + t + '"' : '');
  }
  function lum(c) {
    var m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    var p = m[1].split(',').map(parseFloat);
    if (p.length > 3 && p[3] === 0) return null;
    var f = p.slice(0, 3).map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
  }
  function bgOf(el) {
    while (el && el.nodeType === 1) {
      var c = getComputedStyle(el).backgroundColor;
      var m = c.match(/rgba?\(([^)]+)\)/);
      if (m) { var p = m[1].split(',').map(parseFloat); if (p.length < 4 || p[3] > 0.5) return c; }
      el = el.parentElement;
    }
    return 'rgb(255,255,255)';
  }
  function run() {
    var fails = [];
    var W = window.innerWidth;
    if (document.documentElement.scrollWidth > W + 1)
      fails.push('HSCROLL page is ' + document.documentElement.scrollWidth + 'px wide in a ' + W + 'px window');
    var roots = Array.prototype.slice.call(document.querySelectorAll('header, aside, nav, main, .main, #ov-live'));
    var all = new Set();
    roots.forEach(function (r) { all.add(r); r.querySelectorAll('*').forEach(function (e) { all.add(e); }); });
    all = Array.prototype.filter.call(Array.from(all), function (e) {
      return !(e.closest('svg') && e.tagName.toLowerCase() !== 'svg') && !e.closest('#cmdk-overlay') && vis(e);
    });
    all.forEach(function (el) {
      var cs = getComputedStyle(el), r = el.getBoundingClientRect();
      // off screen horizontally
      if (cs.position !== 'fixed' || true) {
        if (r.right > W + 1 || r.left < -1) {
          if (!el.closest('[data-scroll-ok]')) fails.push('OFFSCREEN ' + desc(el) + ' [' + Math.round(r.left) + ',' + Math.round(r.right) + ']');
        }
      }
      // clipped
      if (/hidden|clip|auto|scroll/.test(cs.overflowX) && el.scrollWidth > el.clientWidth + 1 && !el.closest('[data-scroll-ok]'))
        fails.push('CLIPPED ' + desc(el) + ' ' + el.scrollWidth + '>' + el.clientWidth);
      // sibling overlap
      var kids = el.tagName.toLowerCase() === 'svg' ? [] : Array.prototype.filter.call(el.children, function (k) {
        if (k.tagName === 'STYLE' || k.tagName === 'SCRIPT') return false;
        if (!vis(k)) return false;
        var p = getComputedStyle(k).position;
        return p !== 'absolute' && p !== 'fixed' && k.getAttribute('aria-hidden') !== 'true';
      });
      for (var i = 0; i < kids.length; i++) for (var j = i + 1; j < kids.length; j++) {
        var a = kids[i].getBoundingClientRect(), b = kids[j].getBoundingClientRect();
        var ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        var oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (ox > 1.5 && oy > 1.5) fails.push('OVERLAP ' + desc(kids[i]) + ' X ' + desc(kids[j]));
      }
      // child escaping parent horizontally (text cut or pushed out of its card)
      var par = el.parentElement;
      if (par && vis(par) && cs.position !== 'absolute' && cs.position !== 'fixed' && getComputedStyle(par).display !== 'contents' && !el.closest('[data-scroll-ok]')) {
        var pr = par.getBoundingClientRect();
        if (r.right > pr.right + 2 || r.left < pr.left - 2) fails.push('ESCAPES ' + desc(el) + ' from ' + desc(par));
      }
      // direct text
      var hasText = Array.prototype.some.call(el.childNodes, function (n) { return n.nodeType === 3 && n.nodeValue.trim(); });
      if (hasText) {
        var fs = parseFloat(cs.fontSize);
        if (fs < 16 && !el.closest('.tech-zone') && !el.closest('.tech-only')) fails.push('SMALLTEXT ' + fs + 'px ' + desc(el));
        var l1 = lum(cs.color), l2 = lum(bgOf(el));
        if (l1 !== null && l2 !== null) {
          var ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
          var large = fs >= 24 || (parseInt(cs.fontWeight, 10) >= 700 && fs >= 18.66);
          if (ratio < (large ? 3 : 4.5) && !el.closest('.tech-zone')) fails.push('CONTRAST ' + ratio.toFixed(2) + ' ' + desc(el) + ' ' + cs.color + ' on ' + bgOf(el));
        }
      }
      // targets
      var tag = el.tagName.toLowerCase();
      if ((tag === 'button' || tag === 'select' || tag === 'summary' || (tag === 'a' && el.getAttribute('href'))) && !el.closest('.tech-zone')) {
        var inline = tag === 'a' && /^(P|SPAN|LI|SMALL)$/.test(el.parentElement.tagName) && cs.display === 'inline';
        if (!inline && (r.height < 44 || r.width < 44)) fails.push('TARGET ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' ' + desc(el));
      }
    });
    // menu reachable: the four doctor links visible on screen, directly or after opening the menu
    var need = ['/', '/analyzers', '/verifica', '/results'];
    var navOk = need.every(function (h) {
      var a = document.querySelector('aside a[href="' + h + '"], nav a[href="' + h + '"]');
      if (!a || !vis(a)) return false;
      var r = a.getBoundingClientRect();
      return r.left >= -1 && r.right <= W + 1 && r.top < window.innerHeight;
    });
    var btn = document.querySelector('[aria-controls="sidebar"]');
    if (!navOk && !(btn && vis(btn))) fails.push('NOMENU doctor links not visible and no menu button');
    if (document.body.dataset.view === 'studio') {
      var txt = document.body.innerText;
      var jm = txt.match(/\b(port|MLLP|HL7|DLQ|P95|uptime)\b/i);
      if (jm) fails.push('JARGON "' + jm[0] + '"');
      document.querySelectorAll('.tech-only').forEach(function (e) { if (vis(e)) fails.push('TECHVISIBLE ' + desc(e)); });
    }
    var uniq = Array.from(new Set(fails));
    var pre = document.createElement('pre'); pre.id = '__chk';
    pre.textContent = JSON.stringify({w: W, navOk: navOk, fails: uniq});
    document.body.appendChild(pre);
    if (window.parent !== window) window.parent.postMessage(pre.textContent, '*');
  }
  window.addEventListener('load', function () {
    if (Q.get('theme') === 'dark') { document.documentElement.setAttribute('data-theme', 'dark'); }
    if (Q.get('menu') === '1') { var b = document.querySelector('[aria-controls="sidebar"]'); if (b) b.click(); }
    setTimeout(run, 800);
  });
})();
