setTimeout(function(){
  var W = document.documentElement.clientWidth, out = {w: W, iw: window.innerWidth, sw: document.documentElement.scrollWidth, off: [], overlap: [], clipped: []};
  document.querySelectorAll('body *').forEach(function(el){
    var r = el.getBoundingClientRect(); if (!r.width || !r.height) return;
    var cs = getComputedStyle(el); if (cs.visibility==='hidden') return;
    if (r.right > W + 1 || r.left < -1) {
      // ignore if an ancestor clips with overflow
      var p = el.parentElement, clipped = false;
      while (p && p !== document.body) { var o = getComputedStyle(p).overflowX; if (o==='auto'||o==='hidden'||o==='scroll') { clipped = (typeof p.className==='string'?p.className:'')||p.tagName; break;} p = p.parentElement; }
      if (!clipped) out.off.push((el.id||(typeof el.className==='string'?el.className:'svg')||el.tagName).toString().slice(0,40) + ' r=' + Math.round(r.right));
      else out.clipped.push((el.id||(typeof el.className==='string'?el.className:'svg')||el.tagName).toString().slice(0,30) + ' in ' + clipped.toString().slice(0,20));
    }
    if (el.scrollWidth > el.clientWidth + 1 && ['visible'].indexOf(cs.overflowX)>=0 && el.clientWidth>0 && !/svg|path|circle|text/i.test(el.tagName)) out.clipped.push('OVERFLOWING ' + (el.id||(typeof el.className==='string'?el.className:'svg')||el.tagName).toString().slice(0,30) + ' ' + el.scrollWidth + '>' + el.clientWidth);
  });
  var hdr = document.querySelector('header'); 
  if (hdr) { var kids = Array.from(hdr.querySelectorAll('*')).filter(function(e){var r=e.getBoundingClientRect(); return r.width>0 && e.children.length===0;});
    for (var i=0;i<kids.length;i++) for (var j=i+1;j<kids.length;j++){ var a=kids[i].getBoundingClientRect(), b=kids[j].getBoundingClientRect();
      if (kids[i].contains(kids[j])||kids[j].contains(kids[i])) continue;
      var ox = Math.min(a.right,b.right)-Math.max(a.left,b.left), oy=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
      if (ox>2&&oy>2) out.overlap.push((kids[i].id||(typeof kids[i].className==='string'?kids[i].className:'svg:'+kids[i].parentElement.className)||kids[i].tagName)+' x '+(kids[j].id||(typeof kids[j].className==='string'?kids[j].className:'svg:'+kids[j].parentElement.className)||kids[j].tagName)); } }
  out.hdrH = hdr ? Math.round(hdr.getBoundingClientRect().height) : 0;
  parent.postMessage(JSON.stringify(out), '*');
}, 800);
