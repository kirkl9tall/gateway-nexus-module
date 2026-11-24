setTimeout(function () {
  var out = [];
  var W = window.innerWidth;
  if (document.documentElement.scrollWidth > W + 1) out.push('HSCROLL ' + document.documentElement.scrollWidth + '>' + W);
  function vis(el) { var r = el.getBoundingClientRect(); var cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; }
  function leaves(root) {
    var els = Array.prototype.slice.call(root.querySelectorAll('*')).filter(function (el) {
      if (!vis(el) || el.closest('svg') && el.tagName.toLowerCase() !== 'svg') return false;
      if (['IMG', 'SELECT', 'BUTTON', 'svg'].indexOf(el.tagName) >= 0) return true;
      for (var i = 0; i < el.childNodes.length; i++) { var n = el.childNodes[i]; if (n.nodeType === 3 && n.nodeValue.trim()) return true; }
      return false;
    });
    return els;
  }
  function name(el) { return el.tagName + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').join('.') : '') + '"' + (el.textContent || '').trim().slice(0, 20) + '"'; }
  // text boxes overlapping each other
  ['header', '.sidebar', '#ov-live'].forEach(function (sel) {
    var root = document.querySelector(sel); if (!root) return;
    var ls = leaves(root);
    for (var i = 0; i < ls.length; i++) for (var j = i + 1; j < ls.length; j++) {
      var a = ls[i], b = ls[j]; if (a.contains(b) || b.contains(a)) continue;
      var r1 = a.getBoundingClientRect(), r2 = b.getBoundingClientRect();
      var ix = Math.min(r1.right, r2.right) - Math.max(r1.left, r2.left), iy = Math.min(r1.bottom, r2.bottom) - Math.max(r1.top, r2.top);
      if (ix > 2 && iy > 2) out.push('OVERLAP ' + name(a) + ' x ' + name(b));
    }
    // out of viewport / clipped text
    ls.forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.right > W + 1 || r.left < -1) out.push('OUTSIDE ' + name(el) + ' ' + Math.round(r.left) + '-' + Math.round(r.right));
      if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0 && getComputedStyle(el).overflowX !== 'visible') out.push('CLIPPED ' + name(el));
    });
  });
  // small targets
  Array.prototype.slice.call(document.querySelectorAll('header a, header button, header select, .sidebar a, .sidebar summary, #ov-live a, #ov-live button')).forEach(function (el) {
    if (!vis(el)) return; var r = el.getBoundingClientRect();
    if (r.height < 43.5 && !el.closest('p')) out.push('SMALL ' + name(el) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  });
  var pre = document.createElement('pre'); pre.id = 'chk'; pre.textContent = 'CHK[' + W + '] ' + (out.length ? out.join(' || ') : 'OK'); document.body.appendChild(pre);
  document.title = pre.textContent; if (window.parent !== window) window.parent.postMessage(pre.textContent, '*');
}, 2500);
