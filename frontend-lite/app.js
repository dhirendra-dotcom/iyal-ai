import {consumeSse, canOfferOutcome, safeArtifactUrl, confirmedCapability, starterFromHash} from './core.js';
import {mountStlViewer} from './stl-viewer.js';

const $ = id => document.getElementById(id);
const state = {session:null, busy:false, files:[], capabilities:new Set(), active:new Map(), turn:{}, workspaceViewer:null, inlineViewers:new Set(), controller:null, recorder:null, uploads:{}, measured:{}, rejected:{}, measureLabels:{}, capture:null, booking:null};
const USER_KEY='iyal_user_id';
const UI_BUILD='v0.13.2';
document.body.dataset.uiBuild=UI_BUILD;
// Hero slideshow: crossfade every few seconds; static for reduced motion, paused while hidden (tab or mobile layout).
(()=>{const slides=[...document.querySelectorAll('[data-slideshow] .slide')];if(slides.length<2||matchMedia('(prefers-reduced-motion: reduce)').matches)return;let i=0;setInterval(()=>{if(document.hidden||!slides[i].offsetParent)return;slides[i].classList.remove('is-active');i=(i+1)%slides.length;slides[i].classList.add('is-active');},5000);})();
const riskLabels={GREEN:'Low-risk everyday adaptation · Check physical fit before use',AMBER:'Professional review recommended',RED:'Professional assessment needed'};
const strategyNames={change_technique:'Technique change',buy_existing:'Existing product',modify_object:'Modify existing object',custom_cad:'Custom design',standard_adaptation:'Standard adaptation',professional_help:'Professional support'};
const titles = {search_existing_products:'Checking existing options', present_adaptation_options:'Finding your adaptation', present_measurement_plan:'Planning measurements', measure_object_from_capture:'Measuring the fitting area', register_manual_measurement:'Recording your measurement', register_usage_video:'Adding real-use context', validate_design:'Checking design constraints', generate_3d_design:'Building your prototype', generate_usage_preview:'Creating the illustrative preview', generate_environment_preview:'Visualizing the environment change', assess_support_need:'Assessing fit confidence', offer_product_support:'Preparing fit-review options'};
const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = String(text); if (cls) node.className = cls; return node; };
function clear(id) { $(id).replaceChildren(); return $(id); }
function card(id, title) { const box = clear(id); box.className = 'card'; box.append(el('h3',title)); $('empty').hidden = true; spotlight(box); return box; }
// Bring the card that just changed into view and flash it, so updates are never off-screen.
function spotlight(box) {
  box.classList.remove('updated'); void box.offsetWidth; box.classList.add('updated');
  if(!matchMedia('(min-width: 761px)').matches) return;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  requestAnimationFrame(()=>box.scrollIntoView({block:'nearest',behavior:reduced?'auto':'smooth'}));
}
function scrollChat() { $('messages').scrollTop = $('messages').scrollHeight; }
function formatReply(node,text) {
  node.replaceChildren();
  for(const line of String(text).split('\n')) {
    const paragraph=el('div');
    const normalized=line.replace(/^#{1,6}\s+/,'').replace(/^[-*]\s+/,'• ');
    for(const part of normalized.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)) {
      if(part.startsWith('**') && part.endsWith('**')) paragraph.append(el('strong',part.slice(2,-2)));
      else if(part.startsWith('`') && part.endsWith('`')) paragraph.append(el('code',part.slice(1,-1)));
      else paragraph.append(document.createTextNode(part));
    }
    node.append(paragraph.childNodes.length ? paragraph : el('br'));
  }
}
function message(text, role='assistant') { const node=el('article',text,`message ${role}`); $('messages').append(node); scrollChat(); return node; }
function report(error) { message(error.message || String(error),'error'); }
function url(path) { return safeArtifactUrl(path,location.origin); }
function endpoint(suffix) { return `/api/sessions/${encodeURIComponent(state.session.session_id)}/${suffix}`; }
function stableUserId() {
  let id='';
  try { id=localStorage.getItem(USER_KEY) || ''; } catch {}
  if(!/^usr-[a-z0-9-]{8,120}$/.test(id)) {
    const token=globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    id=`usr-${token.toLowerCase()}`.slice(0,124);
    try { localStorage.setItem(USER_KEY,id); } catch {}
  }
  return id;
}
function setPrompt(text) { $('prompt').value=text.slice(0,4000); $('prompt').focus(); }
function visibleStrategyTitle(option) {
  const strategy=String(option?.strategy || '').trim();
  const raw=String(option?.title || '').trim();
  const internal=/^[a-z0-9_]+:?$/i.test(raw) || raw.toLowerCase().replace(/:$/,'')===strategy.toLowerCase();
  return (!raw || internal) ? (strategyNames[strategy] || 'Adaptation option') : raw.replace(/:\s*$/,'');
}
function nonEmpty(value) { return typeof value==='string' ? value.trim() : value; }
async function request(path, options={}) {
  const response = await fetch(path,options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { const data=await response.json(); detail=typeof data.detail==='string'?data.detail:(data.message || detail); } catch {}
    throw new Error(detail);
  }
  return response;
}
async function post(path, body, signal) { return request(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal}); }
function controls() {
  const recording = state.recorder?.state === 'recording';
  const micSupported = Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  $('send').disabled=!state.session || state.busy || recording;
  for (const id of ['attach','photo']) $(id).disabled=state.busy || recording;
  $('dictate').disabled=!state.session || state.busy || !micSupported;
  $('dictate').textContent=recording ? '■ Stop recording' : '🎙 Record voice';
  $('dictate').classList.toggle('recording',recording);
  $('dictate').setAttribute('aria-pressed',recording ? 'true' : 'false');
  $('dictate').title=micSupported ? 'Record voice and convert it to editable text' : 'Microphone recording is not supported in this browser';
  $('stop').hidden=!state.busy;
  $('prompt').disabled=state.busy;
  $('connection').textContent=state.session ? 'Connected' : 'Offline';
}
async function connect() {
  $('retry').hidden=true; $('connection').textContent='Connecting…';
  try { state.session=await (await post('/api/sessions',{user_id:stableUserId()})).json(); }
  catch(error) { report(new Error(`Could not connect. ${error.message}`)); $('retry').hidden=false; }
  controls();
}
function updateCapabilities(tool,response) {
  const capability=confirmedCapability(tool,response);
  if (capability) state.capabilities.add(capability);
  const box=clear('capabilities');
  if(!state.capabilities.size) box.textContent='Capabilities will appear here as they are used.';
  for(const name of state.capabilities) box.append(el('span',`✦ ${name}`,'capability-chip'));
  $('gemini').querySelector('summary').textContent=state.capabilities.size ? `✦ With Gemini · ${state.capabilities.size} capabilities used` : '✦ With Gemini';
}
function setJourney(stage) {
  const order=['understand','options','fit','design','next'];
  // Progress only moves forward, and only as far as the work actually done.
  state.journey=Math.max(state.journey || 0,order.indexOf(stage));
  const current=state.journey;
  document.querySelectorAll('#journey [data-stage]').forEach(item=>{
    const index=order.indexOf(item.dataset.stage);
    item.classList.toggle('complete',index<current);
    item.classList.toggle('active',index===current);
  });
}
function journeyForTool(tool) {
  if(tool==='search_existing_products' || tool==='present_adaptation_options') return 'options';
  if(['present_measurement_plan','measure_object_from_capture','register_manual_measurement','register_usage_video'].includes(tool)) return 'fit';
  if(['validate_design','generate_3d_design','generate_usage_preview','generate_environment_preview'].includes(tool)) return 'design';
  if(['assess_support_need','offer_product_support'].includes(tool)) return 'next';
  return 'understand';
}
function phase(text) { state.phase=text; $('solution-status').textContent=text; tick(); }
function tick() { $('activity').textContent=state.busy ? `${state.active.size ? [...state.active.values()].join(' · ') : state.phase || 'Preparing'} · ${Math.floor((Date.now()-state.started)/1000)}s` : ''; }
function addFiles(files) {
  for (const file of files) {
    if (state.files.length >= 8) { report(new Error('Attach up to eight files per message.')); break; }
    if (!['image/jpeg','image/png','image/webp','video/mp4','video/webm','video/quicktime'].includes(file.type)) { report(new Error('Choose a JPG, PNG, WebP, MP4, WebM or MOV file.')); continue; }
    if (file.size > 80*1024*1024) { report(new Error('Please use files smaller than 80 MB.')); continue; }
    state.files.push(file);
  }
  renderAttachments();
}
function renderAttachments() {
  clear('attachments');
  state.files.forEach((file,index) => {const b=el('button',`${file.name} ×`,'attachment'); b.type='button'; b.disabled=state.busy; b.setAttribute('aria-label',`Remove ${file.name}`); b.onclick=()=>{state.files.splice(index,1);renderAttachments();}; $('attachments').append(b);});
}
function showInputs(files, userNode) {
  const area=clear('solution-input');
  for(const file of files) {
    const src=URL.createObjectURL(file); const media=el(file.type.startsWith('video/')?'video':'img');
    media.src=src; media.className='input-thumb'; media.setAttribute('aria-label',file.name);
    if(media.tagName==='IMG') media.alt=file.name; else media.controls=true;
    area.append(media); userNode.append(el('small',`\nAttached: ${file.name}`));
    // Keep URLs until the next input replaces this area.
    state.inputUrls.push(src);
  }
}
state.inputUrls=[];
function showRecommendation(options) {
  state.options=options;
  // v0.12: preserve every existing Solution Workspace section. Market research,
  // grounded sources, measurements and later artifacts must remain visible as
  // the agent progresses through the same or subsequent turns.
  Object.assign(state.turn,{strategy:options.recommended_strategy,risk:options.risk_level,requiresMeasurement:options.requires_measurement,requiresUsageEvidence:options.usage_evidence_required});
  const selected=(options.options || []).find(o=>o.strategy===options.recommended_strategy);
  const box=card('recommendation',visibleStrategyTitle(selected) || 'Your adaptation');
  box.append(el('span',riskLabels[options.risk_level] || (options.professional_review_recommended ? 'Professional review recommended' : 'Check physical fit before use'),'badge'));
  box.append(el('p',options.problem_summary || options.user_goal || ''));
  const facts=el('dl',undefined,'facts');
  for (const [label,value] of [['Goal',options.user_goal],['Task',options.task],['Object / space',options.object_name],['Barrier',options.functional_barrier]]) { const row=el('div'); row.append(el('dt',label),el('dd',value || '—')); facts.append(row); }
  box.append(facts);
  if((options.options || []).length>1) {
    const list=el('ul',undefined,'options-list');
    for(const option of options.options) {
      const item=el('li',visibleStrategyTitle(option));
      if(option===selected) {item.className='recommended';item.append(el('span','Recommended','option-tag'));}
      list.append(item);
    }
    box.append(el('span','OPTIONS CONSIDERED','eyebrow'),list);
  }
  const rationale=el('details'); rationale.append(el('summary','Why this adaptation?'),el('p',options.decision_rationale || selected?.rationale || ''),el('p',options.risk_reason || ''));
  for(const feature of options.design_features || []) rationale.append(el('p',`${feature.feature}: ${feature.value}${feature.reason ? ` — ${feature.reason}` : ''}`));
  for(const other of options.options || []) if(other!==selected && nonEmpty(other.rationale)) rationale.append(el('p',`${visibleStrategyTitle(other)}: ${other.rationale}`));
  box.append(rationale);
  if(options.market_check_skipped) {const market=card('market','Your custom-design path'); market.append(el('p','Existing-product comparison skipped at your request. Personal fit and design checks still apply.'));}
  if(options.recommended_strategy==='custom_cad') hideNextStep();
}
// Bridge from existing options to a personal design, for objects the grip-sleeve CAD supports.
const NEXT_STEP_STRATEGIES=['buy_existing','standard_adaptation','modify_object','change_technique'];
const GRIP_OBJECTS=/spoon|fork|knife|utensil|cutlery|pen|pencil|toothbrush|brush|hand tool/i;
function showNextStep() {
  const options=state.options;
  if(!options || state.designShown || !NEXT_STEP_STRATEGIES.includes(options.recommended_strategy) || options.context_type!=='object' || !GRIP_OBJECTS.test(options.object_name || '')) return;
  const box=card('next-step','What’s next');
  box.classList.add('next-step');
  box.append(el('p',`Prefer something shaped around your hand? Iyal can design a custom grip sleeve for your own ${String(options.object_name).toLowerCase()} from a few simple measurements.`));
  const button=el('button','Design a custom grip →','primary');button.type='button';
  button.onclick=()=>setPrompt('I would prefer something personalized and easier for my hand to hold. Can you create a custom grip?');
  box.append(button,el('small','Fills in your message. Nothing is sent until you press Send.','muted'));
  // Offer the same step directly under Iyal's reply, where the user is reading.
  state.chatNextStep?.remove();
  if(state.turn.node?.isConnected) {
    const actions=el('div',undefined,'artifact-actions chat-next-step');
    const inline=el('button','Design a custom grip →','primary');inline.type='button';inline.onclick=button.onclick;
    actions.append(inline);state.turn.node.after(actions);state.chatNextStep=actions;scrollChat();
  }
}
function hideNextStep() { clear('next-step'); $('next-step').className=''; state.chatNextStep?.remove(); state.chatNextStep=null; }
// Between the research and Gemini's recorded recommendation the panel would otherwise look stale.
function showComparing() {
  state.comparing={previous:[...$('recommendation').childNodes],className:$('recommendation').className};
  const box=card('recommendation','Comparing your options');
  box.append(el('span','In progress','badge'),el('p','Gemini is weighing the options from the research against your need. The recommendation and options considered will appear here.'));
}
function endComparing() {
  // If no recommendation arrived this turn, restore whatever the card showed before.
  if(!state.comparing) return;
  const box=$('recommendation');box.replaceChildren(...state.comparing.previous);box.className=state.comparing.className;state.comparing=null;
}
function appendGroundingSources(container, sources) {
  const valid=(sources || []).filter(source=>nonEmpty(source?.url));
  if(!valid.length) return;
  const details=el('details',undefined,'grounding-sources');
  details.append(el('summary',`Search sources · ${valid.length}`));
  for(const source of valid) {
    try {
      const target=new URL(source.url);
      if(!['https:','http:'].includes(target.protocol)) continue;
      const a=el('a',source.title || target.hostname);
      a.href=target.href;a.target='_blank';a.rel='noopener noreferrer';
      details.append(a,el('br'));
    } catch {}
  }
  container.append(details);
}
function showMarketStatus(status, result={}) {
  const box=card('market','Market research');
  const sourceCount=Number(result.source_count || (result.sources || []).length || 0);
  if(status==='progress') {
    box.append(el('span','In progress','badge'),el('p','Checking current existing options with Google Search grounding.'));
    return;
  }
  if(status==='reused') {
    box.append(el('span','Completed','badge'),el('p','Using the market research already shown in the conversation.'));
    return;
  }
  if(status==='completed') {
    box.append(el('span',result.cache_hit?'Completed · recent result':'Completed','badge'),el('p',sourceCount ? `${sourceCount} grounded source${sourceCount===1?'':'s'} found. Full research is shown in the conversation.` : 'Research completed. Full result is shown in the conversation.'));
    return;
  }
  box.append(el('span','Could not complete','badge'),el('p','Live market research did not complete successfully. Details are shown in the conversation.'));
}
function showMarketResearch(result) {
  if(state.turn.marketResearchShown) return;
  state.turn.marketResearchShown=true;
  const box=el('article',undefined,'message assistant market-research-message');
  box.append(el('span','MARKET RESEARCH · GOOGLE SEARCH GROUNDED','eyebrow'),el('h3','Existing options'));
  const body=el('div',undefined,'market-research-body');
  formatReply(body,result.market_text || result.error || 'Live market research could not be completed.');
  box.append(body);
  appendGroundingSources(box,result.sources);
  if(nonEmpty(result.disclaimer)) box.append(el('small',result.disclaimer,'muted'));
  $('messages').append(box);
  scrollChat();
}
function showMeasurements(plan) {
  const box=card('measurements','Measurements for your fit');
  for(const item of plan.measurements || []) if(item.dimension) state.measureLabels[item.dimension]=item.label || item.dimension;
  for(const instruction of plan.common_instructions || []) box.append(el('p',instruction));
  const list=el('ul');
  for(const item of plan.measurements || []) list.append(el('li',`${item.label}${item.required?' (needed)':''}: ${item.instruction}`));
  box.append(list);
  const a=el('a','Optional calibration marker');a.href='/api/calibration/marker.svg';a.target='_blank';a.rel='noopener';box.append(a);
}
const DIMENSION_LABELS={interface_width_mm:'Handle width',interface_depth_mm:'Handle thickness',available_length_mm:'Available length',object_length_mm:'Object length'};
const SOURCE_LABELS={calibrated_photo:'From photo · A4-calibrated',user_measurement:'You entered',trusted_known_dimension:'Known dimension'};
function dimensionLabel(dimension) { return state.measureLabels[dimension] || DIMENSION_LABELS[dimension] || dimension; }
function showMeasuring() {
  const box=card('measured','Measuring from your photo');
  box.append(el('span','In progress','badge'));
  const steps=el('ol',undefined,'measure-steps');
  for(const step of ['Gemini vision locates the part of the object to fit','The A4 sheet is detected and the perspective corrected','The located outline is converted to millimetres']) steps.append(el('li',step));
  box.append(steps,el('small','Iyal never guesses a dimension. If the photo is unclear, it will ask for a retake or a ruler measurement.','muted'));
}
function recordMeasurements(result) {
  const geometry=result?.object_geometry;
  for(const [dimension,item] of Object.entries(geometry?.measurements || {})) if(item && Number.isFinite(Number(item.value_mm))) state.measured[dimension]=item;
  if(geometry?.rejected_readings) state.rejected={...geometry.rejected_readings};
}
function showMeasured(result={}) {
  const box=card('measured','Your measurements');
  const status=result.status;
  if(status==='recapture_required') box.append(el('span','Photo retake needed','badge'),el('p',result.reason || 'The target was not fully measurable in this photo.'));
  else if(status==='error') box.append(el('span','Could not measure','badge'),el('p','The photo could not be measured. You can retake it or type the measurement in millimetres.'));
  const dimensions=[...new Set([...Object.keys(state.measured),...Object.keys(state.rejected)])];
  if(dimensions.length) {
    const table=el('dl',undefined,'measure-table');
    for(const dimension of dimensions) {
      const item=state.measured[dimension];
      const rejected=state.rejected[dimension];
      const row=el('div');
      if(!item) {
        // An implausible photo reading is shown crossed out, never as a usable value.
        row.className='rejected';
        row.append(el('dt',dimensionLabel(dimension)),el('dd',`${Number(rejected.value_mm).toFixed(1)} mm`),el('small','Rejected: implausible photo reading. Measure with a ruler and type the value.'));
        table.append(row);continue;
      }
      const source=[SOURCE_LABELS[item.source] || 'Recorded'];
      if(item.approximate) source.push('approximate');
      // The photo score rates how well the A4 sheet was detected, not this reading.
      if(item.source==='calibrated_photo' && Number.isFinite(Number(item.confidence))) source.push(`A4 detected ${Number(item.confidence).toFixed(2)}`);
      if(rejected && item.source!=='calibrated_photo') source.push(`photo reading ${Number(rejected.value_mm).toFixed(1)} mm rejected`);
      row.append(el('dt',dimensionLabel(dimension)),el('dd',`${Number(item.value_mm).toFixed(1)} mm`),el('small',source.join(' · ')));
      table.append(row);
    }
    box.append(table);
  } else if(!['error','recapture_required'].includes(status)) box.append(el('p',status==='manual_preferred'?'This dimension is easier to measure with a ruler. Type it in millimetres.':'No measurements recorded yet.'));
  const capture=state.capture;
  if(capture?.src && capture.box?.length===4) {
    const figure=el('figure',undefined,'capture-figure');
    const img=el('img');img.src=capture.src;img.alt='Your measurement photo with the located target outlined';
    const [ymin,xmin,ymax,xmax]=capture.box.map(v=>Math.max(0,Math.min(1000,Number(v)))/10);
    const outline=el('span',undefined,'capture-box');
    Object.assign(outline.style,{top:`${ymin}%`,left:`${xmin}%`,height:`${Math.max(0,ymax-ymin)}%`,width:`${Math.max(0,xmax-xmin)}%`});
    const caption=Object.keys(state.rejected).length
      ? `Gemini located the ${capture.label || 'target'}; one reading was implausible, so Iyal asked for a ruler measurement instead of guessing.`
      : `Gemini located the ${capture.label || 'target'}; A4 calibration converted it to millimetres.`;
    figure.append(img,outline,el('figcaption',caption));
    box.append(figure);
  }
}
function handleMeasurementResult(tool,result) {
  recordMeasurements(result);
  if(tool==='measure_object_from_capture') {
    // A call without a photo in this turn is a missing input, not a failed measurement.
    if(!state.turn.hasPhoto || result.status==='photo_required') return;
    const uri=result.object_geometry?.top_capture_uri;
    const box=result.segmentation?.box_2d;
    if(result.status==='ok' && box) state.capture={src:state.uploads[uri],box,label:result.segmentation?.label || result.target_region};
    showMeasured(result);
  } else if(result.status==='ok') showMeasured();
}
function designSummary(data) {
  const design=data.design || {};
  const parts=[];
  if(nonEmpty(design.profile)) parts.push(`Profile: ${design.profile}`);
  if(nonEmpty(design.texture)) parts.push(`Texture: ${design.texture}`);
  const dims=[design.outer_width_mm,design.outer_depth_mm,design.grip_length_mm];
  if(dims.every(v=>Number.isFinite(Number(v)))) parts.push(`Size: ${dims.map(v=>Number(v).toFixed(1)).join(' × ')} mm`);
  if(Number(design.angle_deg)>0) parts.push(`Angle: ${Number(design.angle_deg).toFixed(0)}°`);
  if(design.palm_flare===true) parts.push('Palm support');
  return parts;
}
function inlineArtifact(title, eyebrow='GENERATED FOR THIS TURN') {
  const box=el('article',undefined,'message assistant artifact-message');
  box.append(el('span',eyebrow,'eyebrow'),el('h3',title));
  $('messages').append(box);
  scrollChat();
  return box;
}
function refinementAction(container) {
  const actions=el('div',undefined,'artifact-actions');
  const refine=el('button','Refine this design');refine.type='button';
  refine.onclick=()=>setPrompt('Can you refine the design to make the grip slightly wider and add more palm support, while keeping it securely fitted to the spoon?');
  actions.append(refine);container.append(actions);
}
async function mountInlineViewer(container, stlPath) {
  try {
    const cleanup=await mountStlViewer(container,url(stlPath));
    if(container.isConnected) state.inlineViewers.add(cleanup); else cleanup();
  } catch(error) { container.append(el('p',error.message,'error')); }
}
// The interactive 3D viewer and preview stay in the conversation; the workspace keeps a
// compact summary of the current design that links back to them.
function showDesignSummary(data, inline) {
  const box=card('design',`Current design · version ${data.design_version}`);
  box.append(el('span',data.design?.demo_only?'Demonstration only':'Design checks passed','badge'));
  const chips=el('div',undefined,'design-chips');
  for(const item of designSummary(data)) chips.append(el('span',item,'design-chip'));
  if(chips.childNodes.length) box.append(chips);
  const used=Object.entries(state.measured).map(([dimension,item])=>`${dimensionLabel(dimension)} ${Number(item.value_mm).toFixed(1)} mm`);
  if(used.length) box.append(el('p',`Fitted to: ${used.join(' · ')}`));
  const actions=el('div',undefined,'artifact-actions');
  const view=el('button','View 3D in conversation');view.type='button';view.onclick=()=>inline.scrollIntoView({block:'start',behavior:'smooth'});
  const download=el('a','Download STL');download.href=url(data.stl_path);download.download=`iyal-grip-v${data.design_version}.stl`;download.className='button-link';
  actions.append(view,download);
  box.append(actions,el('small','Physical fit is unverified until the printed prototype is tried.','muted'));
  state.designCard=box;
}
async function showDesign(data) {
  state.workspaceViewer?.(); state.workspaceViewer=null;
  Object.assign(state.turn,{designVersion:data.design_version,demoOnly:Boolean(data.design?.demo_only)});
  const warning=data.design?.demo_only?'Demonstration only. Not a personal fit.':'Physical fit is unverified. Check dimensions, material and manufacturing before use.';

  const inline=inlineArtifact(`Your personalized 3D design · version ${data.design_version}`);
  inline.dataset.artifact='design';
  inline.append(el('p',warning));
  const chips=el('div',undefined,'design-chips');
  for(const item of designSummary(data)) chips.append(el('span',item,'design-chip'));
  if(chips.childNodes.length) inline.append(chips);
  const inlineViewer=el('div',undefined,'inline-viewer');inline.append(inlineViewer);
  refinementAction(inline);
  showDesignSummary(data,inline);
  await mountInlineViewer(inlineViewer,data.stl_path);
  scrollChat();
}
function showPreview(data) {
  // Generated preview images belong to the conversation, not the right-side workspace.
  clear('preview'); $('preview').className='';
  const label=data.label || 'Illustrative preview';
  const disclaimer=data.disclaimer || 'Illustrative concept only; physical fit is not verified.';

  const inline=inlineArtifact(label,'ILLUSTRATIVE PREVIEW');
  inline.dataset.artifact='preview';
  const inlineImg=el('img');inlineImg.src=url(data.image_path);inlineImg.alt=label;inlineImg.className='preview-image inline-preview-image';
  inline.append(inlineImg,el('small',disclaimer));
  if(state.designCard?.isConnected) {
    state.designCard.querySelector('.design-thumb')?.remove();
    const thumb=el('img');thumb.src=inlineImg.src;thumb.alt=label;thumb.className='design-thumb';thumb.onclick=()=>inline.scrollIntoView({block:'start',behavior:'smooth'});
    state.designCard.insertBefore(thumb,state.designCard.children[1]);
    spotlight(state.designCard);
  }
  scrollChat();
}
function handleEvent({type,data}) {
  if(type==='connected' || type==='run_started') phase('Gemini is preparing its response');
  if(type==='tool_start') {state.active.set(data.tool,titles[data.tool] || 'Working on your adaptation'); setJourney(journeyForTool(data.tool)); if(data.tool==='search_existing_products') showMarketStatus('progress'); if(data.tool==='measure_object_from_capture' && state.turn.hasPhoto) showMeasuring(); tick();}
  if(type==='tool_complete') {
    state.active.delete(data.tool); phase('Gemini is preparing the next response'); const result=data.response || {};updateCapabilities(data.tool,result);
    if(result.error || result.status==='error' || result.valid===false) $('solution-status').textContent=String(result.error || 'This step needs revision.');
    if(data.tool==='present_adaptation_options' && result.status==='ready') {state.turn.optionsShown=true;state.comparing=null;showRecommendation(result);}
    if(data.tool==='search_existing_products') {
      // The context question comes first; no search happened, so remove the progress card.
      if(result.status==='context_question_first') {clear('market');$('market').className='';}
      // v0.13.2: a reused/capped search adds no new conversation message.
      else if(result.reused) showMarketStatus('reused',result);
      else {showMarketResearch(result);showMarketStatus(result.status==='ready'?'completed':'failed',result);if(result.status==='ready' && !state.turn.optionsShown) showComparing();}
    }
    if(data.tool==='present_measurement_plan' && result.status==='ready') {hideNextStep();showMeasurements(result);}
    if(['measure_object_from_capture','register_manual_measurement'].includes(data.tool)) handleMeasurementResult(data.tool,result);
    if(data.tool==='register_usage_video' && result.status==='registered') state.turn.usageVideoReceived=true;
    if(data.tool==='offer_product_support' && result.status==='ready') {state.turn.support=result;setJourney('next');showFitReview(result);}
    if(data.tool==='offer_product_support' && result.status==='professional_required') showFitReview(result);
  }
  if(type==='design_ready') {setJourney('design'); state.designShown=true; hideNextStep(); void showDesign(data);}
  if(type==='preview_ready' || type==='environment_preview_ready') {setJourney('design'); showPreview(data);}
  if(type==='assistant_delta' || type==='final') {
    phase('Writing your response');
    if(!state.turn.node) state.turn.node=message('');
    state.turn.node.textContent=type==='final'?data.text:state.turn.node.textContent+data.text;
    if(type==='final') {state.turn.final=true;formatReply(state.turn.node,data.text);}
    scrollChat();
  }
  if(type==='error') {state.turn.failed=true;report(new Error(data.message));}
  if(type==='run_complete') state.turn.complete=true;
}
async function submit(event) {
  event.preventDefault();const text=$('prompt').value.trim();
  if(state.busy || !state.session || (!text && !state.files.length) || state.recorder?.state==='recording') return;
  document.querySelectorAll('.closing').forEach(n=>n.remove());
  // v0.11: once the user starts the conversation, reclaim vertical space from
  // the introductory strip while keeping the two-column width split unchanged.
  document.body.classList.add('conversation-active');
  const files=[...state.files];state.busy=true;state.started=Date.now();state.turn={};state.options=null;state.active.clear();state.controller=new AbortController();controls();renderAttachments();
  document.querySelector('.hero').classList.add('compact');phase('Uploading your input');const timer=setInterval(tick,1000);
  try {
    const refs=await Promise.all(files.map(async file=>{const form=new FormData();form.append('file',file);const kind=file.type.startsWith('video/')?'video':'image';const response=await request(`${endpoint(`artifacts/${kind}`)}?user_id=${encodeURIComponent(state.session.user_id)}`,{method:'POST',body:form,signal:state.controller.signal});return (await response.json()).artifact;}));
    state.turn.hasPhoto=files.some(file=>file.type.startsWith('image/'));
    // Keep a local preview per uploaded photo so measurement results can show Gemini's located target on it.
    refs.forEach((ref,index)=>{if(ref?.uri && files[index].type.startsWith('image/')) state.uploads[ref.uri]=URL.createObjectURL(files[index]);});
    const userNode=message(text,'user');
    if(files.length) {state.inputUrls.forEach(URL.revokeObjectURL);state.inputUrls=[];showInputs(files,userNode);}
    $('prompt').value='';state.files=[];renderAttachments();phase('Connecting to Gemini');
    const response=await post(endpoint('chat'),{user_id:state.session.user_id,message:text,attachments:refs},state.controller.signal);
    if(!response.body) throw new Error('No response stream was received.');
    try { await consumeSse(response.body,handleEvent); }
    catch(error) {
      // Some connections drop while closing the stream. Once run_complete has arrived every
      // event was received, so the turn is finished; otherwise the turn really was cut short.
      if(!state.turn.complete || error.name==='AbortError') throw error.name==='AbortError' ? error : new Error('The connection dropped while Iyal was working. Your earlier results are kept; send your message again to continue.');
    }
    if(!state.turn.complete) throw new Error('The response was interrupted. Please send your message again.');
    if(!state.turn.failed) {phase('Your workspace is up to date.');if(state.turn.support && state.turn.final && !state.booking) showSupport(state.turn.support);if(state.turn.final) showNextStep();if(canOfferOutcome(state.turn)) {state.outcomeVersion=state.turn.designVersion;showFollowUp();}}
  } catch(error) {state.controller.abort();state.turn.failed=true;report(error.name==='AbortError'?new Error('Stopped. You can continue when you’re ready.'):error);$('solution-status').textContent='This turn did not finish. Your earlier results are still available.';}
  finally {endComparing();clearInterval(timer);state.busy=false;state.controller=null;state.active.clear();controls();renderAttachments();tick();$('prompt').focus();}
}
const VISIT_TYPES={in_person:'In person',video_review:'Video review'};
const RATING_BADGES={GREEN:'Low fit risk · optional review',AMBER:'Fit review recommended',RED:'Professional visit required'};
function visitDate(value) {
  const date=new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short',year:'numeric'});
}
// Fit review in the workspace: the reasons appear only when the rating or evidence crosses a threshold.
function showFitReview(offer) {
  state.supportOffer=offer;
  const early=offer.status==='professional_required';
  const rating=early ? 'RED' : (offer.fit_risk_rating || 'GREEN');
  const box=card('fit-review','Fit review');
  box.classList.add('fit-review',`rating-${rating.toLowerCase()}`);
  box.append(el('span',early?'Professional assessment needed':(RATING_BADGES[rating] || rating),'badge rating-badge'));
  box.append(el('p',early ? (offer.message || 'An appropriate qualified professional should assess this first.') : (offer.title || ''),'fit-title'));
  if(early || offer.show_reasons) {
    box.append(el('span',rating==='GREEN'?'WHAT GEMINI NOTED':'WHY GEMINI RECOMMENDS A REVIEW','eyebrow'));
    const list=el('ul',undefined,'fit-reasons');
    for(const concern of offer.gemini_concerns || []) list.append(el('li',concern,'concern'));
    for(const reason of offer.evidence_reasons || []) list.append(el('li',reason,'evidence'));
    if(list.childNodes.length) box.append(list);
    if(nonEmpty(offer.reason)) box.append(el('p',offer.reason,'fit-quote'));
    if(nonEmpty(offer.rating_note)) box.append(el('small',offer.rating_note,'muted'));
  }
  if(early) return;
  if(state.booking) {box.append(el('p','Visit booked. Details are below.','muted'));return;}
  const book=el('button',rating==='RED'?'Book a professional visit →':'Book a fit review →',rating==='GREEN'?'':'primary');book.type='button';
  book.onclick=()=>{let form=document.querySelector('.support-booking');if(!form?.isConnected) form=showSupport(offer);form.open=true;form.scrollIntoView({block:'center',behavior:'smooth'});form.querySelector('select')?.focus();};
  box.append(book,el('small','Not a medical consultation.','muted'));
}
function showSupport(offer) {
  document.querySelector('.support-booking')?.remove();
  const details=el('details',undefined,'closing support-booking');details.open=true;details.append(el('summary',offer.title || 'Arrange product support'));
  details.append(el('p',offer.description || 'Review fit and practical setup. This is not a medical consultation.'));
  const form=el('form');const date=el('select');const time=el('select');const type=el('select');const email=el('input');email.type='email';email.required=true;email.maxLength=320;
  function field(label,input) {const row=el('label',label);row.append(input);form.append(row);}
  for(const day of offer.available_dates || []) {const option=el('option',day.label);option.value=day.date;date.append(option);}
  function times(){time.replaceChildren();for(const slot of (offer.available_dates || []).find(d=>d.date===date.value)?.times || []) {const option=el('option',slot);option.value=slot;time.append(option);}}
  date.onchange=times;times();for(const value of offer.visit_types || []) {const option=el('option',VISIT_TYPES[value] || value);option.value=value;type.append(option);}
  field('Date',date);field('Time',time);field('Review type',type);field('Email for confirmation',email);
  const save=el('button','Confirm visit & email details','primary');save.disabled=!date.options.length || !time.options.length || !type.options.length;const status=el('p');status.setAttribute('role','status');form.append(save,status);details.append(form);
  form.onsubmit=async event=>{event.preventDefault();save.disabled=true;try {const result=await (await post(endpoint('support/book'),{user_id:state.session.user_id,date:date.value,time_slot:time.value,visit_type:type.value,email:email.value})).json();state.booking=result;details.replaceWith(bookingConfirmation(result));showFollowUp();if(state.supportOffer) showFitReview(state.supportOffer);}catch(error){status.textContent=error.message;save.disabled=false;}};
  $('messages').append(details);scrollChat();
  return details;
}
function bookingConfirmation(booking) {
  const box=el('article',undefined,'message assistant booking-confirmed');
  box.append(el('span','✓ VISIT CONFIRMED','eyebrow'),el('h3','Your fit-review visit is booked'));
  const facts=el('dl',undefined,'facts');
  for(const [label,value] of [['When',`${visitDate(booking.date)} · ${booking.time_slot}`],['Type',VISIT_TYPES[booking.visit_type] || booking.visit_type],['Booking ID',booking.booking_id]]) {const row=el('div');row.append(el('dt',label),el('dd',value));facts.append(row);}
  box.append(facts,el('p','Bring your printed grip sleeve and the spoon it fits. The reviewer will check fit, comfort and setup with you.'));
  box.append(el('small',booking.email_status==='simulated'?'Confirmation email: simulated in this demo.':booking.email_status==='sent'?'A confirmation email is on its way.':'Keep this booking ID; the confirmation email could not be sent.','muted'));
  return box;
}
// After the design: the booked visit (if any) and an outcome check-in, kept in the workspace
// rather than interrupting the conversation before the adaptation has been tried.
function showFollowUp() {
  const box=card('follow-up',state.booking?'Your fit-review visit':'After you’ve tried it');
  if(state.booking) {
    const facts=el('dl',undefined,'facts');
    for(const [label,value] of [['When',`${visitDate(state.booking.date)} · ${state.booking.time_slot}`],['Type',VISIT_TYPES[state.booking.visit_type] || state.booking.visit_type],['Booking ID',state.booking.booking_id]]) {const row=el('div');row.append(el('dt',label),el('dd',value));facts.append(row);}
    box.append(el('span','Confirmed','badge'),facts,el('p','The review checks fit, comfort and setup with your printed prototype.'));
  }
  if(state.outcomeSaved) {box.append(el('p',state.outcomeSaved));return;}
  const later=el('details',undefined,'outcome-later');later.append(el('summary','After you’ve tried it: did the task get easier?'));
  const form=el('form');form.setAttribute('aria-label','Outcome feedback');
  const choices=el('div',undefined,'choices');
  for(const [value,label] of [['much_easier','Much easier'],['slightly_easier','A little easier'],['no_change','No change'],['harder','Harder']]) {const item=el('label');const input=el('input');input.type='radio';input.name='outcome';input.value=value;input.required=true;item.append(input,document.createTextNode(` ${label}`));choices.append(item);}
  const comment=el('textarea');comment.placeholder='Optional: what worked or did not work?';comment.setAttribute('aria-label','Outcome comment');comment.maxLength=1000;const save=el('button','Save outcome','primary');const status=el('p');status.setAttribute('role','status');form.append(choices,comment,save,status);
  form.onsubmit=async event=>{event.preventDefault();save.disabled=true;try {const selected=new FormData(form).get('outcome');const result=await (await post(endpoint('outcomes'),{user_id:state.session.user_id,outcome:selected,comment:comment.value,design_version:state.outcomeVersion})).json();state.outcomeSaved=result.message || 'Your outcome has been saved.';form.replaceChildren(el('p',state.outcomeSaved));}catch(error){status.textContent=error.message;save.disabled=false;}};
  later.append(form);box.append(later);
}
function preferredAudioMime() {
  const candidates=['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg;codecs=opus'];
  if(!window.MediaRecorder?.isTypeSupported) return '';
  return candidates.find(type=>MediaRecorder.isTypeSupported(type)) || '';
}
function audioFilename(mimeType) {
  const mime=String(mimeType || '').toLowerCase();
  if(mime.includes('mp4')) return 'dictation.m4a';
  if(mime.includes('ogg')) return 'dictation.ogg';
  if(mime.includes('wav')) return 'dictation.wav';
  return 'dictation.webm';
}
async function dictate() {
  if(state.recorder?.state==='recording') {state.recorder.stop();return;}
  let stream;
  try {
    $('voice-status').textContent='Requesting microphone permission…';
    stream=await navigator.mediaDevices.getUserMedia({audio:true});
    const chunks=[];
    const preferred=preferredAudioMime();
    const recorder=preferred ? new MediaRecorder(stream,{mimeType:preferred}) : new MediaRecorder(stream);
    state.recorder=recorder;
    recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
    recorder.onerror=event=>{report(new Error(event.error?.message || 'Microphone recording failed.'));};
    recorder.onstop=async()=>{
      clearTimeout(state.recordingTimeout);
      stream.getTracks().forEach(track=>track.stop());
      state.recorder=null;state.busy=true;state.started=Date.now();controls();
      $('voice-status').textContent='Transcribing your recording…';
      phase('Transcribing your voice');
      try {
        const mimeType=String(recorder.mimeType || preferred || 'audio/webm').split(';',1)[0];
        const blob=new Blob(chunks,{type:mimeType});
        if(!blob.size) throw new Error('No audio was captured. Please try again.');
        if(blob.size>10*1024*1024) throw new Error('Recording is too large. Please record a shorter message.');
        const form=new FormData();
        form.append('file',blob,audioFilename(mimeType));
        const result=await (await request(`${endpoint('transcribe')}?user_id=${encodeURIComponent(state.session.user_id)}`,{method:'POST',body:form})).json();
        $('prompt').value=[$('prompt').value,result.transcript].filter(Boolean).join(' ').slice(0,4000);
        $('voice-status').textContent='Transcript ready — review or edit it, then press Send.';
        updateCapabilities('voice_transcription',{status:'ready'});
      } catch(error) {
        $('voice-status').textContent='Voice transcription did not complete.';
        report(error);
      } finally {state.busy=false;controls();tick();$('prompt').focus();}
    };
    recorder.start(250);
    $('voice-status').textContent='Recording… press Stop recording when finished.';
    controls();
    state.recordingTimeout=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},60000);
  } catch(error) {
    stream?.getTracks().forEach(track=>track.stop());
    state.recorder=null;controls();
    $('voice-status').textContent=error?.name==='NotAllowedError' ? 'Microphone permission was not granted.' : 'Could not start microphone recording.';
    report(error);
  }
}
$('composer').onsubmit=submit;$('stop').onclick=()=>state.controller?.abort();$('retry').onclick=connect;
$('attach').onclick=()=>$('files').click();$('photo').onclick=()=>$('camera').click();
for(const id of ['files','camera']) $(id).onchange=event=>{addFiles(event.target.files);event.target.value='';};
$('dictate').onclick=()=>void dictate();
$('prompt').onkeydown=event=>{if(event.key==='Enter' && !event.shiftKey && !event.isComposing){event.preventDefault();$('composer').requestSubmit();}};
window.addEventListener('pagehide',()=>{state.controller?.abort();state.workspaceViewer?.();for(const cleanup of state.inlineViewers) cleanup();state.inlineViewers.clear();state.inputUrls.forEach(URL.revokeObjectURL);state.recorder?.stream?.getTracks().forEach(t=>t.stop());});
// The landing page (/) hands over a conversation starter in the URL fragment.
// Prefill it for review only; the person still chooses when to press Send.
function applyStarterFromFragment() {
  const starter=starterFromHash(location.hash);
  if(!starter) return;
  setPrompt(starter);
  history.replaceState(null,'',location.pathname+location.search);
}
applyStarterFromFragment();
void connect();
