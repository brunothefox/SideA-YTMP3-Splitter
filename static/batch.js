'use strict';
let batchBusy = false;
const originalRenderNeko = renderNeko;
renderNeko = function(t) {
  t.selected = true;
  originalRenderNeko(t);
  const check = document.createElement('input');
  check.type = 'checkbox'; check.checked = true; check.className = 'neko-selected';
  check.setAttribute('aria-label', 'Select ' + t.name + ' for batch conversion');
  check.onchange = () => { t.selected = check.checked; syncBatch(); };
  $('.neko-card-head', t.card).prepend(check);
  $('.neko-remove', t.card).addEventListener('click', () => queueMicrotask(syncBatch));
  t.card.addEventListener('input', e => {
    if (e.target.matches('.shift-slider,.volume-slider,.manual-effect')) invalidateNeko(t);
  });
  t.card.addEventListener('click', e => {
    if (e.target.closest('.mode-selector,.format-selector')) invalidateNeko(t);
  });
  syncBatch();
};
function invalidateNeko(t) { t.result = null; $('.neko-result',t.card).hidden = true; syncBatch(); }
const originalConvertNeko = convertNeko;
convertNeko = async function(t) {
  const speed=getShift(t),effect=getEffect(t),shift=t.shift,volume=t.volume;
  t.result=null;
  await originalConvertNeko(t);
  const result=$('.neko-result',t.card);
  if (!t.card.isConnected || result.hidden) { syncBatch(); return false; }
  const link=$('.primary',result);
  t.result={blob:await (await fetch(link.href)).blob(),filename:link.download,title:t.exportName||t.name,
    speed,effectSpeed:effect,shift,volume,duration:t.buffer.duration/speed+(t.paddingStart||0)+(t.paddingEnd||0)};
  syncBatch(); return true;
};
function syncBatch() {
  $('#batch-panel').hidden=!nekoTracks.length;
  const selected=nekoTracks.filter(t=>t.selected),ready=selected.filter(t=>t.result);
  $('#neko-select-all').checked=nekoTracks.length>0 && selected.length===nekoTracks.length;
  $('#neko-select-all').indeterminate=selected.length>0 && selected.length<nekoTracks.length;
  if (!batchBusy) $('#batch-status').textContent=`${selected.length} selected · ${ready.length} converted. Apply settings, then convert the selected list.`;
  $('#batch-downloads').hidden=!ready.length;
}
$('#neko-select-all').onchange=e=>{nekoTracks.forEach(t=>{t.selected=e.target.checked;$('.neko-selected',t.card).checked=t.selected;});syncBatch();};
$('#batch-effect').onchange=e=>$('#batch-manual-wrap').hidden=e.target.value!=='manual';
$('#batch-apply').onclick=()=>{
  if(batchBusy)return;
  const shift=+$('#batch-shift').value,volume=+$('#batch-volume').value/100,manual=+$('#batch-manual').value;
  if(!Number.isFinite(shift)||shift< -12||shift>96||!Number.isFinite(volume)||volume<0||volume>1||!Number.isFinite(manual)||manual<=0||manual>16){notify('Use a shift from -12 to 96, a volume from 0 to 100%, and a positive effectSpeed up to 16.');return;}
  const chosen=nekoTracks.filter(t=>t.selected&&!t.busy);
  if(!chosen.length){notify('Select at least one available track.');return;}
  chosen.forEach(t=>{
    if(t.playing)stopNeko();
    const minimum=$('#batch-fit').checked?Math.ceil(12*Math.log2(t.buffer.duration/419)*10)/10:-Infinity;
    t.shift=Math.max(shift,minimum);t.volume=volume;t.linked=$('#batch-effect').value==='linked';t.effect=manual;t.format=$('#batch-format').value;
    const slider=$('.shift-slider',t.card);slider.max=Math.max(24,Math.ceil(t.shift+12));slider.value=t.shift;$('.volume-slider',t.card).value=volume*100;
    invalidateNeko(t);updateNeko(t);
  });
  $('#batch-status').textContent=`Settings applied to ${chosen.length} tracks. Linked effectSpeed is calculated individually for each shift.`;
};
$('#batch-convert').onclick=async()=>{
  if(batchBusy)return;
  if(nekoTracks.some(t=>t.busy)){notify('Wait for the current conversion to finish.');return;}
  const chosen=nekoTracks.filter(t=>t.selected);
  if(!chosen.length){notify('Select at least one track.');return;}
  batchBusy=true;stopNeko();let completed=0;
  $$('#batch-panel input,#batch-panel button,#batch-panel select,.neko-card input,.neko-card button,#neko-files').forEach(e=>e.disabled=true);
  try {
    for(let i=0;i<chosen.length;i++){
      const t=chosen[i];$('#batch-status').textContent=`Converting ${i+1} of ${chosen.length}: ${t.name}`;
      if(await convertNeko(t))completed++;
      $$('.neko-card input,.neko-card button').forEach(e=>e.disabled=true);
    }
  } finally {
    batchBusy=false;
    $$('#batch-panel input,#batch-panel button,#batch-panel select,.neko-card input,.neko-card button,#neko-files').forEach(e=>e.disabled=false);
    syncBatch();$('#batch-status').textContent=`${completed} of ${chosen.length} tracks converted. Download the ZIP for audio and matching config values.`;
  }
};
function batchConfig(){return nekoTracks.filter(t=>t.selected&&t.result).map(t=>({title:t.result.title,file:t.result.filename,assetId:0,effectSpeed:+t.result.effectSpeed.toFixed(6),exportSpeed:+t.result.speed.toFixed(6),shiftSemitones:t.result.shift,durationSeconds:+t.result.duration.toFixed(3)}));}
function saveBlob(blob,name){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
$('#batch-config').onclick=()=>saveBlob(new Blob([JSON.stringify(batchConfig(),null,2)],{type:'application/json'}),'nekodj-track-values.json');
function crc32(data){let crc=0xffffffff;for(const byte of data){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
async function makeZip(entries){
  const local=[],central=[];let offset=0;
  for(const entry of entries){
    const name=new TextEncoder().encode(entry.name),data=new Uint8Array(await entry.blob.arrayBuffer()),crc=crc32(data),head=new Uint8Array(30+name.length),v=new DataView(head.buffer);
    v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x0800,true);v.setUint32(14,crc,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,name.length,true);head.set(name,30);local.push(head,data);
    const tail=new Uint8Array(46+name.length),t=new DataView(tail.buffer);t.setUint32(0,0x02014b50,true);t.setUint16(4,20,true);t.setUint16(6,20,true);t.setUint16(8,0x0800,true);t.setUint32(16,crc,true);t.setUint32(20,data.length,true);t.setUint32(24,data.length,true);t.setUint16(28,name.length,true);t.setUint32(42,offset,true);tail.set(name,46);central.push(tail);offset+=head.length+data.length;
  }
  const end=new Uint8Array(22),e=new DataView(end.buffer);e.setUint32(0,0x06054b50,true);e.setUint16(8,entries.length,true);e.setUint16(10,entries.length,true);e.setUint32(12,central.reduce((n,a)=>n+a.length,0),true);e.setUint32(16,offset,true);return new Blob([...local,...central,end],{type:'application/zip'});
}
$('#batch-zip').onclick=async()=>{
  const button=$('#batch-zip');button.disabled=true;button.textContent='Building ZIP…';
  try{
    const tracks=nekoTracks.filter(t=>t.selected&&t.result),config=batchConfig();
    const entries=tracks.map((t,i)=>({name:String(i+1).padStart(2,'0')+' - '+t.result.filename.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_'),blob:t.result.blob}));
    config.forEach((c,i)=>c.file=entries[i].name);
    const lua='-- TEMPLATE: replace assetId = 0 with your uploaded Roblox audio IDs.\n-- Adapt these entries to your NekoDJ config schema.\nreturn {\n'+config.map(c=>`  { title = ${JSON.stringify(c.title)}, assetId = 0, effectSpeed = ${c.effectSpeed.toFixed(6)} },`).join('\n')+'\n}\n';
    entries.push({name:'nekodj-track-values.json',blob:new Blob([JSON.stringify(config,null,2)])},{name:'nekodj-config-template.lua',blob:new Blob([lua])});
    saveBlob(await makeZip(entries),'nekodj-ready.zip');
  }catch(e){notify('Could not build the ZIP: '+e.message);}finally{button.disabled=false;button.textContent='Download audio + config ZIP ↓';}
};
const prepButton=document.createElement('button');prepButton.id='prep-selected';prepButton.className='secondary';prepButton.textContent='Split & prep for NekoDJ →';$('#export-button').after(prepButton);
prepButton.onclick=async()=>{const previous=$('#export-format').value;$('#export-format').value='flac';state.exports=null;try{await $('#export-button').onclick();if(state.exports)await $('#send-neko').onclick();}finally{$('#export-format').value=previous;$('#export-format').onchange({target:$('#export-format')});}};
