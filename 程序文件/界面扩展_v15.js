// 沿用原界面，新增独立整改工作区和批量调试入口。
const mainV12=document.querySelector('main');
document.querySelector('nav.nav').insertAdjacentHTML('beforeend','<button data-tab="amend"><span>06</span>整改文本</button><button data-tab="debug"><span>07</span>批量调试 debug</button>');
document.querySelectorAll('[data-tab="amend"],[data-tab="debug"]').forEach(b=>b.onclick=()=>{tab(b.dataset.tab);if(b.dataset.tab==='amend')loadAmendments()});
document.querySelector('.toolbar').insertAdjacentHTML('beforeend','<button class="primary" id="generateAmend">生成整改文本</button><button id="viewImages">查看图片与章节</button><small id="visionStatus"></small>');
document.querySelector('.toolbar').insertAdjacentHTML('afterend','<div id="pageConversionProgress" class="progressbox" hidden><div class="actions"><b id="pageConversionPhase"></b><button id="stopPages" style="margin-left:auto">停止导入</button></div><small id="pageConversionFile"></small><div class="progressbar"><i id="pageConversionBar" style="width:0"></i></div></div><div id="importWarnings"></div>');
let pageOperationId='',pageConversionBusy=false;
document.querySelector('#saveConfig').closest('.buttons-line').insertAdjacentHTML('beforebegin','<div id="visionConfig"><div class="divider"></div><h3>视觉模型配置</h3><label><input type="checkbox" id="visionEnabled" checked> 启用视觉接口</label><div class="formitem"><label>视觉模型</label><input id="visionModel" list="modelList" placeholder="填写支持图片输入的模型名"></div><p class="fieldnote">导入时自动提取章节和图片。Word保留原始插图；PDF按页码关联图片，扫描页和矢量图表自动处理。是否审查图片及审查哪些图片，在审查入口选择。</p><div class="formitem"><label>视觉生成上限 tokens</label><input id="visionMaxTokens" type="number" min="1024" max="262144" value="65536"><small>按服务商支持范围填写；包含思考和正文输出，不再固定限制为8192。</small></div></div>');
mainV12.insertAdjacentHTML('beforeend',`<section class="tab" id="tab-amend"><div class="panel detail"><div class="panelhead"><h2>整改对照表</h2><button id="pickAmend">勾选问题并生成</button></div><p id="amendStatus" class="fieldnote">先完成审查，再选择需要整改的问题。</p><div class="actions" style="margin:16px 0"><button id="amendAll">全选</button><button id="amendNone">取消全选</button><button id="saveAmend">保存对照表</button><button class="primary" id="applyAmend">批量替换并导出Word</button></div><div class="table-wrap"><table><thead><tr><th>采纳</th><th>问题及位置</th><th>替换前原文</th><th style="min-width:340px">替换后文本 可编辑</th></tr></thead><tbody id="amendRows"></tbody></table></div><div id="amendUnresolved"></div></div></section>
<section class="tab" id="tab-debug"><div class="panel detail"><h2>批量调试 debug</h2><p class="fieldnote">解析预览不调用模型。批量诊断按文件依次执行，保留阶段输入输出、耗时、token和失败位置，不进行benchmark评分。</p><div class="actions" style="margin:16px 0"><input type="file" id="debugFiles" multiple accept=".docx,.pdf,.txt"><button id="debugParse">解析并预览切分</button><button class="primary" id="debugRun">调用模型批量诊断</button><button id="debugStop">停止批量诊断</button></div><div id="debugFileList"></div><p id="debugStatus"></p><pre id="debugOutput" style="white-space:pre-wrap;max-height:650px;overflow:auto;background:#f3f6f3;padding:16px"></pre></div></section>`);
const oldCfgV12=cfg,oldApplyConfigV12=applyConfig,oldUpdateDocV12=updateDoc,oldDrawDetailV12=drawDetail;
$('#visionModel').closest('.formitem').insertAdjacentHTML('afterend','<div class="formgrid"><div class="formitem"><label>独立视觉接口 可选</label><input id="visionBase" placeholder="留空沿用主接口"></div><div class="formitem"><label>独立视觉密钥</label><input type="password" id="visionKey" autocomplete="off" placeholder="独立接口需填写对应密钥"></div></div>');
$('#visionModel').previousElementSibling.textContent='视觉模型';
cfg=function(){return {...oldCfgV12(),visionMaxTokens:Number($('#visionMaxTokens').value),visionEnabled:$('#visionEnabled').checked,visionModel:$('#visionModel').value.trim(),visionBase:$('#visionBase').value.trim(),visionKey:$('#visionKey').value.trim()}};
applyConfig=function(c){oldApplyConfigV12(c);$('#visionMaxTokens').value=c.visionMaxTokens||65536;$('#visionEnabled').checked=c.visionEnabled!==false;$('#visionModel').value=c.visionModel||'';$('#visionBase').value=c.visionBase||'';$('#visionKey').value='';$('#visionKey').placeholder=c.visionHasKey?'已保存，留空沿用':'独立接口需填写对应密钥'};
updateDoc=function(){oldUpdateDocV12();refreshImageReview();$('#visionStatus').textContent=doc?`${doc.visualCount||0}张图片 · ${doc.headingCount||0}个标题${doc.imageMode?' · '+doc.imageMode:''}`:'';$('#importWarnings').innerHTML=(doc?.unreadVisuals||[]).map(v=>`<p class="job-note">未提取图形：${esc(v.location||'原文位置待核')} · ${esc(v.reason)}</p>`).join('')};
drawDetail=function(){oldDrawDetailV12();if(job&&selected)$('#detail').insertAdjacentHTML('beforeend','<div class="actions" style="margin-top:15px"><button id="issueImage">查看该问题引用的图片</button></div>');if($('#issueImage'))$('#issueImage').onclick=issueImages};
async function extended(action,data={}){return api('/api/extended/'+action,data)}
function showPageProgress(r){$('#pageConversionProgress').hidden=false;$('#pageConversionPhase').textContent=`${r.phase||'准备文件'}${r.total?' · '+r.completed+'/'+r.total+(r.unit||'项'):''}${r.images!==undefined?' · 已提取'+r.images+'张图片':''}`;$('#pageConversionBar').style.width=(r.status==='done'?100:r.total?Math.min(100,100*r.completed/r.total):0)+'%';$('#stopPages').hidden=r.status!=='running';$('#stopPages').disabled=!!r.cancel}
async function waitOperation(id,message){for(;;){const r=await extended('operation',{operationId:id});if(r.kind==='import')showPageProgress(r);if(r.status==='done')return r;if(r.status==='failed'||r.status==='cancelled')throw Error(r.error);if(r.kind!=='import')$('#amendStatus').textContent=message;await new Promise(ok=>setTimeout(ok,400))}}
const beforeAutoImportApi=api;
api=async function(path,data){
 if(['/api/estimate','/api/start'].includes(path))data={...data,imageReview:currentImageReview()};
 if(path!=='/api/import')return beforeAutoImportApi(path,data);
 if(pageConversionBusy)throw Error('文件正在导入，请等完成后再选择其他文件。');
 pageConversionBusy=true;$('#pageConversionFile').textContent=data.name;
 const buttons=['#importPlan','#importDesign','#start'].map(s=>$(s));const disabled=buttons.map(b=>b.disabled);buttons.forEach(b=>b.disabled=true);
 try{const r=await beforeAutoImportApi('/api/extended/import-start',data);pageOperationId=r.id;showPageProgress(r);const done=await waitOperation(r.id,'正在导入…');return {doc:done.doc}}
 finally{pageConversionBusy=false;buttons.forEach((b,i)=>b.disabled=disabled[i])}
};
$('#stopPages').onclick=async()=>{try{if(pageOperationId){toast((await extended('stop-import',{operationId:pageOperationId})).message);$('#stopPages').disabled=true}}catch(e){toast(e.message)}};
async function displayImages(items,title){if(!items.length)return toast('对应位置没有可显示图片，未提取图形请查看导入结果。');modal(title,items.map(v=>`<div><p>${esc(v.label)}</p><img data-view-image="${esc(v.id)}" style="max-width:100%;border:1px solid #dce5e0;margin:10px 0"></div>`).join(''));for(const v of items){const r=await extended('image',{imageId:v.id});const im=document.querySelector(`[data-view-image="${v.id}"]`);if(im)im.src=r.dataUrl}}
$('#viewImages').onclick=async()=>{try{if(!doc)return toast('请先导入方案。');await displayImages(doc.visuals||[],'图片与所属章节')}catch(e){toast(e.message)}};
async function issueImages(){try{const r=await extended('issue-images',{id:job.id,issueId:selected});await displayImages(r.images,'引用图像')}catch(e){toast(e.message)}}
let amendJobId='',amendDraft={edits:[],unresolved:[]},debugDocs=[],debugBatch='',debugTimer=null;
function pickAmend(){if(!job||job.status==='running')return toast('请先完成审查或导入结果。');modal('选择需要整改的问题',`<div class="actions"><button id="pickAll">全选</button><button id="pickNone">取消全选</button></div><div style="margin:12px 0">${job.issues.map(i=>`<label style="display:block;padding:8px;border-bottom:1px solid #eee"><input type="checkbox" data-amend-issue="${esc(i.id)}"> ${esc(i.id)} · ${esc(i.title)} <small>${esc(reviews[i.id]?.status||'待复核')}</small></label>`).join('')}</div><p class="fieldnote">点击生成后调用当前模型，只处理勾选问题。已有对照表会在新结果完整生成后更新。</p><button class="primary" id="confirmGenerate">生成选中问题的整改文本</button>`);$('#pickAll').onclick=()=>document.querySelectorAll('[data-amend-issue]').forEach(x=>x.checked=true);$('#pickNone').onclick=()=>document.querySelectorAll('[data-amend-issue]').forEach(x=>x.checked=false);$('#confirmGenerate').onclick=generateAmend}
$('#generateAmend').onclick=pickAmend;$('#pickAmend').onclick=pickAmend;
async function generateAmend(){const ids=[...document.querySelectorAll('[data-amend-issue]:checked')].map(x=>x.dataset.amendIssue);if(!ids.length)return toast('请先勾选问题。');const jid=job.id;$('#confirmGenerate').disabled=true;try{const r=await extended('generate',{id:jid,issueIds:ids,config:cfg(),consent:true});$('#dialog').close();tab('amend');$('#amendStatus').textContent='正在生成整改对照表…';await waitOperation(r.id,'正在生成整改对照表…');if(job?.id===jid)await loadAmendments();else toast('原记录整改文本已生成，切回该记录查看。')}catch(e){toast(e.message);$('#amendStatus').textContent=e.message;if($('#confirmGenerate'))$('#confirmGenerate').disabled=false}}
async function loadAmendments(){if(!job)return;try{amendDraft=await extended('amendments',{id:job.id});amendJobId=job.id;drawAmendments()}catch(e){toast(e.message)}}
function drawAmendments(){$('#amendStatus').textContent=`${job?.document.name||''} · ${amendDraft.edits.length}处可替换内容`;
$('#amendRows').innerHTML=amendDraft.edits.map(x=>`<tr data-edit="${esc(x.editId)}"><td><input type="checkbox" class="acceptEdit" ${x.selected!==false?'checked':''}></td><td>${esc(x.issueIds.join('、'))}<br>${esc(x.location)}<p class="fieldnote">${esc(x.reason)}</p></td><td style="white-space:pre-wrap;min-width:260px">${esc(x.before)}</td><td><textarea class="afterEdit" style="min-height:160px">${esc(x.after)}</textarea></td></tr>`).join('')||'<tr><td colspan="4">尚未生成整改文本。</td></tr>';
$('#amendUnresolved').innerHTML=(amendDraft.unresolved||[]).map(x=>`<p class="job-note">${esc(x.issueId)} · 待补信息：${esc(x.reason)}</p>`).join('')}
function readEdits(){if(!job||job.id!==amendJobId)throw Error('审查记录已切换，请重新打开对应整改表。');return [...document.querySelectorAll('[data-edit]')].map(row=>({editId:row.dataset.edit,after:row.querySelector('.afterEdit').value,selected:row.querySelector('.acceptEdit').checked}))}
$('#amendAll').onclick=()=>document.querySelectorAll('.acceptEdit').forEach(x=>x.checked=true);$('#amendNone').onclick=()=>document.querySelectorAll('.acceptEdit').forEach(x=>x.checked=false);
$('#saveAmend').onclick=async()=>{try{const r=await extended('save-draft',{id:job.id,edits:readEdits()});toast(r.message+' '+r.path)}catch(e){toast(e.message)}};
$('#applyAmend').onclick=async()=>{const b=$('#applyAmend');b.disabled=true;try{const r=await extended('apply',{id:job.id,edits:readEdits()});$('#amendStatus').textContent=`已替换${r.count}处；文件：${r.path}；修改记录：${r.recordPath}`;toast('已导出：'+r.path)}catch(e){toast(e.message)}finally{b.disabled=false}};
function drawDebugFiles(){$('#debugFileList').innerHTML=debugDocs.map(d=>`<div class="source-chip"><span>${esc(d.name)} · ${d.count}段 · ${d.visualCount||0}张图片 · ${d.headingCount||0}个标题${d.unreadVisuals?.length?' · '+d.unreadVisuals.length+'项图形待处理':''}</span></div>`).join('')}
$('#debugParse').onclick=async()=>{const files=[...$('#debugFiles').files];if(!files.length)return toast('请先选择文件。');const b=$('#debugParse');b.disabled=true;debugDocs=[];const output=[];try{for(const file of files){$('#debugStatus').textContent='正在解析：'+file.name;const r=await api('/api/import',await fileData(file));debugDocs.push(r.doc);const preview=await extended('debug-preview',{sha256:r.doc.sha256,imageReview:currentImageReview()});output.push(preview);drawDebugFiles()}$('#debugOutput').textContent=JSON.stringify(output,null,2);$('#debugStatus').textContent=`已解析${debugDocs.length}份；模型调用0次。`}catch(e){toast(e.message);$('#debugStatus').textContent=e.message}finally{b.disabled=false}};
$('#debugRun').onclick=()=>{if(!debugDocs.length)return toast('请先解析文件。');modal('批量诊断',`<p>即将按顺序诊断${debugDocs.length}份文件，调用所配置的模型接口并按用量计费。每次请求及结果保存在本地调试记录中。</p><button class="primary" id="confirmDebugRun">开始批量诊断</button>`);$('#confirmDebugRun').onclick=async()=>{try{const r=await extended('debug-start',{documents:debugDocs.map(d=>d.sha256),config:cfg(),imageReview:currentImageReview(),schemeType:currentType()?.name||'通用',consent:true});debugBatch=r.id;$('#dialog').close();pollDebug()}catch(e){toast(e.message)}}};
async function pollDebug(){try{const r=await extended('debug-status',{batchId:debugBatch});$('#debugStatus').textContent=`${r.status==='running'?'运行中':r.status==='done'?'已完成':r.status==='stopped'?'已停止':'失败'} · ${r.results.length}/${r.total}${r.path?' · '+r.path:''}`;$('#debugOutput').textContent=JSON.stringify(r,null,2);if(r.status==='running')debugTimer=setTimeout(pollDebug,1200);else{const boot=await (await fetch('/api/bootstrap')).json();records=boot.jobs||records;drawRecordSelect()}}catch(e){toast(e.message)}}
$('#debugStop').onclick=async()=>{try{if(debugBatch)toast((await extended('debug-stop',{batchId:debugBatch})).message)}catch(e){toast(e.message)}};
// 保存意见之外，关闭服务前也可保存当前整改草稿。
const oldStopV12=stopDialog;
stopDialog=function(){if(document.querySelectorAll('[data-edit]').length&&job?.id===amendJobId){extended('save-draft',{id:job.id,edits:readEdits()}).then(()=>oldStopV12()).catch(e=>toast(e.message))}else oldStopV12()};
$('#stopSide').onclick=stopDialog;$('#stopTop').onclick=stopDialog;


// 本次审查的图片选择与接口配置分开；新导入文件默认只审文字。
const imageReviewChoices=new Map();
document.querySelector('.toolbar').insertAdjacentHTML('afterend',`<div class="panel" id="imageReviewPanel" style="padding:14px 18px;margin:14px 0"><div class="actions"><label><input type="checkbox" id="reviewImages"> 使用视觉模型审查图片</label><button id="pickReviewImages" hidden>选择待审图片</button><span id="imageReviewSummary" class="fieldnote">关闭：只审查正文和表格文字，图片仍可查看。</span></div><p id="reviewBatchSummary" class="fieldnote"></p></div>`);
function reviewDocuments(){return [doc,...design,...debugDocs].filter(Boolean).filter((d,i,a)=>a.findIndex(x=>x.sha256===d.sha256)===i)}
function policyFor(d){
 if(!imageReviewChoices.has(d.sha256))imageReviewChoices.set(d.sha256,d.imageReview?structuredClone(d.imageReview):{enabled:false,imageIds:[]});
 return imageReviewChoices.get(d.sha256);
}
function currentImageReview(){return Object.fromEntries(reviewDocuments().map(d=>[d.sha256,structuredClone(policyFor(d))]))}
let batchPreviewSeq=0;
async function refreshBatchPreview(){const seq=++batchPreviewSeq;if(!doc)return;try{const r=await extended('review-preview',{sha256:doc.sha256,design:design.map(d=>d.sha256),imageReview:currentImageReview()});if(seq===batchPreviewSeq)$('#reviewBatchSummary').textContent=`预计初审${r.initialCalls}批：文字${r.textCalls}批、图文${r.visualCalls}批；选中${r.selectedImages}张图片。之后按候选问题分组回查并汇总。`}catch(e){if(seq===batchPreviewSeq)$('#reviewBatchSummary').textContent=e.message}}
function refreshImageReview(){
 const docs=reviewDocuments(),enabled=docs.some(d=>policyFor(d).enabled),count=docs.reduce((n,d)=>n+(policyFor(d).enabled?policyFor(d).imageIds.length:0),0);
 $('#reviewImages').checked=enabled;$('#pickReviewImages').hidden=!enabled;
 $('#imageReviewSummary').textContent=enabled?`已选${count}张；只有勾选的图片会发送给视觉模型。`:'关闭：只审查正文和表格文字，图片仍可查看。';refreshBatchPreview();
}
$('#reviewImages').onchange=()=>{const enabled=$('#reviewImages').checked;for(const d of reviewDocuments())policyFor(d).enabled=enabled;refreshImageReview();if(enabled)pickReviewImages()};
$('#pickReviewImages').onclick=pickReviewImages;
async function pickReviewImages(){
 const docs=reviewDocuments();if(!docs.length)return toast('请先导入方案。');
 modal('选择需要视觉审查的图片',`<div class="actions"><button id="selectReviewAll">全选</button><button id="selectReviewNone">取消全选</button><button class="primary" id="saveReviewImages">保存选择</button></div><p class="fieldnote">封面、标志和装饰图可以不选。扫描页中的文字需勾选该页图片才能审查。</p>${docs.map(d=>`<h3>${esc(d.name)}</h3><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px">${(d.visuals||[]).map(v=>`<label style="border:1px solid #dce5e0;border-radius:8px;padding:10px"><span><input type="checkbox" data-review-doc="${esc(d.sha256)}" data-review-image="${esc(v.id)}" ${policyFor(d).imageIds.includes(v.id)?'checked':''}> ${esc(v.label)}</span><img data-review-thumb="${esc(v.id)}" loading="lazy" style="display:block;width:100%;max-height:180px;object-fit:contain;margin-top:8px"></label>`).join('')}</div>`).join('')}`);
 $('#selectReviewAll').onclick=()=>document.querySelectorAll('[data-review-image]').forEach(x=>x.checked=true);
 $('#selectReviewNone').onclick=()=>document.querySelectorAll('[data-review-image]').forEach(x=>x.checked=false);
 $('#saveReviewImages').onclick=()=>{for(const d of docs){const p=policyFor(d);p.enabled=true;p.imageIds=[...document.querySelectorAll('[data-review-image]:checked')].filter(x=>x.dataset.reviewDoc===d.sha256).map(x=>x.dataset.reviewImage)}$('#dialog').close();refreshImageReview()};
 for(const v of docs.flatMap(d=>d.visuals||[])){try{const r=await extended('image',{imageId:v.id});const im=document.querySelector(`[data-review-thumb="${v.id}"]`);if(!im)break;im.src=r.dataUrl}catch(e){toast(e.message);break}}
}
const beforeReviewDrawDesign=drawDesign;
drawDesign=function(){beforeReviewDrawDesign();refreshImageReview()};
refreshImageReview();
const beforeReviewDrawDebugFiles=drawDebugFiles;
drawDebugFiles=function(){beforeReviewDrawDebugFiles();refreshImageReview()};
