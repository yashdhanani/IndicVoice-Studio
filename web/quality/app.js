/* IndicVoice Quality Console — vanilla JS, no dependencies.
   All evidence comes from the local task server on 8010; nothing is fabricated. */
(() => {
"use strict";
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const LANGS = ["hi","gu","mr","bn","ta","te","kn","ml","pa","or","as","en"];
const NAMES = {hi:"Hindi",gu:"Gujarati",mr:"Marathi",bn:"Bengali",ta:"Tamil",te:"Telugu",
  kn:"Kannada",ml:"Malayalam",pa:"Punjabi",or:"Odia",as:"Assamese",en:"English"};
const DIM_Q = {
  pronunciation:["Is the pronunciation correct?","native phonemes, names, numbers"],
  intelligibility:["Is the speech easy to understand?","effort needed to follow the words"],
  naturalness:["Does the speech sound natural?","human-like vs machine-like"],
  prosody:["Is the language fluent?","natural pitch and stress flow"],
  rhythm:["Is the rhythm natural?","syllable timing, not mechanical"],
  pauses:["Are the pauses appropriate?","phrase boundaries, breath-like gaps"],
  sentence_endings:["Do sentence endings sound correct?","falling statements, continuing clauses"],
  question_intonation:["Do questions sound like questions?","judge relative to the sentence type"],
  conversational_feel:["Conversational, not robotic?","spoken register vs reading a document"],
  overall:["Overall listening comfort","would you keep talking with this voice?"],
};
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = (v,d=3) => v==null ? "—" : Number(v).toFixed(d);
const pct = v => v==null ? "—" : Math.round(v*100)+"%";

const S = {
  route:"overview", overview:null, languages:null, runs:[], run:null, runName:null,
  dataset:null, listening:null, pkg:null, pkgId:"v2", pkgList:[],
  ratings:{}, feedback:{}, listener:"", sampleIdx:0,
  jobs:[], reports:[], report:null, baseline:null, resources:null,
  gates:{cer:0.15,rms:-35,voiced:0.30,band:0.70,clip:0.002,dur:0.4},
  filters:{lang:"",sort:"default",q:"",defects:false,density:false},
  sel:new Set(), order:[], dsOrder:[], views:[],
  muted:false, vol:0.9, rate:1, playingKey:null, queue:[], queueTimer:null,
  benchLangs:new Set(LANGS), jobTimer:null, lastDeletedView:null,
};

/* ---------------- audio: one gain bus, master mute ---------------- */
let AC=null, busGain=null, playerEl=$("#player"), playerSrc=null;
function audioBus(){
  if(!AC){
    AC = new (window.AudioContext||window.webkitAudioContext)();
    busGain = AC.createGain(); busGain.gain.value = S.muted?0:S.vol;
    busGain.connect(AC.destination);
    playerSrc = AC.createMediaElementSource(playerEl);
    playerSrc.connect(busGain);
  }
  if(AC.state==="suspended") AC.resume();
  return AC;
}
function tick(freq=660,dur=0.06,type="sine",vol=0.12){
  if(S.muted) return;
  try{
    const ctx=audioBus(); const o=ctx.createOscillator(), g=ctx.createGain();
    o.type=type; o.frequency.value=freq;
    g.gain.setValueAtTime(vol,ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.0001,ctx.currentTime+dur);
    o.connect(g); g.connect(busGain); o.start(); o.stop(ctx.currentTime+dur+0.02);
  }catch(e){/* audio unavailable */}
}
const sndOk=()=>{tick(740,.07);setTimeout(()=>tick(988,.09),70);};
const sndErr=()=>tick(196,.16,"square",0.08);
const sndClick=()=>tick(520,.035,"triangle",0.06);
function applyAudio(){
  if(busGain) busGain.gain.value = S.muted?0:S.vol;
  playerEl.playbackRate = S.rate;
  const b=$("#masterMute");
  b.setAttribute("aria-pressed",String(S.muted));
  b.querySelector(".mute-ico").textContent = S.muted?"🔇":"🔊";
  b.querySelector(".mute-label").textContent = S.muted?"Muted":"Sound on";
}
function stopPlayback(){
  playerEl.pause(); S.playingKey=null;
  clearTimeout(S.queueTimer); S.queue=[];
  $$(".rowplay.playing").forEach(b=>{b.classList.remove("playing");b.textContent="▶";});
}
function playUrl(url,key,btn){
  audioBus();
  if(S.playingKey===key && !playerEl.paused){ stopPlayback(); return; }
  stopPlayback();
  playerEl.src=url; playerEl.playbackRate=S.rate;
  S.playingKey=key;
  if(btn){btn.classList.add("playing");btn.textContent="❚❚";}
  playerEl.play().catch(()=>toast("Audio could not be played","err"));
}
playerEl.addEventListener("ended",()=>{
  const btn=$(`.rowplay[data-key="${CSS.escape(S.playingKey||"")}"]`);
  if(btn){btn.classList.remove("playing");btn.textContent="▶";}
  S.playingKey=null;
  if(S.queue.length){ const next=S.queue.shift();
    S.queueTimer=setTimeout(()=>playUrl(next.url,next.key,next.btn),220); }
});
function playQueue(items){
  if(!items.length) return;
  stopPlayback(); S.queue=items.slice(1);
  playUrl(items[0].url,items[0].key,items[0].btn);
}

/* ---------------- toasts / undo ---------------- */
function toast(msg,kind="info",action){
  const t=document.createElement("div");
  t.className="toast "+kind;
  t.innerHTML=`<span>${esc(msg)}</span>`;
  if(action){
    const b=document.createElement("button"); b.textContent=action.label;
    b.onclick=()=>{t.remove();action.fn();};
    t.appendChild(b);
  }
  $("#toasts").appendChild(t);
  setTimeout(()=>{t.style.opacity="0";t.style.transition="opacity .4s";
    setTimeout(()=>t.remove(),420);}, action?8000:4200);
}

/* ---------------- api ---------------- */
async function api(path,opts){
  const r=await fetch(path,opts);
  if(!r.ok){
    let detail=r.statusText;
    try{const j=await r.json();detail=j.detail||JSON.stringify(j);}catch(e){}
    throw new Error(detail);
  }
  return r.json();
}
const post=(p,body)=>api(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})});

/* ---------------- gate what-if ---------------- */
function rowStatus(row,g){
  const s=row.signal||{};
  const fails=[];
  if((s.duration_s??0)<g.dur) fails.push("short");
  if((s.rms_dbfs??-99)<g.rms) fails.push("quiet");
  if((s.voiced_frac??0)<g.voiced) fails.push("unvoiced");
  if((s.voice_band_ratio??0)<g.band) fails.push("band");
  if((s.clip_frac??1)>g.clip) fails.push("clipped");
  if(fails.length) return {status:"FAIL",fails};
  if(!row.script_ok) return {status:"PARTIAL",fails:["script"]};
  if((row.cer_clean??1)>g.cer || (row.wer_clean??1)>0.30) return {status:"PARTIAL",fails:["words"]};
  return {status:"PASS (automated)",fails:[]};
}
function langStatus(rows,g){
  let worst="PASS (automated)";
  for(const r of rows){
    const st=rowStatus(r,g).status;
    if(st==="FAIL") return "FAIL";
    if(st==="PARTIAL") worst="PARTIAL";
  }
  return worst;
}
function badge(st){
  if(!st) return `<span class="badge b-nt">NOT TESTED</span>`;
  if(st.startsWith("PASS")) return `<span class="badge b-pass">${esc(st)}</span>`;
  if(st==="PARTIAL") return `<span class="badge b-partial">PARTIAL</span>`;
  if(st==="FAIL") return `<span class="badge b-fail">FAIL</span>`;
  if(st==="NOT APPLICABLE") return `<span class="badge b-na">N/A</span>`;
  return `<span class="badge b-nt">${esc(st)}</span>`;
}
function runRows(){
  if(!S.run) return [];
  const out=[];
  for(const l of S.run.languages) for(const r of l.rows) out.push({...r,lang:l.lang});
  return out;
}
function visibleRows(){
  let rows=runRows();
  const g=S.gates,f=S.filters;
  if(f.lang) rows=rows.filter(r=>r.lang===f.lang);
  if(f.q){const q=f.q.toLowerCase();
    rows=rows.filter(r=>(r.reference+r.hypothesis+r.lang+(r.notes||[]).join(" ")).toLowerCase().includes(q));}
  rows=rows.map(r=>({...r,_g:rowStatus(r,g)}));
  if(f.defects) rows=rows.filter(r=>r._g.status!=="PASS (automated)");
  const rank={"FAIL":0,"PARTIAL":1,"PASS (automated)":2};
  if(f.sort==="cer") rows.sort((a,b)=>(b.cer_clean??0)-(a.cer_clean??0));
  else if(f.sort==="status") rows.sort((a,b)=>rank[a._g.status]-rank[b._g.status]||(b.cer_clean??0)-(a.cer_clean??0));
  else if(f.sort==="lang") rows.sort((a,b)=>a.lang.localeCompare(b.lang)||a.sentence-b.sentence||a.take-b.take);
  else if(f.sort==="custom"&&S.order.length){
    const idx=new Map(S.order.map((k,i)=>[k,i]));
    rows.sort((a,b)=>(idx.get(rowKey(a))??1e9)-(idx.get(rowKey(b))??1e9));
  }
  return rows;
}
const rowKey=r=>`${r.lang}_${String(r.sentence).padStart(2,"0")}_r${r.take}`;

/* ---------------- markdown ---------------- */
function md(src){
  const lines=String(src||"").split("\n"); let html="",i=0,inCode=false,code=[];
  const inline=t=>esc(t).replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/`([^`]+)`/g,"<code>$1</code>");
  while(i<lines.length){
    const L=lines[i];
    if(L.startsWith("```")){
      if(inCode){html+="<pre>"+esc(code.join("\n"))+"</pre>";code=[];inCode=false;}
      else inCode=true;
      i++;continue;
    }
    if(inCode){code.push(L);i++;continue;}
    if(/^\s*\|/.test(L)&&i+1<lines.length&&/^\s*\|[\s:|-]+\|?\s*$/.test(lines[i+1])){
      const cells=r=>r.trim().replace(/^\||\|$/g,"").split("|").map(c=>c.trim());
      const head=cells(L); i+=2; let body=[];
      while(i<lines.length&&/^\s*\|/.test(lines[i])){body.push(cells(lines[i]));i++;}
      html+="<table><thead><tr>"+head.map(h=>`<th>${inline(h)}</th>`).join("")+"</tr></thead><tbody>"
        +body.map(r=>"<tr>"+r.map(c=>`<td>${inline(c)}</td>`).join("")+"</tr>").join("")+"</tbody></table>";
      continue;
    }
    if(/^###\s/.test(L)) html+="<h3>"+inline(L.slice(4))+"</h3>";
    else if(/^##\s/.test(L)) html+="<h2>"+inline(L.slice(3))+"</h2>";
    else if(/^#\s/.test(L)) html+="<h1>"+inline(L.slice(2))+"</h1>";
    else if(/^[-*]\s/.test(L)){
      let items=[];
      while(i<lines.length&&/^[-*]\s/.test(lines[i])){items.push("<li>"+inline(lines[i].slice(2))+"</li>");i++;}
      html+="<ul>"+items.join("")+"</ul>";continue;
    }
    else if(/^\d+\.\s/.test(L)){
      let items=[];
      while(i<lines.length&&/^\d+\.\s/.test(lines[i])){items.push("<li>"+inline(lines[i].replace(/^\d+\.\s/,""))+"</li>");i++;}
      html+="<ol>"+items.join("")+"</ol>";continue;
    }
    else if(/^>\s?/.test(L)) html+="<blockquote>"+inline(L.replace(/^>\s?/,""))+"</blockquote>";
    else if(/^---+\s*$/.test(L)) html+="<hr>";
    else if(L.trim()) html+="<p>"+inline(L)+"</p>";
    i++;
  }
  if(inCode) html+="<pre>"+esc(code.join("\n"))+"</pre>";
  return html;
}

/* ---------------- charts ---------------- */
function barChart(items){
  const W=720,H=210,pad=34,bw=(W-pad*2)/items.length;
  const hues=["#ff9d2e","#ff4d8d","#17c3b2","#7b8cff","#4cc9f0","#3ddc84","#ffc857","#ff5470","#e07b0a","#9d6bff","#2ee6a8","#f06292"];
  let bars="",labels="";
  items.forEach((it,i)=>{
    const h=Math.max(2,(H-58)*it.value), x=pad+i*bw+bw*0.16, y=H-30-h, w=bw*0.68;
    bars+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" rx="4" fill="${hues[i%hues.length]}" opacity="0.92"><title>${esc(it.label)}: ${esc(it.text)}</title></rect>`;
    bars+=`<text x="${(x+w/2).toFixed(1)}" y="${(y-5).toFixed(1)}" text-anchor="middle" font-size="10.5" fill="#f5ecdf">${esc(it.text)}</text>`;
    labels+=`<text x="${(x+w/2).toFixed(1)}" y="${H-12}" text-anchor="middle" font-size="11" fill="#b3a4c9">${esc(it.label)}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Clean render rate per language">
    <line x1="${pad}" y1="${H-30}" x2="${W-pad}" y2="${H-30}" stroke="#3d2f52"/>
    ${bars}${labels}</svg>`;
}
function donut(counts){
  const total=Object.values(counts).reduce((a,b)=>a+b,0)||1;
  const colors={"PASS (automated)":"#3ddc84","PARTIAL":"#ffc857","FAIL":"#ff5470","NOT TESTED":"#8f86a8"};
  let a0=-Math.PI/2,paths="";
  for(const [k,v] of Object.entries(counts)){
    if(!v) continue;
    const a1=a0+2*Math.PI*v/total, large=(a1-a0)>Math.PI?1:0;
    const x0=80+62*Math.cos(a0),y0=80+62*Math.sin(a0),x1=80+62*Math.cos(a1),y1=80+62*Math.sin(a1);
    paths+=`<path d="M80 80 L${x0.toFixed(1)} ${y0.toFixed(1)} A62 62 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)} Z" fill="${colors[k]||"#7b8cff"}" opacity="0.9"><title>${esc(k)}: ${v}</title></path>`;
    a0=a1;
  }
  const legend=Object.entries(counts).map(([k,v])=>
    `<span><i style="background:${colors[k]||"#7b8cff"}"></i>${esc(k)} · ${v}</span>`).join("");
  return `<svg viewBox="0 0 160 160" style="max-width:170px;margin:0 auto" role="img" aria-label="Status distribution">
    ${paths}<circle cx="80" cy="80" r="38" fill="#1d1428"/>
    <text x="80" y="76" text-anchor="middle" font-size="22" font-weight="800" fill="#f5ecdf">${total}</text>
    <text x="80" y="94" text-anchor="middle" font-size="9.5" fill="#b3a4c9">languages</text></svg>
    <div class="legend">${legend}</div>`;
}

/* ---------------- drawer / modal ---------------- */
function openDrawer(title,html){
  $("#drawerTitle").textContent=title;
  $("#drawerBody").innerHTML=html;
  $("#drawer").hidden=false; $("#drawerScrim").hidden=false;
}
function closeDrawer(){ $("#drawer").hidden=true; $("#drawerScrim").hidden=true; }
function openModal(html){ $("#modalBox").innerHTML=html; $("#modalScrim").hidden=false; }
function closeModal(){ $("#modalScrim").hidden=true; stopRecorder(); }

/* ---------------- data loaders ---------------- */
async function loadOverview(){ S.overview=await api("/api/overview"); }
async function loadLanguages(){ S.languages=await api("/api/languages"); }
async function loadRuns(){ S.runs=(await api("/api/runs")).runs;
  if(!S.runName&&S.runs.length){
    const full=S.runs.filter(r=>Object.keys(r.statuses||{}).length===12);
    S.runName=(full.length?full:S.runs)[(full.length?full:S.runs).length-1].run;
  }
  if(S.runName) S.run=await api("/api/runs/"+encodeURIComponent(S.runName));
}
async function loadDataset(){ S.dataset=await api("/api/dataset"); }
async function loadListening(){
  S.listening=await api("/api/listening"); S.pkgList=S.listening.packages;
  if(!S.pkgList.find(p=>p.id===S.pkgId)&&S.pkgList.length) S.pkgId=S.pkgList[S.pkgList.length-1].id;
  if(S.pkgList.length) S.pkg=await api(`/api/listening/${S.pkgId}/package`);
}
async function loadJobs(){ S.jobs=(await api("/api/jobs")).jobs; }
async function loadReports(){ S.reports=(await api("/api/reports")).reports; }
async function loadBaseline(){ S.baseline=await api("/api/baseline"); }
async function loadResources(){ S.resources=await api("/api/resources"); }

/* ---------------- views ---------------- */
function vOverview(){
  const o=S.overview; if(!o) return `<div class="empty"><span class="spinner"></span>Loading evidence…</div>`;
  const g=S.gates;
  const rows=runRows();
  const perLang=LANGS.map(lang=>{
    const lr=rows.filter(r=>r.lang===lang);
    const st=lr.length?langStatus(lr,g):"NOT TESTED";
    const clean=lr.filter(r=>rowStatus(r,g).status==="PASS (automated)").length;
    const m=o.matrix.find(x=>x.lang===lang)||{};
    return {lang,st,clean,n:lr.length,m};
  });
  const counts={"PASS (automated)":0,"PARTIAL":0,"FAIL":0,"NOT TESTED":0};
  perLang.forEach(p=>counts[p.st]=(counts[p.st]||0)+1);
  const totalRenders=rows.length, cleanRenders=rows.filter(r=>rowStatus(r,g).status==="PASS (automated)").length;
  const worst=rows.map(r=>({...r,_g:rowStatus(r,g)}))
    .filter(r=>r._g.status!=="PASS (automated)")
    .sort((a,b)=>(b.cer_clean??0)-(a.cer_clean??0)).slice(0,4);
  const ds=o.dataset, ls=o.listening;
  return `
  <h1 class="page">Speech quality, <em>measured — never assumed</em></h1>
  <p class="page-sub">Twelve Indian languages, one CPU-only pipeline. Every number below comes from a local
  render→recognise round-trip or a real file on disk. Human naturalness stays <b>NOT TESTED</b> until native listeners rate it.</p>
  <div class="honesty"><span class="ico">⚠️</span><div>
    <b>Honesty contract.</b> Round-trip CER/WER measure intelligibility of synthetic renders — they are <b>not</b> TTS naturalness scores.
    MOS: <b>NOT TESTED</b>. Human dataset: <b>${ds.collected}/${ds.total_slots}</b> collected.
    Listener responses: <b>${ls.n_response_files}</b>. No synthetic audio is ever counted as human speech.</div></div>
  <div class="grid g4">
    <div class="card kpi"><div class="v">${totalRenders}</div><div class="l">renders audited</div><div class="s">${esc(o.latest_run?.run||"no run")}</div></div>
    <div class="card kpi k-teal"><div class="v">${pct(totalRenders?cleanRenders/totalRenders:null)}</div><div class="l">fully clean</div><div class="s">${cleanRenders}/${totalRenders} under live gates</div></div>
    <div class="card kpi k-green"><div class="v">${counts["PASS (automated)"]}/12</div><div class="l">languages PASS</div><div class="s">automated only — not human verified</div></div>
    <div class="card kpi k-amber"><div class="v">${o.tests?.tests_run??"—"}</div><div class="l">regression tests</div><div class="s">${esc(o.tests?.status||"NOT TESTED")}</div></div>
  </div>
  <div class="grid g2" style="margin-top:14px">
    <div class="card chart-card"><h2 class="sec" style="margin-top:0">Clean render rate · live gates</h2>
      ${barChart(perLang.map(p=>({label:p.lang,value:p.n?p.clean/p.n:0,text:p.n?Math.round(100*p.clean/p.n)+"%":"—"})))}
      <div class="tiny">Move the gate sliders in the Live controls rail — this chart and the matrix recompute instantly.</div></div>
    <div class="card chart-card"><h2 class="sec" style="margin-top:0">Language status distribution</h2>${donut(counts)}
      <div class="grid g2" style="margin-top:12px">
        <div><div class="tiny">HUMAN DATASET</div>${badge(ds.human_dataset_status)} <span class="tiny">${ds.collected}/${ds.total_slots} slots · ${ds.verified} verified</span></div>
        <div><div class="tiny">LISTENING</div>${badge(ls.status)} <span class="tiny">${ls.n_listeners} listeners</span></div>
      </div></div>
  </div>
  <h2 class="sec">Quality gate matrix <span class="tiny">recomputed with your live gates</span></h2>
  <div class="tbl-wrap"><table class="tbl"><thead><tr>
    <th>Lang</th><th>Language</th><th>Status</th><th class="num">Clean / n</th><th class="num">CER clean mean</th>
    <th class="num">Worst CER</th><th class="num">RTF</th><th>TTS</th><th>ASR</th><th>Human naturalness</th></tr></thead><tbody>
    ${perLang.map(p=>`<tr data-action="lang-open" data-lang="${p.lang}" style="cursor:pointer">
      <td><b>${p.lang}</b></td><td>${esc(NAMES[p.lang])}</td><td>${badge(p.st)}</td>
      <td class="num">${p.clean}/${p.n}</td><td class="num">${fmt(p.m.cer_clean_mean)}</td>
      <td class="num">${fmt(p.m.cer_clean_max)}</td><td class="num">${fmt(p.m.rtf,2)}</td>
      <td>${esc(p.m.tts_backend||"—")}</td><td>${esc(p.m.asr_backend||"—")}</td><td>${badge("NOT TESTED")}</td></tr>`).join("")}
  </tbody></table></div>
  <h2 class="sec">Defect spotlight <span class="tiny">worst measured renders — candidates, not native-speaker verdicts</span></h2>
  <div class="grid g2">
    ${worst.length?worst.map(r=>`<div class="card">
      <div style="display:flex;gap:9px;align-items:center;margin-bottom:8px">
        ${badge(r._g.status)}<b>${r.lang} · s${r.sentence} take ${r.take}</b>
        <button class="rowplay" data-action="play-row" data-key="${rowKey(r)}" data-url="/api/runs/${encodeURIComponent(S.runName)}/audio/${r.wav.split("/").pop()}" style="margin-left:auto">▶</button></div>
      <div class="quote">${esc(r.reference)}</div>
      <div class="quote hyp" style="margin-top:6px">${esc(r.hypothesis)}</div>
      <div class="tiny" style="margin-top:7px">CER clean ${fmt(r.cer_clean)} · ${(r.notes||[]).map(esc).join("; ")}</div>
    </div>`).join(""):`<div class="card empty">No defective renders under the current gates.</div>`}
  </div>`;
}

function vLanguages(){
  const d=S.languages; if(!d) return `<div class="empty"><span class="spinner"></span>Loading languages…</div>`;
  return `
  <h1 class="page">Twelve languages, <em>twelve audits</em></h1>
  <p class="page-sub">Each card carries the measured round-trip status, the phonetic checklist that still needs
  native-speaker evidence, and the human-dataset progress. Click a card for the full audit drawer.</p>
  <div class="grid g3">
    ${d.languages.map(l=>{
      const m=l.metrics||{};
      const rate=m.n?m.clean_renders/m.n:0;
      return `<div class="card lang-card" data-action="lang-open" data-lang="${l.lang}">
        <div class="lc-top"><span class="lc-code">${l.lang}</span>
          <div><div class="lc-name">${esc(l.name)}</div><div class="lc-script">${esc(l.script||"")} · ${esc(l.tts_backend||"?")} TTS</div></div>
          <span style="margin-left:auto">${badge(l.status)}</span></div>
        <div class="bar ${rate<1?"warm":""}"><i style="width:${Math.round(rate*100)}%"></i></div>
        <div class="lc-metrics"><span>clean <b>${m.clean_renders??"—"}/${m.n??"—"}</b></span>
          <span>CER <b>${fmt(m.cer_clean_mean)}</b></span><span>RTF <b>${fmt(m.render_rtf_mean,2)}</b></span></div>
        <div class="tiny" style="margin-top:8px">${l.defects.length} measured defect render${l.defects.length===1?"":"s"} ·
          dataset ${l.dataset.collected}/${l.dataset.slots} · phonetics NOT TESTED</div>
        ${l.asr_note?`<div class="tiny" style="color:var(--amber);margin-top:5px">⚠ ${esc(l.asr_note)}</div>`:""}
      </div>`;}).join("")}
  </div>`;
}

function langDrawer(lang){
  const l=S.languages?.languages.find(x=>x.lang===lang); if(!l) return;
  const m=l.metrics||{};
  openDrawer(`${l.name} (${lang}) — audit`, `
    <div style="display:flex;gap:8px;flex-wrap:wrap">${badge(l.status)}${badge("NOT TESTED")}<span class="tiny">human naturalness</span></div>
    <dl class="kv">
      <dt>Script</dt><dd>${esc(l.script||"—")}</dd>
      <dt>TTS backend</dt><dd>${esc(l.tts_backend||"—")}</dd>
      <dt>ASR backend</dt><dd>${esc(l.asr_backend||"—")}${l.asr_note?` <span class="tiny">(${esc(l.asr_note)})</span>`:""}</dd>
      <dt>Renders</dt><dd>${m.clean_renders??"—"} clean / ${m.n??"—"} total</dd>
      <dt>CER clean mean / max</dt><dd>${fmt(m.cer_clean_mean)} / ${fmt(m.cer_clean_max)}</dd>
      <dt>WER clean mean</dt><dd>${fmt(m.wer_clean_mean)}</dd>
      <dt>Render RTF mean</dt><dd>${fmt(m.render_rtf_mean,3)}</dd>
      <dt>Mean duration</dt><dd>${fmt(m.duration_mean_s,2)} s</dd>
      <dt>All renders audible</dt><dd>${m.audible_all?"yes":"no"}</dd>
      <dt>Dataset</dt><dd>${l.dataset.collected}/${l.dataset.slots} collected · ${l.dataset.verified} verified · ${l.dataset.speakers} speakers</dd>
    </dl>
    <h2 class="sec">Phonetic checklist</h2>
    <div class="tiny" style="margin-bottom:8px">Evaluation targets from the audit brief. Status: <b>NOT TESTED</b> — each item needs native-speaker evidence.</div>
    <ul class="check-list">${l.phonetic_checks.map(c=>`<li><span class="st">${badge("NOT TESTED")}</span><span>${esc(c)}</span></li>`).join("")}</ul>
    <h2 class="sec">Measured defect renders (${l.defects.length})</h2>
    ${l.defects.length?l.defects.map(df=>`<div class="card" style="padding:11px 13px">
      <div style="display:flex;gap:8px;align-items:center">${badge(df.status)}<span class="tiny">s${df.sentence} · take ${df.take} · CER ${fmt(df.cer_clean)}</span>
        <button class="rowplay" data-action="play-row" data-key="d_${lang}_${df.sentence}_${df.take}" data-url="/api/runs/${encodeURIComponent(S.runName)}/audio/${df.wav.split("/").pop()}" style="margin-left:auto">▶</button></div>
      <div class="quote" style="margin-top:7px">${esc(df.reference)}</div>
      <div class="quote hyp" style="margin-top:5px">${esc(df.hypothesis)}</div>
      <div class="tiny" style="margin-top:5px">${(df.notes||[]).map(esc).join("; ")}</div></div>`).join("")
      :`<div class="empty">No defective renders in the latest run.</div>`}
  `);
}

function vEvidence(){
  if(!S.run) return `<div class="empty"><span class="spinner"></span>Loading evidence…</div>`;
  const rows=visibleRows();
  const all=runRows();
  const selCount=S.sel.size;
  return `
  <h1 class="page">Render evidence <em>· ${esc(S.runName)}</em></h1>
  <p class="page-sub">${all.length} local renders, ${S.run.repeats_per_sentence} takes per sentence.
  Search, filter, sort, drag to build your own review order, select in bulk, and play any take.
  Status badges recompute live with the gate sliders.</p>
  <div class="toolbar">
    <select id="runSelect" class="btn ghost small" style="padding:7px 10px">
      ${S.runs.map(r=>`<option value="${esc(r.run)}" ${r.run===S.runName?"selected":""}>${esc(r.run)} · ${r.n_renders} renders</option>`).join("")}
    </select>
    <div class="search"><span>⌕</span><input id="evSearch" type="text" placeholder="search reference, hypothesis, notes…" value="${esc(S.filters.q)}"></div>
    <button class="btn small ghost" data-action="ev-play-all">▶ Play shown</button>
    <button class="btn small ghost" data-action="ev-play-sel" ${selCount?"":"disabled"}>▶ Play selected (${selCount})</button>
    <button class="btn small ghost" data-action="ev-export-sel" ${selCount?"":"disabled"}>Export selected</button>
    <button class="btn small ghost" data-action="ev-clear-sel" ${selCount?"":"disabled"}>Clear selection</button>
    <span class="count-note">${rows.length} shown · ${all.filter(r=>rowStatus(r,S.gates).status!=="PASS (automated)").length} flagged</span>
  </div>
  <div class="tbl-wrap"><table class="tbl" id="evTable"><thead><tr>
    <th style="width:30px"><input type="checkbox" id="evSelAll" aria-label="Select all shown"></th>
    <th style="width:26px"></th><th>Key</th><th>Reference</th><th>Heard</th><th>Status</th>
    <th class="num">CER</th><th class="num">WER</th><th class="num">Dur s</th><th class="num">RMS</th>
    <th class="num">Voiced</th><th class="num">Band</th><th class="num">RTF</th><th></th></tr></thead><tbody>
    ${rows.map(r=>{const k=rowKey(r);const k2=k;return `<tr draggable="true" data-drag="${k2}" data-key="${k2}" class="${S.sel.has(k2)?"sel":""}">
      <td><input type="checkbox" data-action="ev-sel" data-key="${k2}" ${S.sel.has(k2)?"checked":""} aria-label="select ${k2}"></td>
      <td><span class="drag-handle" title="Drag to reorder">⠿</span></td>
      <td><b>${r.lang}</b> <span class="tiny">s${r.sentence}·t${r.take}</span></td>
      <td class="indic" style="max-width:230px">${esc(r.reference)}</td>
      <td class="indic" style="max-width:230px;color:${r._g.status==="PASS (automated)"?"var(--muted)":"var(--amber)"}">${esc(r.hypothesis)}</td>
      <td>${badge(r._g.status)}</td>
      <td class="num">${fmt(r.cer_clean)}</td><td class="num">${fmt(r.wer_clean)}</td>
      <td class="num">${fmt(r.signal?.duration_s,2)}</td><td class="num">${fmt(r.signal?.rms_dbfs,1)}</td>
      <td class="num">${fmt(r.signal?.voiced_frac,2)}</td><td class="num">${fmt(r.signal?.voice_band_ratio,2)}</td>
      <td class="num">${fmt(r.render_rtf,2)}</td>
      <td style="white-space:nowrap"><button class="rowplay" data-action="play-row" data-key="${k2}" data-url="/api/runs/${encodeURIComponent(S.runName)}/audio/${r.wav.split("/").pop()}">▶</button>
        <button class="icon-btn" data-action="ev-detail" data-key="${k2}" title="Details">⋯</button></td></tr>`;}).join("")}
  </tbody></table></div>
  ${rows.length?"":`<div class="empty">No renders match the current filters.</div>`}`;
}

function evDetail(key){
  const r=runRows().find(x=>rowKey(x)===key); if(!r) return;
  const g=rowStatus(r,S.gates); const s=r.signal||{};
  openDrawer(`${key} — render detail`,`
    <div style="display:flex;gap:8px;align-items:center">${badge(g.status)}
      <button class="btn small teal" data-action="play-row" data-key="det_${key}" data-url="/api/runs/${encodeURIComponent(S.runName)}/audio/${r.wav.split("/").pop()}">▶ Play take</button></div>
    ${g.fails.length?`<div class="tiny" style="color:var(--red)">Gate failures: ${g.fails.join(", ")}</div>`:""}
    <div class="quote">${esc(r.reference)}</div>
    <div class="quote hyp">${esc(r.hypothesis)}</div>
    <dl class="kv">
      <dt>Language</dt><dd>${esc(NAMES[r.lang])} (${r.lang})</dd>
      <dt>Prepared text</dt><dd class="indic">${esc(r.prepared)}</dd>
      <dt>TTS / ASR</dt><dd>${esc(r.tts_backend)} / ${esc(r.asr_backend)}</dd>
      <dt>Script OK</dt><dd>${r.script_ok?"yes":"no"} (${esc(r.script)})</dd>
      <dt>CER raw / clean</dt><dd>${fmt(r.cer)} / ${fmt(r.cer_clean)}</dd>
      <dt>WER raw / clean</dt><dd>${fmt(r.wer)} / ${fmt(r.wer_clean)}</dd>
      ${r.cer_clean_digit_expanded!=null?`<dt>CER digit-expanded</dt><dd>${fmt(r.cer_clean_digit_expanded)}</dd>`:""}
      <dt>Render / ASR ms</dt><dd>${fmt(r.render_ms,0)} / ${fmt(r.asr_ms,0)}</dd>
      <dt>Render RTF</dt><dd>${fmt(r.render_rtf,3)}</dd>
      <dt>Duration</dt><dd>${fmt(s.duration_s,3)} s @ ${s.sample_rate} Hz</dd>
      <dt>RMS / peak dBFS</dt><dd>${fmt(s.rms_dbfs,1)} / ${fmt(s.peak_dbfs,1)}</dd>
      <dt>Clip fraction</dt><dd>${fmt(s.clip_frac,5)}</dd>
      <dt>Voiced fraction</dt><dd>${fmt(s.voiced_frac,3)}</dd>
      <dt>Lead / trail silence</dt><dd>${fmt(s.lead_silence_s,2)} / ${fmt(s.trail_silence_s,2)} s</dd>
      <dt>Voice band 100–4k</dt><dd>${fmt(s.voice_band_ratio,3)}</dd>
      <dt>Telephone band (diag)</dt><dd>${fmt(s.speech_band_ratio,3)}</dd>
      <dt>HF share (diag)</dt><dd>${fmt(s.hf_share,4)}</dd>
      <dt>Spectral centroid</dt><dd>${fmt(s.spectral_centroid_hz,0)} Hz</dd>
      <dt>Notes</dt><dd>${(r.notes||[]).map(esc).join("; ")||"—"}</dd>
    </dl>
    <div class="tiny">HF share and telephone-band ratio are diagnostics only — fricatives and the humanizer's room tone
    legitimately raise them; they are not hiss verdicts. Objective hiss detection: NOT TESTED.</div>`);
}

function vBenchmarks(){
  const jobs=S.jobs, res=S.resources;
  const running=jobs.some(j=>j.state==="running");
  return `
  <h1 class="page">Benchmarks <em>· bounded, local, reproducible</em></h1>
  <p class="page-sub">Launch the proven speak-check harness on a subset of languages. Every run writes a NEW
  timestamped directory — historical results are never overwritten. No cloud inference is used.</p>
  <div class="grid g2">
    <div class="card">
      <h2 class="sec" style="margin-top:0">New round-trip run</h2>
      <div class="field"><label>Languages</label>
        <div style="display:flex;flex-wrap:wrap;gap:6px" id="benchLangs">
          ${LANGS.map(l=>`<button class="chip ${S.benchLangs.has(l)?"on":""}" data-action="bench-lang" data-lang="${l}">${l} · ${NAMES[l]}</button>`).join("")}
        </div></div>
      <div class="grid g2">
        <div class="field"><label>Takes per sentence</label>
          <select id="benchRepeats"><option>1</option><option selected>2</option><option>3</option><option>4</option><option>5</option></select></div>
        <div class="field"><label>Sentences per language</label>
          <select id="benchSentences"><option>1</option><option>2</option><option selected>3</option><option>4</option><option>5</option></select></div>
      </div>
      <button class="btn" data-action="bench-run" ${running?"disabled":""}>${running?"<span class='spinner'></span>Run in progress":"▶ Launch benchmark"}</button>
      <div class="tiny" style="margin-top:8px">12 langs × 3 sentences × 2 takes ≈ 72 renders, a few minutes on this CPU.</div>
    </div>
    <div class="card">
      <h2 class="sec" style="margin-top:0">Resources</h2>
      ${res?`<dl class="kv">
        <dt>Console RSS</dt><dd>${res.console_rss_mb??"—"} MB</dd>
        <dt>Logical CPUs</dt><dd>${res.cpu_logical}</dd>
        <dt>STT threads</dt><dd>${res.stt_threads}</dd>
        <dt>TTS threads knob</dt><dd>${res.tts_threads} (0 = ORT default)</dd>
      </dl>
      <div class="tiny" style="margin-top:8px">${esc(res.note)}</div>
      ${Object.keys(res.historical||{}).length?`<h2 class="sec">Historical capacity (read-only)</h2>
        <div class="job-log">${esc(JSON.stringify(res.historical,null,1).slice(0,1400))}</div>`:""}`
      :`<div class="empty"><span class="spinner"></span>measuring…</div>`}
    </div>
  </div>
  <h2 class="sec">Jobs</h2>
  ${jobs.length?jobs.map(j=>`<div class="card" style="margin-bottom:10px">
    <div style="display:flex;gap:9px;align-items:center;flex-wrap:wrap">
      ${j.state==="running"?`<span class="badge b-info"><span class="spinner" style="width:10px;height:10px;margin:0"></span> running</span>`
        :j.state==="done"?`<span class="badge b-pass">done</span>`
        :j.state==="partial"?`<span class="badge b-partial">partial</span>`:`<span class="badge b-fail">error</span>`}
      <b>${esc(j.kind)}</b><span class="tiny">${esc(j.id)} · started ${esc(j.started||"")}</span>
      ${j.out?`<span class="tiny">→ ${esc(j.out)}</span>`:""}
      ${j.langs?`<span class="tiny">${j.langs.join(",")} · ${j.repeats}×${j.sentences}</span>`:""}
    </div>
    ${j.error?`<div class="tiny" style="color:var(--red);margin-top:6px">${esc(j.error)}</div>`:""}
    ${j.log?`<details style="margin-top:7px"><summary class="tiny" style="cursor:pointer">log tail</summary><div class="job-log">${esc(j.log)}</div></details>`:""}
  </div>`).join(""):`<div class="card empty">No jobs yet. Launch a benchmark or prepare an extended listening package.</div>`}`;
}

/* ---------------- dataset ---------------- */
function dsVisible(){
  let e=S.dataset?.entries||[];
  const f=S.filters;
  if(f.lang) e=e.filter(x=>x.lang===f.lang);
  if(f.q){const q=f.q.toLowerCase();
    e=e.filter(x=>(x.id+(x.reference_text||"")+(x.speaker_id||"")+(x.prompt_hint||"")).toLowerCase().includes(q));}
  if(f.defects) e=e.filter(x=>x.status==="NOT_COLLECTED"||(x._problems||[]).length);
  if(f.sort==="lang") e=[...e].sort((a,b)=>a.lang.localeCompare(b.lang)||a.id.localeCompare(b.id));
  else if(f.sort==="status") e=[...e].sort((a,b)=>(a.status==="COLLECTED"?0:1)-(b.status==="COLLECTED"?0:1));
  else if(f.sort==="cer") e=[...e].sort((a,b)=>(b.duration_s||0)-(a.duration_s||0));
  else if(f.sort==="custom"&&S.dsOrder.length){
    const idx=new Map(S.dsOrder.map((k,i)=>[k,i]));
    e=[...e].sort((a,b)=>(idx.get(a.id)??1e9)-(idx.get(b.id)??1e9));
  }
  return e;
}
function vDataset(){
  const d=S.dataset; if(!d) return `<div class="empty"><span class="spinner"></span>Loading manifest…</div>`;
  const entries=dsVisible(), sum=d.summary;
  const collected=sum.collected;
  return `
  <h1 class="page">Human recording dataset <em>· ${collected}/${sum.total_slots}</em></h1>
  <p class="page-sub">240 slots, 20 per language. Only genuine, consented human recordings belong here —
  synthetic TTS audio is never accepted, and an ASR hypothesis is never a ground-truth transcript.
  Every mutation is backed up and undoable.</p>
  <div class="honesty"><span class="ico">🎙</span><div>
    <b>HUMAN DATASET: ${esc(sum.human_dataset_status)}.</b> ${collected} collected · ${sum.verified} independently verified.
    Target: ≥5 consented native speakers per language. Recording requires a real microphone and a real person —
    the console enforces consent, human-written references, and a second-speaker transcript verification.</div></div>
  <div class="grid g4" style="margin-bottom:14px">
    ${["hi","ta","ml","en"].map(l=>{const p=sum.per_lang[l];return `<div class="card kpi k-teal" style="padding:12px 14px">
      <div class="v" style="font-size:20px">${p.collected}/${p.slots}</div><div class="l">${NAMES[l]}</div>
      <div class="bar" style="margin-top:7px"><i style="width:${Math.round(100*p.collected/p.slots)}%"></i></div>
      <div class="s">${p.speakers} speakers · ${p.verified} verified</div></div>`;}).join("")}
  </div>
  <div class="toolbar">
    <button class="btn" data-action="ds-record">🎙 Record a slot</button>
    <button class="btn small ghost" data-action="ds-validate">Validate collected</button>
    <button class="btn small ghost" data-action="ds-undo" ${d.undo_available?"":"disabled"}>↩ Undo last change</button>
    <button class="btn small ghost" data-action="ds-bulk-verify" ${S.sel.size?"":"disabled"}>Verify selected (${S.sel.size})</button>
    <button class="btn small danger" data-action="ds-bulk-clear" ${S.sel.size?"":"disabled"}>Clear selected</button>
    <div class="search"><span>⌕</span><input id="dsSearch" type="text" placeholder="search slot, reference, speaker…" value="${esc(S.filters.q)}"></div>
    <span class="count-note">${entries.length} shown</span>
  </div>
  <div class="tbl-wrap"><table class="tbl" id="dsTable"><thead><tr>
    <th style="width:30px"><input type="checkbox" id="dsSelAll" aria-label="Select all shown"></th>
    <th style="width:26px"></th><th>Slot</th><th>Lang</th><th>Status</th><th>Reference (human-written)</th>
    <th>Speaker</th><th>Verified</th><th class="num">Dur s</th><th>Noise</th><th>Device</th><th></th></tr></thead><tbody>
    ${entries.map(e=>`<tr draggable="true" data-drag="${e.id}" data-key="${e.id}" class="${S.sel.has(e.id)?"sel":""}">
      <td><input type="checkbox" data-action="ds-sel" data-key="${e.id}" ${S.sel.has(e.id)?"checked":""} aria-label="select ${e.id}"></td>
      <td><span class="drag-handle" title="Drag to reorder">⠿</span></td>
      <td><b>${e.id}</b></td><td>${e.lang}</td>
      <td>${e.status==="COLLECTED"?`<span class="badge b-pass">COLLECTED</span>`:`<span class="badge b-nt">NOT_COLLECTED</span>`}</td>
      <td class="indic" style="max-width:250px">${esc(e.reference_text||e.prompt_hint||"—")}</td>
      <td>${esc(e.speaker_id||"—")}</td>
      <td>${e.status!=="COLLECTED"?"—":e.transcript_verified?`<span class="badge b-pass">yes</span>`:`<span class="badge b-partial">pending</span>`}</td>
      <td class="num">${fmt(e.duration_s,1)}</td><td>${esc(e.noise_condition||"—")}</td><td>${esc(e.device||"—")}</td>
      <td style="white-space:nowrap">
        ${e.status==="COLLECTED"?`<button class="rowplay" data-action="play-row" data-key="ds_${e.id}" data-url="/api/dataset/${e.id}/audio">▶</button>
          <button class="icon-btn" data-action="ds-verify" data-key="${e.id}" title="Verify transcript">✓</button>
          <button class="icon-btn" data-action="ds-clear" data-key="${e.id}" title="Clear slot (undoable)">🗑</button>`
          :`<button class="icon-btn" data-action="ds-record-slot" data-key="${e.id}" title="Record this slot">🎙</button>`}
        <button class="icon-btn" data-action="ds-detail" data-key="${e.id}" title="Details">⋯</button></td></tr>`).join("")}
  </tbody></table></div>
  <div class="tiny" style="margin-top:9px">Drag rows to set your collection priority order (saved with views). Cleared audio is quarantined, never deleted.</div>`;
}

function dsDetail(id){
  const e=S.dataset?.entries.find(x=>x.id===id); if(!e) return;
  openDrawer(`Slot ${id}`,`
    <div style="display:flex;gap:8px">${e.status==="COLLECTED"?`<span class="badge b-pass">COLLECTED</span>`:`<span class="badge b-nt">NOT_COLLECTED</span>`}
      ${e.status==="COLLECTED"?`<button class="btn small teal" data-action="play-row" data-key="det_${id}" data-url="/api/dataset/${id}/audio">▶ Play recording</button>`:""}</div>
    <dl class="kv">
      <dt>Language</dt><dd>${NAMES[e.lang]} (${e.lang})</dd>
      <dt>Domain</dt><dd>${esc(e.domain||"—")}</dd>
      <dt>Prompt hint</dt><dd>${esc(e.prompt_hint||"—")}</dd>
      <dt>Target group</dt><dd>${e.target_speaker_group??"—"}</dd>
      <dt>Reference</dt><dd class="indic">${esc(e.reference_text||"— (human-written text required at ingest)")}</dd>
      <dt>Speaker (pseudonymous)</dt><dd>${esc(e.speaker_id||"—")}</dd>
      <dt>Consent</dt><dd>${e.consent===true?"recorded ✓":"—"}</dd>
      <dt>Transcript verified</dt><dd>${e.transcript_verified?`yes, by ${esc(e.transcript_verified_by||"?")}`:"no"}</dd>
      <dt>Duration</dt><dd>${fmt(e.duration_s,2)} s</dd>
      <dt>Noise / device</dt><dd>${esc(e.noise_condition||"—")} / ${esc(e.device||"—")}</dd>
      <dt>Collected at</dt><dd>${esc(e.collected_at||"—")}</dd>
      <dt>Audio path</dt><dd>${esc(e.audio_path)}</dd>
      <dt>SHA-256</dt><dd style="font-size:11px">${esc(e.audio_sha256||"—")}</dd>
      <dt>Validation</dt><dd>${(e._problems||[]).length?`<span style="color:var(--red)">${(e._problems||[]).map(esc).join("; ")}</span>`:"clean"}</dd>
    </dl>`);
}

/* ---------------- recorder ---------------- */
let rec=null;
const WORKLET=`class Rec extends AudioWorkletProcessor{process(inputs){const c=inputs[0]&&inputs[0][0];if(c)this.port.postMessage(new Float32Array(c));return true;}}registerProcessor('rec',Rec);`;
async function startRecorder(){
  const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
  const ctx=new AudioContext();
  const blob=new Blob([WORKLET],{type:"application/javascript"});
  await ctx.audioWorklet.addModule(URL.createObjectURL(blob));
  const src=ctx.createMediaStreamSource(stream);
  const node=new AudioWorkletNode(ctx,"rec");
  const analyser=ctx.createAnalyser(); analyser.fftSize=512;
  const chunks=[]; node.port.onmessage=e=>chunks.push(e.data);
  src.connect(analyser); analyser.connect(node); node.connect(ctx.destination);
  rec={stream,ctx,node,analyser,chunks,t0:performance.now(),raf:0,wav:null};
  const meter=$("#recMeter i"), time=$("#recTime");
  const buf=new Uint8Array(analyser.frequencyBinCount);
  const loop=()=>{ if(!rec) return;
    analyser.getByteTimeDomainData(buf);
    let peak=0; for(let i=0;i<buf.length;i++) peak=Math.max(peak,Math.abs(buf[i]-128)/128);
    if(meter) meter.style.width=Math.min(100,peak*140)+"%";
    if(time) time.textContent=((performance.now()-rec.t0)/1000).toFixed(1)+" s";
    rec.raf=requestAnimationFrame(loop); };
  loop();
}
function stopRecorder(){
  if(!rec) return null;
  cancelAnimationFrame(rec.raf);
  try{rec.node.disconnect();}catch(e){}
  rec.stream.getTracks().forEach(t=>t.stop());
  const chunks=rec.chunks, rate=rec.ctx.sampleRate;
  rec.ctx.close(); rec=null;
  if(!chunks.length) return null;
  let total=0; chunks.forEach(c=>total+=c.length);
  const all=new Float32Array(total); let o=0;
  chunks.forEach(c=>{all.set(c,o);o+=c.length;});
  const target=16000, n=Math.round(all.length*target/rate);
  const out=new Float32Array(n);
  for(let i=0;i<n;i++){const pos=i*rate/target, i0=Math.floor(pos), frac=pos-i0;
    out[i]=(all[i0]??0)*(1-frac)+(all[i0+1]??all[i0]??0)*frac;}
  const buf=new ArrayBuffer(44+out.length*2), dv=new DataView(buf);
  const ws=(off,s)=>{for(let i=0;i<s.length;i++)dv.setUint8(off+i,s.charCodeAt(i));};
  ws(0,"RIFF");dv.setUint32(4,36+out.length*2,true);ws(8,"WAVE");ws(12,"fmt ");
  dv.setUint32(16,16,true);dv.setUint16(20,1,true);dv.setUint16(22,1,true);
  dv.setUint32(24,target,true);dv.setUint32(28,target*2,true);dv.setUint16(32,2,true);dv.setUint16(34,16,true);
  ws(36,"data");dv.setUint32(40,out.length*2,true);
  for(let i=0;i<out.length;i++){const v=Math.max(-1,Math.min(1,out[i]));dv.setInt16(44+i*2,v<0?v*0x8000:v*0x7FFF,true);}
  return new Blob([buf],{type:"audio/wav"});
}
function recordModal(slotId){
  const d=S.dataset; if(!d) return;
  const lang=slotId?slotId.slice(0,2):"hi";
  const openSlots=d.entries.filter(e=>e.lang===lang&&e.status==="NOT_COLLECTED");
  openModal(`
    <h3>🎙 Record a human slot</h3>
    <div class="tiny" style="margin-bottom:10px">A real person must speak into a real microphone. The reference below must be
    written by a human — never copied from an ASR hypothesis. Consent is mandatory and recorded.</div>
    <div class="grid g2">
      <div class="field"><label>Language</label><select id="recLang">
        ${LANGS.map(l=>`<option value="${l}" ${l===lang?"selected":""}>${l} · ${NAMES[l]}</option>`).join("")}</select></div>
      <div class="field"><label>Slot</label><select id="recSlot">
        ${openSlots.map(e=>`<option value="${e.id}" ${e.id===slotId?"selected":""}>${e.id}</option>`).join("")||`<option value="">auto (next open)</option>`}</select></div>
    </div>
    <div class="field"><label>Reference text — human-written, in the native script</label>
      <textarea id="recRef" placeholder="e.g. मेरा ऑर्डर नंबर एक दो तीन है।"></textarea>
      <span class="hint">What the speaker will say. Verified later by a second fluent speaker.</span></div>
    <div class="grid g2">
      <div class="field"><label>Pseudonymous speaker id</label><input type="text" id="recSpeaker" placeholder="spk_hi_01" maxlength="40"></div>
      <div class="field"><label>Environment note (optional)</label><input type="text" id="recEnv" placeholder="quiet room, evening" maxlength="80"></div>
    </div>
    <div class="grid g2">
      <div class="field"><label>Noise condition</label><select id="recNoise">${d.noise_conditions.map(n=>`<option>${n}</option>`).join("")}</select></div>
      <div class="field"><label>Device</label><select id="recDevice">${d.devices.map(n=>`<option ${n==="laptop"?"selected":""}>${n}</option>`).join("")}</select></div>
    </div>
    <div class="rec-box">
      <button class="rec-btn" id="recBtn" data-action="rec-toggle">REC</button>
      <div class="rec-meter" id="recMeter"><i></i></div>
      <div class="rec-time" id="recTime">0.0 s</div>
      <audio id="recPreview" controls style="width:100%;display:none"></audio>
      <div class="tiny" id="recHint">Press REC, speak the reference naturally, press STOP. 0.5–60 s, 16 kHz mono WAV.</div>
    </div>
    <div class="consent"><input type="checkbox" id="recConsent">
      <span>I confirm the speaker gave explicit consent for this recording to be stored and used for IndicVoice evaluation,
      the reference text is human-written, and no private recording is uploaded to any external service.</span></div>
    <div class="modal-actions">
      <button class="btn ghost" data-action="modal-close">Cancel</button>
      <button class="btn" data-action="rec-submit">Ingest recording</button>
    </div>`);
  $("#recLang").addEventListener("change",e=>{
    const l=e.target.value;
    const slots=S.dataset.entries.filter(x=>x.lang===l&&x.status==="NOT_COLLECTED");
    $("#recSlot").innerHTML=slots.map(x=>`<option>${x.id}</option>`).join("")||`<option value="">auto (next open)</option>`;
  });
}
async function recToggle(){
  const btn=$("#recBtn");
  if(!rec){
    try{ await startRecorder(); btn.textContent="STOP"; btn.classList.add("rec");
      $("#recHint").textContent="Recording… speak the reference naturally."; sndClick(); }
    catch(e){ toast("Microphone unavailable: "+e.message,"err"); sndErr(); }
  }else{
    const wav=stopRecorder();
    btn.textContent="REC"; btn.classList.remove("rec");
    if(wav){ rec_lastWav=wav;
      const p=$("#recPreview"); p.src=URL.createObjectURL(wav); p.style.display="block";
      $("#recHint").textContent=`Captured ${(wav.size/32000).toFixed(1)} s @16 kHz. Preview, then ingest.`;
      sndOk();
    } else $("#recHint").textContent="Nothing captured — try again.";
  }
}
let rec_lastWav=null;
async function recSubmit(){
  const wav=rec_lastWav;
  if(!wav){toast("Record audio first","err");sndErr();return;}
  if(!$("#recConsent").checked){toast("Explicit consent is required","err");sndErr();return;}
  const reference=$("#recRef").value.trim(), speaker=$("#recSpeaker").value.trim();
  if(!reference){toast("Human-written reference text is required","err");sndErr();return;}
  if(!speaker){toast("Pseudonymous speaker id is required","err");sndErr();return;}
  const qs=new URLSearchParams({lang:$("#recLang").value,reference,speaker,consent:"yes",
    noise:$("#recNoise").value,device:$("#recDevice").value,slot_id:$("#recSlot").value||"",
    environment:$("#recEnv").value,convert:"1"});
  try{
    const r=await api("/api/dataset/ingest?"+qs.toString(),
      {method:"POST",headers:{"Content-Type":"audio/wav"},body:wav});
    rec_lastWav=null; closeModal();
    await loadDataset(); render();
    toast(`Slot ${r.entry.id} collected — verify with a second speaker`,"ok",
      {label:"Undo",fn:async()=>{try{await post("/api/dataset/undo");await loadDataset();render();toast("Ingest undone","info");}catch(e){toast(e.message,"err");}}});
    sndOk();
  }catch(e){ toast("Ingest rejected: "+e.message,"err"); sndErr(); }
}

/* ---------------- listening ---------------- */
function vListening(){
  const ls=S.listening; if(!ls) return `<div class="empty"><span class="spinner"></span>Loading listening program…</div>`;
  const pkg=S.pkg;
  const codes=pkg?pkg.samples:[];
  const code=codes[S.sampleIdx];
  const rated=Object.keys(S.ratings).length;
  const dims=pkg?pkg.dimensions:Object.keys(DIM_Q);
  return `
  <h1 class="page">Blind listening test <em>· human evidence</em></h1>
  <p class="page-sub">Samples are anonymized and shuffled; some repeat intentionally. Rate what you hear —
  do not guess the language. Results are labelled <b>mean listener rating</b>, never MOS.
  With zero responses the status stays <b>NOT TESTED</b>.</p>
  <div class="toolbar">
    <select id="pkgSelect" class="btn ghost small" style="padding:7px 10px">
      ${ls.packages.map(p=>`<option value="${p.id}" ${p.id===S.pkgId?"selected":""}>${esc(p.label)} · ${p.n_samples} samples</option>`).join("")}</select>
    <button class="btn small ghost" data-action="listen-prepare">Prepare extended 10-type set</button>
    <button class="btn small ghost" data-action="listen-results">View results</button>
    <span class="count-note">${ls.n_response_files} response files · ${ls.n_listeners} listeners · ${badge(ls.status)}</span>
  </div>
  ${pkg?`
  <div class="grid g2">
    <div class="card">
      <h2 class="sec" style="margin-top:0">Sample ${S.sampleIdx+1} / ${codes.length} · code ${esc(code||"—")}</h2>
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:10px">
        <button class="btn teal" data-action="listen-play" ${code?"":"disabled"}>▶ Play sample</button>
        <button class="btn small ghost" data-action="listen-prev" ${S.sampleIdx>0?"":"disabled"}>← Prev</button>
        <button class="btn small ghost" data-action="listen-next" ${S.sampleIdx<codes.length-1?"":"disabled"}>Next →</button>
        <span class="tiny">${rated}/${codes.length} rated this session</span>
      </div>
      <div class="sample-queue">${codes.map((c,i)=>`<button class="chip ${i===S.sampleIdx?"current":""} ${S.ratings[c]?"done":""}" data-action="listen-jump" data-idx="${i}">${i+1}</button>`).join("")}</div>
      <div class="field"><label>Pseudonymous listener id</label>
        <input type="text" id="listenerId" value="${esc(S.listener)}" placeholder="listener_01" maxlength="40"></div>
      <div class="field"><label>Comment for this sample (pronunciation / accent problems)</label>
        <textarea id="listenFeedback" placeholder="optional">${esc(S.feedback[code]||"")}</textarea></div>
      <div class="modal-actions" style="justify-content:flex-start">
        <button class="btn" data-action="listen-submit" ${rated&&S.listener?"":"disabled"}>Submit ${rated} ratings</button>
        <button class="btn small ghost" data-action="listen-reset">Reset session</button>
      </div>
    </div>
    <div class="card">
      <h2 class="sec" style="margin-top:0">Rate every dimension 1–5</h2>
      <div class="tiny" style="margin-bottom:9px">5 excellent · 4 good · 3 fair · 2 poor · 1 bad.
      The brief's eight questions are covered, plus prosody detail and overall comfort.</div>
      <div class="rate-grid">
        ${dims.map(dim=>{const q=DIM_Q[dim]||[dim,""];const cur=(S.ratings[code]||{})[dim];
          return `<div class="rate-row"><div class="q">${esc(q[0])}<small>${esc(dim)} · ${esc(q[1])}</small></div>
            <div class="stars" data-dim="${dim}">${[1,2,3,4,5].map(v=>
              `<button data-action="listen-rate" data-dim="${dim}" data-v="${v}" class="${cur>=v?"on":""}">${v}</button>`).join("")}</div></div>`;}).join("")}
      </div>
    </div>
  </div>`:`<div class="card empty">No listening package available.</div>`}`;
}

async function listenResults(){
  try{
    const r=await api(`/api/listening/${S.pkgId}/results`);
    const langs=Object.entries(r.per_lang||{});
    openDrawer(`Listening results — ${S.pkgId}`,`
      <div style="display:flex;gap:8px;align-items:center">${badge(r.status)}
        <span class="tiny">${esc(r.metric_label||"")}</span></div>
      <div class="tiny">${r.n_listeners||0} listeners · ${r.n_response_files||0} response files</div>
      ${r.status==="NOT TESTED"?`<div class="honesty"><span class="ico">🎧</span><div>${esc(r.note||"No listener responses exist. No scores are reported.")}</div></div>`:""}
      ${langs.map(([lang,st])=>`<div class="card" style="padding:12px 14px">
        <b>${NAMES[lang]||lang} (${lang})</b> <span class="tiny">${st.n_listeners} listeners · ${st.n_utterances} utterances</span>
        <table class="tbl" style="min-width:0;margin-top:8px"><thead><tr><th>Dimension</th><th class="num">Mean</th><th class="num">SD</th><th class="num">n</th></tr></thead><tbody>
        ${Object.entries(st.dimensions).map(([d,v])=>`<tr><td>${esc(d)}</td><td class="num">${v.mean??"—"}</td><td class="num">${v.sd??"—"}</td><td class="num">${v.n_ratings}</td></tr>`).join("")}
        </tbody></table>
        <div class="tiny" style="margin-top:6px">Repeat consistency: ${st.repeat_consistency.n_pairs_rated} pairs · mean |Δ| ${st.repeat_consistency.mean_abs_delta??"—"}</div>
      </div>`).join("")}
      ${Object.entries(r.qualitative_feedback||{}).map(([lang,fb])=>`<div><h2 class="sec">${lang} comments</h2>
        ${fb.map(f=>`<div class="quote" style="margin-bottom:6px">${esc(f.text)} <span class="tiny">— ${esc(f.listener)}</span></div>`).join("")}</div>`).join("")}
      ${(r.problems||[]).length?`<div class="tiny" style="color:var(--red)">${r.problems.map(esc).join("<br>")}</div>`:""}`);
  }catch(e){toast(e.message,"err");}
}

/* ---------------- reports / baseline ---------------- */
function vReports(){
  return `
  <h1 class="page">Final reports <em>· 14 sections, strict statuses</em></h1>
  <p class="page-sub">Generate the master-prompt final report from live evidence: quality matrix, ASR/TTS results,
  defects, human evaluation, MOS status, provider comparison, latency, CPU/RAM, regression, limitations,
  next steps, and per-language production readiness. New timestamped directory every time.</p>
  <div class="toolbar">
    <button class="btn" data-action="report-generate">▤ Generate final report</button>
    ${S.report?`<button class="btn small ghost" data-action="report-download">⬇ Download .md</button>`:""}
    <select id="reportSelect" class="btn ghost small" style="padding:7px 10px">
      <option value="">— pick a saved report —</option>
      ${S.reports.map(r=>`<option value="${r.run}" ${S.report?.run===r.run?"selected":""}>${r.run}</option>`).join("")}</select>
  </div>
  ${S.report?`<div class="md">${md(S.report.markdown)}</div>`:`<div class="card empty">No report loaded. Generate one or pick a saved report.</div>`}`;
}
function vBaseline(){
  const b=S.baseline; if(!b) return `<div class="empty"><span class="spinner"></span>Loading baseline…</div>`;
  return `
  <h1 class="page">Phase 0 baseline <em>· audit before change</em></h1>
  <p class="page-sub">Read-only repository audit at HEAD ${esc(b.data?.git?.head||"?")}: inventory, providers,
  language configuration, historical benchmarks, regression results, and the safety attestation.</p>
  <div class="toolbar"><span class="count-note">${b.all.length} baseline run(s) · latest ${esc(b.run)}</span></div>
  <div class="md">${md(b.markdown)}</div>`;
}

/* ---------------- render / routing ---------------- */
const VIEWS={overview:vOverview,languages:vLanguages,evidence:vEvidence,benchmarks:vBenchmarks,
  dataset:vDataset,listening:vListening,reports:vReports,baseline:vBaseline};
const LOADERS={overview:async()=>{await loadOverview();if(!S.run)await loadRuns();},
  languages:async()=>{await loadLanguages();if(!S.run)await loadRuns();},
  evidence:async()=>{await loadRuns();},
  benchmarks:async()=>{await loadJobs();await loadResources();},
  dataset:loadDataset, listening:loadListening,
  reports:loadReports, baseline:loadBaseline};
let renderToken=0;
async function render(){
  const token=++renderToken;
  const route=S.route;
  $$(".sidenav a").forEach(a=>a.classList.toggle("active",a.dataset.nav===route));
  const view=$("#view");
  try{
    if(LOADERS[route]) await LOADERS[route]();
    if(token!==renderToken) return;
    view.innerHTML=VIEWS[route]();
    view.classList.remove("enter"); void view.offsetWidth; view.classList.add("enter");
    document.body.classList.toggle("compact",S.filters.density);
    afterRender();
  }catch(e){
    view.innerHTML=`<div class="card empty" style="color:var(--red)">Could not load this section: ${esc(e.message)}<br>
      <span class="tiny">Is the console server running on 8010?</span></div>`;
  }
}
function afterRender(){
  const rs=$("#runSelect"); if(rs) rs.onchange=async e=>{S.runName=e.target.value;S.sel.clear();S.order=[];await loadRuns();render();};
  const ps=$("#pkgSelect"); if(ps) ps.onchange=async e=>{S.pkgId=e.target.value;S.sampleIdx=0;S.ratings={};S.feedback={};await loadListening();render();};
  const rp=$("#reportSelect"); if(rp) rp.onchange=async e=>{if(!e.target.value)return;
    S.report=await api("/api/reports/"+encodeURIComponent(e.target.value));render();};
  const es=$("#evSearch"); if(es) es.oninput=e=>{S.filters.q=e.target.value;rerenderTable();};
  const ds=$("#dsSearch"); if(ds) ds.oninput=e=>{S.filters.q=e.target.value;rerenderTable();};
  const sa=$("#evSelAll"); if(sa) sa.onchange=e=>{
    visibleRows().forEach(r=>{const k=rowKey(r);e.target.checked?S.sel.add(k):S.sel.delete(k);});render();};
  const da=$("#dsSelAll"); if(da) da.onchange=e=>{
    dsVisible().forEach(x=>{e.target.checked?S.sel.add(x.id):S.sel.delete(x.id);});render();};
  const li=$("#listenerId"); if(li) li.oninput=e=>{S.listener=e.target.value;
    const b=$('[data-action="listen-submit"]'); if(b) b.disabled=!(Object.keys(S.ratings).length&&S.listener);};
  const lf=$("#listenFeedback"); if(lf) lf.oninput=e=>{
    const code=S.pkg?.samples[S.sampleIdx]; if(code) S.feedback[code]=e.target.value;};
  bindDrag();
}
function rerenderTable(){
  const active=document.activeElement, id=active?.id, pos=active?.selectionStart;
  $("#view").innerHTML=VIEWS[S.route]();
  afterRender();
  if(id){const el=$("#"+id); if(el){el.focus(); try{el.setSelectionRange(pos,pos);}catch(e){}}}
}
function go(route){
  S.route=route; S.sel.clear();
  if(location.hash!=="#/"+route) location.hash="#/"+route;
  render();
  $("#sidenav").classList.remove("open");
}
window.addEventListener("hashchange",()=>{
  const r=(location.hash||"#/overview").slice(2);
  if(VIEWS[r]&&r!==S.route){S.route=r;S.sel.clear();render();}
});

/* ---------------- drag reorder ---------------- */
let dragKey=null;
function bindDrag(){
  $$("#view tr[draggable]").forEach(tr=>{
    tr.addEventListener("dragstart",e=>{dragKey=tr.dataset.drag;tr.classList.add("dragging");
      e.dataTransfer.effectAllowed="move";try{e.dataTransfer.setData("text/plain",dragKey);}catch(x){}});
    tr.addEventListener("dragend",()=>{tr.classList.remove("dragging");dragKey=null;
      $$(".drop-hint").forEach(x=>x.classList.remove("drop-hint"));});
    tr.addEventListener("dragover",e=>{e.preventDefault();tr.classList.add("drop-hint");});
    tr.addEventListener("dragleave",()=>tr.classList.remove("drop-hint"));
    tr.addEventListener("drop",e=>{
      e.preventDefault();tr.classList.remove("drop-hint");
      const target=tr.dataset.drag; if(!dragKey||dragKey===target) return;
      if(S.route==="evidence"){
        const keys=visibleRows().map(rowKey);
        const arr=S.order.length?S.order.filter(k=>keys.includes(k)):keys;
        keys.forEach(k=>{if(!arr.includes(k))arr.push(k);});
        const from=arr.indexOf(dragKey),to=arr.indexOf(target);
        if(from<0||to<0)return;
        arr.splice(from,1);arr.splice(to,0,dragKey);
        S.order=arr;S.filters.sort="custom";$("#fSort").value="custom";
      }else if(S.route==="dataset"){
        const ids=dsVisible().map(x=>x.id);
        const arr=S.dsOrder.length?S.dsOrder.filter(k=>ids.includes(k)):ids;
        ids.forEach(k=>{if(!arr.includes(k))arr.push(k);});
        const from=arr.indexOf(dragKey),to=arr.indexOf(target);
        if(from<0||to<0)return;
        arr.splice(from,1);arr.splice(to,0,dragKey);
        S.dsOrder=arr;S.filters.sort="custom";$("#fSort").value="custom";
      }
      sndClick(); render();
    });
  });
}

/* ---------------- saved views ---------------- */
function loadViews(){ try{S.views=JSON.parse(localStorage.getItem("ivq_views")||"[]");}catch(e){S.views=[];} }
function persistViews(){ localStorage.setItem("ivq_views",JSON.stringify(S.views)); renderViews(); }
function renderViews(){
  $("#savedList").innerHTML=S.views.length?S.views.map((v,i)=>
    `<li><button class="load" data-action="view-load" data-i="${i}">${esc(v.name)}</button>
     <span class="tiny">${esc(v.route)}</span>
     <button class="del" data-action="view-del" data-i="${i}" title="Delete view">✕</button></li>`).join("")
    :`<li class="tiny" style="border:none;background:none">No saved views yet</li>`;
}
function saveView(){
  const name=$("#viewName").value.trim();
  if(!name){toast("Name the view first","err");return;}
  S.views.push({name,route:S.route,gates:{...S.gates},filters:{...S.filters},
    order:[...S.order],dsOrder:[...S.dsOrder]});
  $("#viewName").value=""; persistViews(); sndOk(); toast(`View “${name}” saved`,"ok");
}
function applyView(v){
  S.gates={...v.gates}; S.filters={...v.filters}; S.order=v.order||[]; S.dsOrder=v.dsOrder||[];
  syncRail(); go(v.route); toast(`View “${v.name}” applied`,"info");
}
function syncRail(){
  const g=S.gates,f=S.filters;
  $("#gCer").value=g.cer;$("#gCerOut").textContent=g.cer.toFixed(2);
  $("#gRms").value=g.rms;$("#gRmsOut").textContent=g.rms;
  $("#gVoiced").value=g.voiced;$("#gVoicedOut").textContent=g.voiced.toFixed(2);
  $("#gBand").value=g.band;$("#gBandOut").textContent=g.band.toFixed(2);
  $("#gClip").value=g.clip;$("#gClipOut").textContent=g.clip.toFixed(4);
  $("#gDur").value=g.dur;$("#gDurOut").textContent=g.dur.toFixed(1);
  $("#pRate").value=S.rate;$("#pRateOut").textContent=S.rate.toFixed(2)+"×";
  $("#pVol").value=S.vol;$("#pVolOut").textContent=Math.round(S.vol*100)+"%";
  $("#fLang").value=f.lang;$("#fSort").value=f.sort;
  $("#tDensity").setAttribute("aria-checked",String(f.density));
  $("#tDefects").setAttribute("aria-checked",String(f.defects));
}

/* ---------------- actions ---------------- */
document.addEventListener("click",async e=>{
  const el=e.target.closest("[data-action]"); if(!el) return;
  const a=el.dataset.action;
  try{
  switch(a){
    case "lang-open": if(!S.languages) await loadLanguages(); langDrawer(el.dataset.lang); sndClick(); break;
    case "play-row": playUrl(el.dataset.url,el.dataset.key,el.classList.contains("rowplay")?el:null); break;
    case "ev-sel": {const k=el.dataset.key; el.checked?S.sel.add(k):S.sel.delete(k);
      el.closest("tr").classList.toggle("sel",el.checked);
      const n=S.sel.size;
      $$('[data-action="ev-play-sel"],[data-action="ev-export-sel"],[data-action="ev-clear-sel"]').forEach(b=>b.disabled=!n);
      const pb=$('[data-action="ev-play-sel"]'); if(pb)pb.textContent=`▶ Play selected (${n})`; break;}
    case "ev-clear-sel": S.sel.clear(); render(); break;
    case "ev-play-all": playQueue(visibleRows().map(r=>({url:`/api/runs/${encodeURIComponent(S.runName)}/audio/${r.wav.split("/").pop()}`,
      key:rowKey(r),btn:$(`.rowplay[data-key="${CSS.escape(rowKey(r))}"]`)}))); break;
    case "ev-play-sel": playQueue(visibleRows().filter(r=>S.sel.has(rowKey(r))).map(r=>({url:`/api/runs/${encodeURIComponent(S.runName)}/audio/${r.wav.split("/").pop()}`,
      key:rowKey(r),btn:$(`.rowplay[data-key="${CSS.escape(rowKey(r))}"]`)}))); break;
    case "ev-export-sel": {
      const rows=runRows().filter(r=>S.sel.has(rowKey(r)));
      download(JSON.stringify({exported:new Date().toISOString(),run:S.runName,gates:S.gates,rows},null,2),
        `evidence_selection_${Date.now()}.json`,"application/json");
      toast(`${rows.length} renders exported`,"ok"); break;}
    case "ev-detail": evDetail(el.dataset.key); break;
    case "bench-lang": {const l=el.dataset.lang;
      S.benchLangs.has(l)?S.benchLangs.delete(l):S.benchLangs.add(l);
      el.classList.toggle("on"); sndClick(); break;}
    case "bench-run": {
      if(!S.benchLangs.size){toast("Pick at least one language","err");break;}
      const r=await post("/api/benchmarks/run",{langs:[...S.benchLangs],
        repeats:+$("#benchRepeats").value,sentences:+$("#benchSentences").value});
      toast(`Benchmark job ${r.job} launched`,"ok"); sndOk();
      await loadJobs(); render(); startJobPoll(); break;}
    case "ds-record": recordModal(null); break;
    case "ds-record-slot": recordModal(el.dataset.key); break;
    case "ds-sel": {const k=el.dataset.key; el.checked?S.sel.add(k):S.sel.delete(k);
      el.closest("tr").classList.toggle("sel",el.checked);
      const n=S.sel.size;
      $$('[data-action="ds-bulk-verify"],[data-action="ds-bulk-clear"]').forEach(b=>b.disabled=!n);
      const vb=$('[data-action="ds-bulk-verify"]'); if(vb)vb.textContent=`Verify selected (${n})`; break;}
    case "ds-detail": dsDetail(el.dataset.key); break;
    case "ds-verify": verifyModal([el.dataset.key]); break;
    case "ds-bulk-verify": verifyModal([...S.sel].filter(id=>S.dataset.entries.find(x=>x.id===id)?.status==="COLLECTED")); break;
    case "ds-clear": clearSlots([el.dataset.key]); break;
    case "ds-bulk-clear": clearSlots([...S.sel]); break;
    case "ds-undo": {const r=await post("/api/dataset/undo"); await loadDataset(); render();
      toast(`Restored ${r.restored_from}`,"info"); sndClick(); break;}
    case "ds-validate": {const r=await post("/api/dataset/validate");
      toast(Object.keys(r.problems).length?`Validation: ${Object.keys(r.problems).length} slots with problems`:"Validation clean — PASS (automated)",
        Object.keys(r.problems).length?"err":"ok");
      await loadDataset(); render(); break;}
    case "rec-toggle": await recToggle(); break;
    case "rec-submit": await recSubmit(); break;
    case "modal-close": closeModal(); break;
    case "listen-play": {const code=S.pkg.samples[S.sampleIdx];
      playUrl(`/api/listening/${S.pkgId}/audio/${code}`,"ls_"+code,null); break;}
    case "listen-prev": S.sampleIdx=Math.max(0,S.sampleIdx-1); render(); break;
    case "listen-next": S.sampleIdx=Math.min(S.pkg.samples.length-1,S.sampleIdx+1); render(); break;
    case "listen-jump": S.sampleIdx=+el.dataset.idx; render(); break;
    case "listen-rate": {
      const code=S.pkg.samples[S.sampleIdx]; if(!code)break;
      S.ratings[code]=S.ratings[code]||{};
      S.ratings[code][el.dataset.dim]=+el.dataset.v;
      const row=el.closest(".stars");
      row.querySelectorAll("button").forEach(b=>b.classList.toggle("on",+b.dataset.v<=+el.dataset.v));
      const chip=$(`.sample-queue .chip[data-idx="${S.sampleIdx}"]`); if(chip)chip.classList.add("done");
      const sb=$('[data-action="listen-submit"]'); if(sb){sb.disabled=!(Object.keys(S.ratings).length&&S.listener);
        sb.textContent=`Submit ${Object.keys(S.ratings).length} ratings`;}
      tick(440+ +el.dataset.v*90,.05); break;}
    case "listen-submit": {
      const r=await post(`/api/listening/${S.pkgId}/responses`,
        {listener_id:S.listener,ratings:S.ratings,feedback:S.feedback});
      toast(`Saved ${r.saved} — thank you`,"ok"); sndOk();
      S.ratings={};S.feedback={};S.sampleIdx=0;
      await loadListening(); render(); break;}
    case "listen-reset": S.ratings={};S.feedback={};S.sampleIdx=0;render();toast("Session reset","info");break;
    case "listen-results": await listenResults(); break;
    case "listen-prepare": {
      const r=await post("/api/listening/prepare",{langs:LANGS,repeats:1});
      toast(`Preparing extended package → ${r.out}`,"ok"); sndOk();
      await loadJobs(); startJobPoll();
      if(S.route!=="benchmarks") go("benchmarks"); else render(); break;}
    case "report-generate": {
      el.disabled=true; el.innerHTML="<span class='spinner'></span>Generating…";
      const r=await post("/api/reports/generate");
      S.report=r; await loadReports(); render();
      toast(`Report ${r.run} written`,"ok"); sndOk(); break;}
    case "report-download": download(S.report.markdown,`indicvoice_final_report_${S.report.run}.md`,"text/markdown"); break;
    case "view-load": applyView(S.views[+el.dataset.i]); break;
    case "view-del": {const i=+el.dataset.i; const v=S.views[i];
      S.lastDeletedView={v,i}; S.views.splice(i,1); persistViews();
      toast(`View “${v.name}” deleted`,"info",{label:"Undo",fn:()=>{
        S.views.splice(S.lastDeletedView.i,0,S.lastDeletedView.v);persistViews();toast("View restored","ok");}}); break;}
  }
  }catch(err){ toast(err.message,"err"); sndErr(); }
});

function verifyModal(ids){
  if(!ids.length){toast("No COLLECTED slots selected","err");return;}
  openModal(`<h3>✓ Independent transcript verification</h3>
    <div class="tiny" style="margin-bottom:10px">A second native/fluent speaker — not the recorder — asserts that the
    human-written reference matches the audio in ${ids.length} slot(s): ${ids.map(esc).join(", ")}.</div>
    <div class="field"><label>Pseudonymous verifier id</label><input type="text" id="verifierId" placeholder="ver_01" maxlength="40"></div>
    <div class="modal-actions"><button class="btn ghost" data-action="modal-close">Cancel</button>
      <button class="btn" id="verifyGo">Record verification</button></div>`);
  $("#verifyGo").onclick=async()=>{
    const v=$("#verifierId").value.trim();
    if(!v){toast("Verifier id required","err");return;}
    let ok=0,fail=0;
    for(const id of ids){
      try{await post(`/api/dataset/${id}/verify`,{verifier:v});ok++;}
      catch(e){fail++;toast(`${id}: ${e.message}`,"err");}
    }
    closeModal(); await loadDataset(); S.sel.clear(); render();
    if(ok)toast(`${ok} slot(s) verified${fail?`, ${fail} failed`:""}`,"ok");
    sndOk();
  };
}
async function clearSlots(ids){
  const collected=ids.filter(id=>S.dataset.entries.find(x=>x.id===id)?.status==="COLLECTED");
  if(!collected.length){toast("Nothing COLLECTED to clear","info");return;}
  openModal(`<h3>🗑 Clear ${collected.length} slot(s)?</h3>
    <div class="tiny">Slots return to NOT_COLLECTED. Recordings are moved to quarantine, never deleted.
    The manifest is backed up first and this action is undoable.</div>
    <div class="modal-actions"><button class="btn ghost" data-action="modal-close">Cancel</button>
      <button class="btn danger" id="clearGo">Clear slots</button></div>`);
  $("#clearGo").onclick=async()=>{
    closeModal();
    const before=S.dataset.entries.filter(x=>collected.includes(x.id)).map(x=>({...x}));
    for(const id of collected){
      const i=S.dataset.entries.findIndex(x=>x.id===id);
      if(i>=0)S.dataset.entries[i]={...S.dataset.entries[i],status:"NOT_COLLECTED"};
    }
    S.sel.clear(); render();
    try{
      for(const id of collected) await post(`/api/dataset/${id}/clear`);
      await loadDataset(); render();
      toast(`${collected.length} slot(s) cleared`,"info",{label:"Undo",fn:async()=>{
        try{await post("/api/dataset/undo");await loadDataset();render();toast("Clear undone","ok");}
        catch(e){toast(e.message,"err");}}});
    }catch(e){
      S.dataset.entries=S.dataset.entries.map(x=>before.find(b=>b.id===x.id)||x);
      render(); toast("Clear failed, rolled back: "+e.message,"err"); sndErr();
    }
  };
}
function download(text,name,type){
  const b=new Blob([text],{type}); const u=URL.createObjectURL(b);
  const a=document.createElement("a"); a.href=u; a.download=name; a.click();
  setTimeout(()=>URL.revokeObjectURL(u),4000);
}

/* ---------------- job polling ---------------- */
function startJobPoll(){
  if(S.jobTimer) return;
  S.jobTimer=setInterval(async()=>{
    try{
      await loadJobs();
      const running=S.jobs.some(j=>j.state==="running");
      if(S.route==="benchmarks") render();
      if(!running){clearInterval(S.jobTimer);S.jobTimer=null;
        await loadRuns(); await loadListening();
        if(S.route==="benchmarks") render();
        toast("Job finished — evidence refreshed","ok"); sndOk();}
    }catch(e){clearInterval(S.jobTimer);S.jobTimer=null;}
  },2500);
}

/* ---------------- rail wiring ---------------- */
function wireRail(){
  const bind=(id,key,fmtFn)=>{
    const inp=$("#"+id),out=$("#"+id+"Out");
    inp.addEventListener("input",()=>{
      S.gates[key]=+inp.value; out.textContent=fmtFn(+inp.value);
      if(["overview","evidence","languages"].includes(S.route)) rerenderTable();
    });
  };
  bind("gCer","cer",v=>v.toFixed(2));
  bind("gRms","rms",v=>String(v));
  bind("gVoiced","voiced",v=>v.toFixed(2));
  bind("gBand","band",v=>v.toFixed(2));
  bind("gClip","clip",v=>v.toFixed(4));
  bind("gDur","dur",v=>v.toFixed(1));
  $("#pRate").addEventListener("input",e=>{S.rate=+e.target.value;
    $("#pRateOut").textContent=S.rate.toFixed(2)+"×";playerEl.playbackRate=S.rate;});
  $("#pVol").addEventListener("input",e=>{S.vol=+e.target.value;
    $("#pVolOut").textContent=Math.round(S.vol*100)+"%";applyAudio();});
  $("#fLang").addEventListener("change",e=>{S.filters.lang=e.target.value;S.sel.clear();render();});
  $("#fSort").addEventListener("change",e=>{S.filters.sort=e.target.value;render();});
  $("#tDensity").addEventListener("click",e=>{S.filters.density=!S.filters.density;
    e.currentTarget.setAttribute("aria-checked",String(S.filters.density));
    document.body.classList.toggle("compact",S.filters.density);sndClick();});
  $("#tDefects").addEventListener("click",e=>{S.filters.defects=!S.filters.defects;
    e.currentTarget.setAttribute("aria-checked",String(S.filters.defects));S.sel.clear();render();sndClick();});
  $("#gateReset").addEventListener("click",()=>{
    S.gates={cer:0.15,rms:-35,voiced:0.30,band:0.70,clip:0.002,dur:0.4};
    syncRail();render();toast("Gates reset to calibrated defaults","info");sndClick();});
  $("#viewExport").addEventListener("click",()=>{
    download(JSON.stringify({route:S.route,gates:S.gates,filters:S.filters,order:S.order,dsOrder:S.dsOrder},null,2),
      `view_${S.route}_${Date.now()}.json`,"application/json");
    toast("View exported","ok");});
  $("#viewSave").addEventListener("click",saveView);
  $("#viewName").addEventListener("keydown",e=>{if(e.key==="Enter")saveView();});
  $("#railCollapse").addEventListener("click",()=>{
    const r=$("#rail");
    if(window.innerWidth<=900){r.classList.toggle("open");}
    else{r.classList.toggle("collapsed");
      $("#railCollapse").textContent=r.classList.contains("collapsed")?"⟨":"⟩";}
    sndClick();});
  $("#masterMute").addEventListener("click",()=>{
    S.muted=!S.muted; if(S.muted) stopPlayback(); applyAudio();
    if(!S.muted) sndOk();
    toast(S.muted?"All sound muted":"Sound on","info");});
  $("#navToggle").addEventListener("click",()=>$("#sidenav").classList.toggle("open"));
  $("#drawerClose").addEventListener("click",closeDrawer);
  $("#drawerScrim").addEventListener("click",closeDrawer);
  $("#modalScrim").addEventListener("click",e=>{if(e.target.id==="modalScrim")closeModal();});
  document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeDrawer();closeModal();}});
  const fab=document.createElement("button");
  fab.className="rail-fab"; fab.textContent="🎛"; fab.title="Live controls";
  fab.onclick=()=>{$("#rail").classList.toggle("open");sndClick();};
  document.body.appendChild(fab);
  const fl=$("#fLang");
  LANGS.forEach(l=>{const o=document.createElement("option");o.value=l;o.textContent=`${l} · ${NAMES[l]}`;fl.appendChild(o);});
}

/* ---------------- boot ---------------- */
async function boot(){
  loadViews(); renderViews(); wireRail(); syncRail(); applyAudio();
  setInterval(()=>{const d=new Date();
    $("#clockPill").textContent=d.toTimeString().slice(0,8);},1000);
  const r=(location.hash||"#/overview").slice(2);
  S.route=VIEWS[r]?r:"overview";
  try{
    await api("/api/overview");
    $("#serverPill").classList.add("ok");
    $("#serverPill").querySelector("span:last-child").textContent="console live · 8010";
  }catch(e){
    $("#serverPill").classList.add("bad");
    $("#serverPill").querySelector("span:last-child").textContent="server offline";
  }
  await render();
  try{await loadJobs(); if(S.jobs.some(j=>j.state==="running")) startJobPoll();}catch(e){}
}
boot();
})();