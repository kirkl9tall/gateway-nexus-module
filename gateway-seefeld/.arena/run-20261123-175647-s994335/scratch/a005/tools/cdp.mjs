// node cdp.mjs PORT ROLE LANG SCN WIDTHS(comma) [shotPrefix] [dlq]
import { spawn } from 'node:child_process';
import fs from 'node:fs';
const [PORT, ROLE, LANG, SCN, WIDTHS, SHOT] = process.argv.slice(2);
const dbg = 9300 + Math.floor(Math.random()*500);
const ud = fs.mkdtempSync('/tmp/claude-1000/cdp-');
const ch = spawn('google-chrome', ['--headless=new','--no-sandbox','--disable-gpu','--hide-scrollbars',`--remote-debugging-port=${dbg}`,`--user-data-dir=${ud}`,'about:blank'], {stdio:'ignore'});
const sleep = ms => new Promise(r=>setTimeout(r,ms));
let ws; for (let i=0;i<50;i++){ try { const j = await (await fetch(`http://127.0.0.1:${dbg}/json/list`)).json(); const p=j.find(x=>x.type==='page'); if(p){ ws=p.webSocketDebuggerUrl; break;} } catch(e){} await sleep(200); }
const sock = new WebSocket(ws); await new Promise(r=>sock.onopen=r);
let id=0; const pend={}; sock.onmessage = m => { const d=JSON.parse(m.data); if(d.id&&pend[d.id]){pend[d.id](d.result||d); delete pend[d.id];} };
const send=(method,params={})=>new Promise(r=>{const i=++id; pend[i]=r; sock.send(JSON.stringify({id:i,method,params}));});
await send('Page.enable'); await send('Runtime.enable'); if (process.env.DARK) await send('Emulation.setEmulatedMedia', {features:[{name:'prefers-color-scheme', value:'dark'}]}); if (process.env.RM) await send('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion', value:'reduce'}]});
const measure = fs.readFileSync(new URL('./measure.js', import.meta.url),'utf8').replace(/^setTimeout\(function\(\)\{/, '(function(){').replace(/\}, 2500\);\s*$/, '})();');
for (const w of WIDTHS.split(',').map(Number)) {
  await send('Emulation.setDeviceMetricsOverride', {width:w, height:900, deviceScaleFactor:1, mobile:false});
  await send('Page.navigate', {url:`http://127.0.0.1:${PORT}/__go?role=${ROLE}&lang=${LANG}&scn=${SCN}&next=/`});
  await sleep(3500);
  if (process.env.OPEN) await send('Runtime.evaluate', {expression:"document.querySelectorAll('details').forEach(d=>d.open=true)"}), await sleep(300);
  const r = await send('Runtime.evaluate', {expression: measure + ";document.getElementById('__m').textContent", returnByValue:true});
  let v = (r.result && r.result.value)||JSON.stringify(r); v = v.replace(/^MEASURE/,'').replace(/ENDMEASURE$/,'');
  await send('Runtime.evaluate', {expression:"var m=document.getElementById('__m'); m&&m.remove()"});
  console.log(`${w} ${ROLE} ${LANG} ${SCN} ${v}`);
  if (SHOT) {
    const h = (await send('Runtime.evaluate',{expression:'document.documentElement.scrollHeight',returnByValue:true})).result.value;
    await send('Emulation.setDeviceMetricsOverride', {width:w, height:Math.min(h,4000), deviceScaleFactor:1, mobile:false});
    await sleep(300);
    const s = await send('Page.captureScreenshot', {format:'png'});
    fs.writeFileSync(`${SHOT}-${ROLE}-${LANG}-${SCN}-${w}.png`, Buffer.from(s.data,'base64'));
  }
}
sock.close(); ch.kill(); process.exit(0);
