// 飞书主题工作区：沿用已有事件和接口，仅调整布局与窗口生命周期。
const desktopTitles={review:['方案审查工作台','导入方案，按需选择图片，让 AI 初审，再逐条复核。'],focus:['重点关注','按方案类别管理关注项，审查时逐项核对。'],params:['项目参数','查看提取的参数、适用工况与原文来源。'],model:['模型设置','配置文字与视觉模型，保存后下次启动继续使用。'],basis:['使用说明','了解资料导入、方案审查和批量整改的操作方法。'],amend:['整改文本','勾选问题生成建议，人工编辑后批量替换原文。'],debug:['批量调试','本地预览切分，或按文件依次运行诊断。']};
const desktopIcons={review:'<rect x="4" y="3" width="12" height="16" rx="2"/><path d="M7 7h6M7 10h6m-6 3h3m3 3 2 2 4-5"/>',focus:'<path d="m10 3 2 5 5 .5-4 3.5 1 5-4-2.5L6 17l1-5-4-3.5L8 8z"/>',params:'<path d="M4 17V9m6 8V3m6 14v-6M2 18h17"/>',model:'<path d="M4 6h12M4 14h12"/><circle cx="8" cy="6" r="2"/><circle cx="12" cy="14" r="2"/>',basis:'<path d="M4 3h10a2 2 0 0 1 2 2v13H6a2 2 0 0 1-2-2zm0 12h12M7 7h6M7 10h4"/>',amend:'<path d="M12 4H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7M10 14l-4 1 1-4 8-8 3 3z"/>',debug:'<path d="m7 6-4 4 4 4m6-8 4 4-4 4M11 3 9 17"/>'};
function desktopIcon(name){return `<svg viewBox="0 0 20 20" aria-hidden="true">${desktopIcons[name]||desktopIcons.review}</svg>`}
$('.logo').innerHTML=desktopIcon('review');
$('.brandnote').textContent='方案审查 · 本地工作台';
const desktopNav=$('nav.nav');
for(const name of ['review','amend','params','focus','model','basis','debug']){const b=desktopNav.querySelector(`[data-tab="${name}"]`);b.querySelector('span').innerHTML=desktopIcon(name);desktopNav.append(b)}
desktopNav.querySelector('[data-tab="model"]').insertAdjacentHTML('beforebegin','<div class="nav-divider">配置与工具</div>');
$('.sidebottom').childNodes[0].textContent='AI 初审 · 人工确认';
$('.top .eyebrow').id='desktopBreadcrumb';
const connection=$('.top .pill');
$('.top').insertAdjacentHTML('beforeend','<div class="top-actions"><div class="theme-switch" role="group" aria-label="界面主题"><button data-theme="light" title="浅色模式">浅色</button><button data-theme="dark" title="深色模式">深色</button><button data-theme="system" title="跟随系统">跟随系统</button></div></div>');
$('.top-actions').prepend(connection);
$('.hero .index').remove();$('.hero').insertAdjacentHTML('beforeend','<span class="hero-status">图文审查 / 人工整改</span>');
const toolbar=$('.toolbar'),recordLine=document.createElement('div'),actionLine=document.createElement('div');
recordLine.className='record-line';actionLine.className='toolbar-actions';
recordLine.append(toolbar.querySelector('label'),$('#sample'));
for(const id of ['importPlan','start','resume','generateAmend','viewImages'])actionLine.append($('#'+id));
actionLine.insertAdjacentHTML('beforeend','<details class="more-actions"><summary>更多操作 ▾</summary><div class="more-menu"></div></details>');
for(const id of ['importResult','linkSources','export','stopTop'])actionLine.querySelector('.more-menu').append($('#'+id));
actionLine.append($('#visionStatus'));toolbar.append(recordLine,actionLine);
const workspaceTools=document.createElement('div');workspaceTools.id='documentWorkspace';toolbar.before(workspaceTools);
for(const item of [toolbar,$('#imageReviewPanel'),$('#pageConversionProgress'),$('#importWarnings'),$('.audit-options'),$('#progress')])if(item)workspaceTools.append(item);
$('#tab-review').prepend($('.metrics'));
const reviewSettings=document.createElement('details');reviewSettings.className='review-settings panel';
reviewSettings.innerHTML='<summary>设计依据与重点关注 <small>展开查看或调整</small></summary>';
const existingInput=$('#tab-review .input-panel');existingInput.before(reviewSettings);reviewSettings.append(existingInput);
const beforeDesktopDrawJob=drawJob;
drawJob=function(){beforeDesktopDrawJob();document.body.classList.toggle('review-completed',job?.status==='done')};
$('.workspace').insertAdjacentHTML('beforeend','<aside class="panel source-panel"><div class="panelhead"><h3>原文对照</h3><small>引用上下文</small></div><div id="desktopSource" class="source-content"><div class="empty">选择问题后，在这里对照原文和图片。</div></div></aside>');
const beforeDesktopTab=tab;
tab=function(name){beforeDesktopTab(name);const t=desktopTitles[name]||desktopTitles.review;$('.hero h1').textContent=t[0];$('.hero p').textContent=t[1];$('#desktopBreadcrumb').textContent='施工方案 AI 审查 / '+t[0];workspaceTools.hidden=!['review','amend','debug'].includes(name);$('.audit-options').hidden=name!=='review';document.querySelector('.more-actions').open=false};
const desktopMedia=matchMedia('(prefers-color-scheme: dark)');let desktopTheme='system';
try{desktopTheme=localStorage.getItem('scheme-desktop-theme')||'system'}catch{}
function applyDesktopTheme(mode){
 desktopTheme=['light','dark','system'].includes(mode)?mode:'system';const dark=desktopTheme==='dark'||desktopTheme==='system'&&desktopMedia.matches;
 document.body.setAttribute('theme-mode',dark?'dark':'light');document.documentElement.style.colorScheme=dark?'dark':'light';
 document.querySelectorAll('[data-theme]').forEach(b=>{b.classList.toggle('active',b.dataset.theme===desktopTheme);b.setAttribute('aria-pressed',String(b.dataset.theme===desktopTheme))});
 try{localStorage.setItem('scheme-desktop-theme',desktopTheme)}catch{}
 if(window.pywebview?.api)window.pywebview.api.set_theme(dark?'dark':'light');
}
document.querySelectorAll('[data-theme]').forEach(b=>b.onclick=()=>applyDesktopTheme(b.dataset.theme));
desktopMedia.addEventListener('change',()=>{if(desktopTheme==='system')applyDesktopTheme('system')});
window.addEventListener('pywebviewready',()=>applyDesktopTheme(desktopTheme));applyDesktopTheme(desktopTheme);
let sourceSequence=0;
const beforeDesktopDetail=drawDetail;
drawDetail=function(){beforeDesktopDetail();loadDesktopSource()};
async function loadDesktopSource(){
 const seq=++sourceSequence,item=job?.issues.find(i=>i.id===selected),pane=$('#desktopSource');
 if(!item?.citations?.length){pane.innerHTML='<div class="empty">选择问题后，在这里对照原文和图片。</div>';return}
 const cite=item.citations[0],jid=job.id;pane.innerHTML='<p class="fieldnote">正在读取原文…</p>';
 try{const r=await api('/api/context',{jobId:jid,source:cite.source,paragraph:cite.paragraph});if(seq!==sourceSequence)return;
 pane.innerHTML=`<div class="source-title">${esc(citationLocation(cite))}</div>${r.rows.map(row=>`<div class="contextrow ${row.id===cite.paragraph?'target':''}"><small>${esc(row.id===cite.paragraph?'引用原文':row.location||row.section||'相邻段落')}</small><br>${esc(row.text)}</div>`).join('')}`;
 const pics=await extended('issue-images',{id:jid,issueId:item.id});if(seq!==sourceSequence)return;
 if(pics.images.length){pane.insertAdjacentHTML('beforeend','<div class="divider"></div><p class="source-title">引用位置附近图片</p>');for(const v of pics.images){const p=await extended('image',{imageId:v.id});if(seq!==sourceSequence)return;pane.insertAdjacentHTML('beforeend',`<p class="fieldnote">${esc(v.label)}</p><img alt="${esc(v.label)}" src="${p.dataUrl}">`)}}
 }catch(e){if(seq===sourceSequence)pane.innerHTML=`<div class="empty">${esc(e.message)}</div>`}
}
let desktopClosing=false,desktopAllowUnload=false,desktopAmendDirty=false,desktopConfigDirty=false;
document.addEventListener('input',e=>{if(e.target.closest('#tab-model'))desktopConfigDirty=true;if(e.target.closest('#amendRows'))desktopAmendDirty=true});
document.addEventListener('change',e=>{if(e.target.closest('#amendRows'))desktopAmendDirty=true});
document.addEventListener('click',e=>{if(e.target.closest('#amendAll,#amendNone'))desktopAmendDirty=true});
const beforeDesktopApplyConfig=applyConfig;applyConfig=function(c){beforeDesktopApplyConfig(c);desktopConfigDirty=false};
async function saveDesktopWork(){
 if(desktopConfigDirty){const r=await api('/api/config',{config:cfg()});applyConfig(r.config)}
 if(libraryDirty){focusRead();const r=await api('/api/scheme-library',{library});library=r.schemeLibrary;libraryDirty=false;$('#libraryState').textContent='已保存'}
 if(job)reviewCache[job.id]=structuredClone(reviews);
 for(const id of Object.keys(dirtyReviews).filter(id=>dirtyReviews[id])){await api('/api/export',{id,reviews:reviewCache[id]||{}});dirtyReviews[id]=false}
 if(desktopAmendDirty&&job?.id===amendJobId&&document.querySelector('[data-edit]')){await extended('save-draft',{id:job.id,edits:readEdits()});desktopAmendDirty=false}
}
async function finishDesktopClose(){
 desktopAllowUnload=true;
 if(window.pywebview?.api){const r=await window.pywebview.api.finish_close();if(!r.ok){desktopAllowUnload=false;throw Error(r.error)}}
 else{await api('/api/stop',{});$('#dialog').close();$('#connection').textContent='服务已关闭';toast('服务已关闭，可以关闭此页面。')}
}
window.requestDesktopClose=async function(){
 if(desktopClosing)return;desktopClosing=true;
 try{
  const state=await api('/api/desktop/state',{}),dirty=Object.values(dirtyReviews).some(Boolean)||libraryDirty||desktopAmendDirty||desktopConfigDirty;
  if(!state.busy&&!dirty){await finishDesktopClose();return}
  if($('#dialog').open)$('#dialog').close();
  modal(state.busy?'任务仍在运行':'保存后退出',`${state.busy?`<p>当前任务：${state.running.map(esc).join('、')}。</p><p class="fieldnote">停止后不再启动新批次，等待当前请求或转换结束，再保存并退出。</p>`:'<p>有未保存的复核意见、整改文本或设置。</p>'}<p id="desktopCloseStatus" class="fieldnote" style="margin:12px 0">${state.busy?'':'保存后可通过审查记录恢复。'}</p><div class="actions"><button id="desktopKeepOpen">返回工作台</button>${state.busy?'':'<button id="desktopDiscardClose">不保存退出</button>'}<button class="primary" id="desktopSaveClose">${state.busy?'停止任务并保存退出':'保存并退出'}</button></div>`);
  $('#desktopKeepOpen').onclick=()=>{desktopClosing=false;$('#dialog').close()};
  if($('#desktopDiscardClose'))$('#desktopDiscardClose').onclick=async()=>{try{await finishDesktopClose()}catch(e){toast(e.message);desktopClosing=false}};
  $('#desktopSaveClose').onclick=async()=>{
   $('#desktopSaveClose').disabled=true;
   try{
    if(state.busy){await api('/api/desktop/cancel',{});for(;;){if(!desktopClosing)return;const now=await api('/api/desktop/state',{});if(!now.busy)break;$('#desktopCloseStatus').textContent='已申请停止，等待当前任务结束…';await new Promise(ok=>setTimeout(ok,500))}}
    $('#desktopCloseStatus').textContent='正在保存…';await saveDesktopWork();await finishDesktopClose();
   }catch(e){$('#desktopCloseStatus').textContent='尚未退出：'+e.message;$('#desktopSaveClose').disabled=false}
  };
 }catch(e){toast(e.message);desktopClosing=false}
};
$('#dialog').addEventListener('close',()=>{if(!desktopAllowUnload)desktopClosing=false});
window.addEventListener('beforeunload',e=>{if(!desktopAllowUnload&&(Object.values(dirtyReviews).some(Boolean)||desktopAmendDirty||desktopConfigDirty||libraryDirty)){e.preventDefault();e.returnValue=''}});
stopDialog=()=>window.requestDesktopClose();$('#stopSide').textContent='退出客户端';$('#stopTop').textContent='退出客户端';$('#stopSide').onclick=stopDialog;$('#stopTop').onclick=stopDialog;
tab(document.querySelector('.tab.active')?.id.replace('tab-','')||'review');
document.body.classList.toggle('review-completed',job?.status==='done');

window.addEventListener('pywebviewready',()=>{
    const footer=document.querySelector('.sidebottom');
    if(!footer||!window.pywebview?.api?.open_data_folder)return;
    const button=document.createElement('button');
    button.textContent='打开资料目录';button.type='button';
    button.onclick=()=>window.pywebview.api.open_data_folder();
    footer.appendChild(button);
});
