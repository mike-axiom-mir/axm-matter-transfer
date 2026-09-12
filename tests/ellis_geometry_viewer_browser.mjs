import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';

const htmlPath = path.resolve(process.argv[2]);
const evidenceDir = path.resolve(process.argv[3] || 'viewer-evidence');
fs.mkdirSync(evidenceDir, { recursive: true });
const html = fs.readFileSync(htmlPath, 'utf8');

function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }
function reservePort(){
  return new Promise((resolve,reject)=>{
    const server=net.createServer();
    server.once('error',reject);
    server.listen(0,'127.0.0.1',()=>{
      const address=server.address();
      const port=typeof address==='object'&&address ? address.port : 0;
      server.close(error=>error?reject(error):resolve(port));
    });
  });
}

const chrome=process.env.CHROME_BIN || (process.platform==='linux' ? 'chromium' : 'google-chrome');
const userData=fs.mkdtempSync('/tmp/axm-ellis-viewer-');
const debugPort=await reservePort();
const proc=spawn(chrome,[
  '--headless=new',
  '--no-sandbox',
  '--disable-gpu',
  '--disable-dev-shm-usage',
  '--disable-background-networking',
  '--no-first-run',
  '--no-default-browser-check',
  '--hide-scrollbars',
  `--user-data-dir=${userData}`,
  '--remote-debugging-address=127.0.0.1',
  `--remote-debugging-port=${debugPort}`,
  'about:blank'
],{stdio:['ignore','pipe','pipe']});
let stderr='';proc.stderr.on('data',d=>stderr+=d.toString());
let wsUrl='';
for(let i=0;i<100&&!wsUrl;i++){
  if(proc.exitCode!==null) break;
  try{
    const response=await fetch(`http://127.0.0.1:${debugPort}/json/version`,{signal:AbortSignal.timeout(300)});
    if(response.ok){
      const version=await response.json();
      if(typeof version.webSocketDebuggerUrl==='string') wsUrl=version.webSocketDebuggerUrl;
    }
  }catch{}
  if(!wsUrl) await sleep(50);
}
if(!wsUrl){
  try{proc.kill('SIGTERM')}catch{}
  throw new Error(`Chromium DevTools endpoint unavailable on 127.0.0.1:${debugPort}; exit=${proc.exitCode}: ${stderr.slice(-1000)}`);
}
const browserWs=new WebSocket(wsUrl);
await new Promise((resolve,reject)=>{browserWs.addEventListener('open',resolve,{once:true});browserWs.addEventListener('error',reject,{once:true})});
let id=0;const pending=new Map();const pendingS=new Map();let sessionId='';
browserWs.addEventListener('message',ev=>{
  const msg=JSON.parse(ev.data);
  if(msg.sessionId===sessionId&&msg.id&&pendingS.has(msg.id)){const {resolve,reject}=pendingS.get(msg.id);pendingS.delete(msg.id);msg.error?reject(new Error(JSON.stringify(msg.error))):resolve(msg.result);return;}
  if(msg.id&&pending.has(msg.id)){const {resolve,reject}=pending.get(msg.id);pending.delete(msg.id);msg.error?reject(new Error(JSON.stringify(msg.error))):resolve(msg.result);}
});
const send=(method,params={})=>new Promise((resolve,reject)=>{const call=++id;pending.set(call,{resolve,reject});browserWs.send(JSON.stringify({id:call,method,params}))});
const {targetId}=await send('Target.createTarget',{url:'about:blank'});
({sessionId}=await send('Target.attachToTarget',{targetId,flatten:true}));
const sendS=(method,params={})=>new Promise((resolve,reject)=>{const call=++id;pendingS.set(call,{resolve,reject});browserWs.send(JSON.stringify({id:call,method,params,sessionId}))});
await sendS('Runtime.enable');await sendS('Page.enable');await sendS('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
const tree=await sendS('Page.getFrameTree');
await sendS('Page.setDocumentContent',{frameId:tree.frameTree.frame.id,html});
await sleep(250);
async function evalv(expression){const r=await sendS('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value}
const start=await evalv(`({schema:window.__AXM_VIEWER__?.schema,index:window.__AXM_VIEWER__?.selectedIndex,heading:document.querySelector('#sample-heading')?.textContent,overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth})`);
if(start.schema!=='axm.matter-transfer.ellis-geometry-viewer/v1') throw new Error(`viewer schema missing: ${JSON.stringify(start)}`);
if(start.overflow) throw new Error('desktop horizontal overflow');
await evalv(`document.querySelector('#next').click()`);await sleep(80);
const after=await evalv(`({index:window.__AXM_VIEWER__.selectedIndex,heading:document.querySelector('#sample-heading').textContent,meaning:document.querySelector('#meaning').textContent,live:document.querySelector('#announce').textContent})`);
if(after.index===start.index) throw new Error('next sample did not change selected receipt sample');
if(!after.meaning.includes('Negative radial NEC')) throw new Error(`NEC meaning missing: ${JSON.stringify(after)}`);
if(!after.live.includes('Selected sample')) throw new Error(`accessible live feedback missing: ${JSON.stringify(after)}`);
const shot=await sendS('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(evidenceDir,'ellis-geometry-desktop.png'),Buffer.from(shot.data,'base64'));
await sendS('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await sleep(120);
const mobile=await evalv(`({overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,width:document.documentElement.clientWidth,truth:document.querySelector('.truth strong').textContent})`);
if(mobile.overflow) throw new Error('mobile horizontal overflow');
const shotM=await sendS('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(evidenceDir,'ellis-geometry-mobile.png'),Buffer.from(shotM.data,'base64'));
console.log(JSON.stringify({status:'PASS',start,after,mobile,evidenceDir},null,2));
try{browserWs.close()}catch{};
try{proc.kill('SIGTERM')}catch{}
