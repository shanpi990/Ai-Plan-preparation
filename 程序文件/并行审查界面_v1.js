(() => {
    let lanes=5, saved=5, average=90, preview=null, ready=false, lastRunning='';
    let saving=Promise.resolve();
    const controls=[];
    for (const [target, id] of [['#start','parallelReview'], ['#saveConfig','parallelModel']]) {
        const box=document.createElement('label');
        box.className='parallel-setting';
        box.innerHTML=`<span>并发请求数</span><input id="${id}" type="range" min="1" max="10" step="1" value="5" disabled><output></output><small>数量越大越快；接口繁忙时会自动减速，不影响审查结果。</small>`;
        const anchor=document.querySelector(target);
        if (id==='parallelReview') anchor.after(box); else anchor.parentElement.before(box);
        controls.push(box);
        box.querySelector('input').oninput=event=>{lanes=Number(event.target.value);render()};
        box.querySelector('input').onchange=()=>{
            const value=lanes;
            saving=saving.then(async()=>{
                try { await api('/api/parallel-settings',{lanes:value}); saved=value; }
                catch(e) { if(lanes===value)lanes=saved; render();toast(e.message); }
            });
        };
    }
    function render(){
        const locked=!ready||job?.status==='running';
        for(const box of controls){
            const slider=box.querySelector('input');slider.value=String(lanes);slider.disabled=locked;
            const waves = preview?.sha === doc?.sha256 ? preview?.waves[lanes - 1] : 0;
            box.querySelector('output').textContent = `同时 ${lanes} 路` +
                (waves ? ` · 预计初审约 ${Math.ceil(waves * average / 60)} 分钟` : '');
        }
    }
    const baseConfig=cfg;
    cfg=function(){const config=baseConfig();if(ready)config.parallelism=lanes;return config};
    const previousApi=api;
    let latestPreview = 0;
    api=async function(path,data){
        const isPreview = ['/api/estimate','/api/extended/review-preview'].includes(path);
        const version = isPreview ? ++latestPreview : 0;
        const result=await previousApi(path,data);
        if (isPreview && version === latestPreview && data.sha256 === doc?.sha256 && Array.isArray(result.initialWaves)){
            preview = {sha: data.sha256, waves: result.initialWaves};
            render();
        }
        return result;
    };
    const baseDraw=drawJob;
    drawJob=function(){
        baseDraw();
        if(job?.status==='running')lastRunning=job.id;
        if(job?.status==='done' && job.id===lastRunning){
            const rows=(job.requests||[]).filter(r=>r.phase==='正文初审'&&r.status==='completed'&&Number.isFinite(r.requestSeconds));
            if (job.initialAverageSeconds > 0) average = job.initialAverageSeconds;
            else if(rows.length)average=rows.reduce((n,r)=>n+r.requestSeconds,0)/rows.length;
            lastRunning='';
        }
        render();
    };
    fetch('/api/parallel-settings').then(r=>r.json()).then(v=>{
        saved=lanes=v.lanes;average=v.average;ready=true;render()
    }).catch(()=>toast('读取并发设置失败，请刷新客户端。'));
})();
