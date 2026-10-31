'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="demo-token"]').content;
let state = null, busy = false, selected = null;
const blocked = event => ['confirm','sandbox','isolate'].includes(event.decision);
const number = value => value == null ? 'N/A' : Number(value).toFixed(3);
function node(tag, text, className) { const el = document.createElement(tag); el.textContent = text; if(className) el.className = className; return el; }
function details(event) {
  selected = event.event_id;
  $('detail').textContent = JSON.stringify({event: event.event_id, tool: event.tool, server: event.server_id,
    fixture_label: event.malicious ? 'malicious (synthetic)' : 'benign (synthetic)',
    decision: event.decision, forwarded_upstream: event.forwarded, risk: event.risk, trust: event.trust,
    components: event.components, uncertainty: event.uncertainty, model_updates: event.model_updates,
    attestation_verified: event.attestation_verified, novelty: event.novelty,
    response_error: event.response_error, trace_id: event.trace_id, latency_ms: event.latency_ms}, null, 2);
}
function render(data) {
  if (JSON.stringify(data) === JSON.stringify(state)) return;
  state = data;
  $('total').textContent = data.total;
  $('blocked').textContent = data.events.filter(blocked).length;
  $('updates').textContent = data.events.reduce((n,e) => n + e.model_updates, 0);
  $('latency').textContent = data.events.length ? (data.events.reduce((n,e)=>n+e.latency_ms,0)/data.events.length).toFixed(1)+' ms' : '—';
  const chosen = $('scenario').value;
  $('scenario').replaceChildren(...Object.entries(data.scenarios).map(([key,value]) => { const option=node('option',value[0]); option.value=key; return option; }));
  $('scenario').value = chosen;
  $('description').textContent = data.scenarios[chosen][1];
  $('events').replaceChildren(...[...data.events].reverse().map(e => {
    const row=node('tr',''), cell=node('td',''), button=node('button',String(e.event_id).padStart(3,'0')+' / '+e.tool);
    button.addEventListener('click',()=>details(e)); cell.append(button); row.append(cell);
    const decision=node('td',''); decision.append(node('span',e.decision,'pill'+(blocked(e)?' block':''))); row.append(decision);
    for(const value of [number(e.risk),number(e.trust),e.forwarded?'Forwarded':'Not sent']) row.append(node('td',value));
    return row;
  }));
  $('empty').hidden = data.events.length > 0;
  $('retention').textContent = `${data.events.length} retained / ${data.total} calls`;
  $('capabilities').replaceChildren(...data.capabilities.map(c=>{
    const el=node('div',c.tool+' · '+number(c.trust),'cap'); el.append(node('small',c.server));
    const bar=document.createElement('progress'); bar.max=1; bar.value=c.trust; bar.setAttribute('aria-label',c.tool+' trust'); el.append(bar); return el;
  }));
  if (!data.events.length) { selected=null; $('detail').textContent='Select an interaction to inspect its evidence.'; }
  else details(data.events.find(e=>e.event_id===selected) || data.events[data.events.length-1]);
}
async function refresh() {
  if(busy) return;
  try { const response=await fetch('/api/state'); if(response.status===409) return false; if(!response.ok) throw Error('Gateway unavailable'); render(await response.json()); $('connection').textContent='● Local gateway connected'; $('run').disabled=false; $('reset').disabled=false; return true; }
  catch(error) { $('connection').textContent='○ Disconnected · start the dashboard server'; $('run').disabled=true; $('reset').disabled=true; return false; }
}
async function action(path, body) {
  busy=true; $('run').disabled=true; $('reset').disabled=true; $('status').textContent=path.endsWith('reset')?'Restoring enrolled state…':'Sending real calls through the gateway…';
  try {
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Demo-Token':token},body:JSON.stringify(body)});
    const result=await response.json(); if(!response.ok) throw Error(result.error); selected=null; render(result);
    $('status').textContent=path.endsWith('reset')?'Demo reset. Research files were not changed.':'Scenario complete. Inspect actual decisions below.';
  } catch(error) { $('status').textContent=error.message; }
  finally { busy=false; $('run').disabled=false; $('reset').disabled=false; await refresh(); }
}
$('run').addEventListener('click',()=>action('/api/run',{scenario:$('scenario').value}));
$('reset').addEventListener('click',()=>action('/api/reset',{}));
$('scenario').addEventListener('change',()=>{if(state) $('description').textContent=state.scenarios[$('scenario').value][1];});
refresh().then(connected=>{$('status').textContent=connected?'Ready. Choose a scenario to begin.':'Server unavailable. Start the local dashboard command.';});
setInterval(refresh,2000);
