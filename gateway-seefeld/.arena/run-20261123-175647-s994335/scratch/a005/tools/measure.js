setTimeout(function(){
  var W = document.documentElement.clientWidth, out = {w: W, docW: document.documentElement.scrollWidth, overlaps: [], offscreen: [], clipped: []};
  function vis(e){ var r=e.getBoundingClientRect(); var cs=getComputedStyle(e); return r.width>0 && r.height>0 && cs.visibility!=='hidden' && cs.display!=='none'; }
  function name(e){ return e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(e.className&&typeof e.className==='string'?'.'+e.className.trim().split(/\s+/).join('.'):''); }
  function inter(a,b){ var x=Math.min(a.right,b.right)-Math.max(a.left,b.left), y=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top); return (x>1&&y>1)?Math.round(x)+'x'+Math.round(y):null; }
  // header: every visible leaf-ish item vs every other
  var hdr = document.querySelector('header'); 
  if (hdr) {
    var items = Array.prototype.filter.call(hdr.querySelectorAll('a, select, button, img, span, strong, b'), vis).filter(function(e){ return !e.querySelector('a,select,button,img,span,strong,b'); });
    for (var i=0;i<items.length;i++) for (var j=i+1;j<items.length;j++){ if (items[i].contains(items[j])||items[j].contains(items[i])) continue; var o=inter(items[i].getBoundingClientRect(), items[j].getBoundingClientRect()); if(o) out.overlaps.push(name(items[i])+' X '+name(items[j])+' '+o); }
    var hr = hdr.getBoundingClientRect(); out.hdrH = Math.round(hr.height);
  }
  function inScroller(e){ for (var p=e.parentElement;p;p=p.parentElement){ var cs=getComputedStyle(p); if(/(auto|scroll)/.test(cs.overflowX) && p.scrollWidth>p.clientWidth) return true; } return false; }
  Array.prototype.forEach.call(document.body.querySelectorAll('*'), function(e){
    if (!vis(e) || e.closest('#__m') || e.closest('details:not([open]) > :not(summary)')) return;
    var r=e.getBoundingClientRect();
    if ((r.right>W+1 || r.left< -1) && !inScroller(e) && getComputedStyle(e).position!=='fixed') out.offscreen.push(name(e)+' ['+Math.round(r.left)+','+Math.round(r.right)+']');
    var cs=getComputedStyle(e);
    if (e.children.length===0 && e.textContent.trim() && e.scrollWidth>e.clientWidth+1 && cs.overflowX!=='visible' && e.clientWidth>0) out.clipped.push(name(e)+' "'+e.textContent.trim().slice(0,30)+'"');
  });
  out.offscreen = out.offscreen.slice(0,15); out.clipped = out.clipped.slice(0,15);
  // tap targets < 44px among visible links/buttons/selects
  out.small = Array.prototype.filter.call(document.querySelectorAll('a,button,select,summary'), vis).filter(function(e){ var r=e.getBoundingClientRect(); return (r.height<44) && !e.closest('#__m') && !e.closest('details:not([open]) > :not(summary)'); }).map(function(e){ var r=e.getBoundingClientRect(); return name(e)+' '+Math.round(r.width)+'x'+Math.round(r.height)+' "'+e.textContent.trim().slice(0,20)+'"'; }).slice(0,15);
  var pre=document.createElement('pre'); pre.id='__m'; pre.textContent='MEASURE'+JSON.stringify(out)+'ENDMEASURE'; document.body.appendChild(pre);
}, 2500);
