// 成效看板：按当前审查记录估算人工投入，并做界面细节增强。只读取已有数据，不调用模型。
(() => {
    const ASSUME_KEY = 'scheme-impact-assumptions-v3';
    // 人工基准：一份评审前深基坑方案（约 11.5 万字）由一人完整审查约需 3 个工作日。
    const DEFAULTS = { baseHours: 24, baseWan: 11.5, spot: 1.5, A: 2, B: 2, C: 2, D: 2, pend: 2 };
    const LABELS = {
        baseHours: ['人工审查基准工时', '小时', '基准方案由一人完整审查所需工时，评审前深基坑方案约 3 个工作日'],
        baseWan: ['基准方案篇幅', '万字', '基准工时对应的方案字数，本次方案按字数比例折算'],
        spot: ['抽查原文用时', '小时', '基准篇幅下人工抽查原文、查参数的用时，按篇幅折算'],
        A: ['复核一条 A 类意见', '分钟', '对照原文判断后点选复核状态'],
        B: ['复核一条 B 类意见', '分钟', '对照原文判断后点选复核状态'],
        C: ['复核一条 C 类意见', '分钟', '对照原文判断后点选复核状态'],
        D: ['复核一条 D 类意见', '分钟', '对照原文判断后点选复核状态'],
        pend: ['待核意见额外核对', '分钟', 'AI 标为待核的意见，另需补查原文或规范'],
    };
    const PCOLOR = { A: '#D2452F', B: '#E09A0E', C: '#2F6FD6', D: '#7C8BA1' };
    const PNAME = { A: '优先处理', B: '尽快修改', C: '常规完善', D: '文字修正' };
    const CATS = ['内容缺项', '技术性错误', '前后矛盾', '与本项目条件不符', '错别字与表述问题'];
    const DONE = ['确认修改', '已修改'];

    function assumptions() {
        try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(ASSUME_KEY) || '{}') }; }
        catch { return { ...DEFAULTS }; }
    }
    function saveAssumptions(a) { try { localStorage.setItem(ASSUME_KEY, JSON.stringify(a)); } catch {} }

    const num = (v, d = 1) => Number.isFinite(v) ? (Math.round(v * 10 ** d) / 10 ** d).toLocaleString('zh-CN') : '—';

    // 统计口径：正文初审批次的原文字数（续审重复的批次按起始段号去重）。
    function measure(j) {
        const seen = new Set(); let chars = 0;
        for (const r of j.requests || []) {
            if (r.phase !== '正文初审' || !Number.isFinite(r.textChars)) continue;
            const key = r.paragraphStart + '-' + r.paragraphEnd;
            if (seen.has(key)) continue;
            seen.add(key); chars += r.textChars;
        }
        const estimated = !chars;
        if (estimated) chars = (j.document?.count || 0) * 40;
        const requests = j.requests || [];
        let tokens = 0, metered = 0, failed = 0, retries = 0;
        for (const r of requests) {
            if (r.status === 'failed') failed++;
            retries += r.retries?.length || 0;
            const usage = r.usage || {};
            const reported = usage.total_tokens ?? (usage.prompt_tokens + usage.completion_tokens);
            if (Number.isFinite(reported)) {
                tokens += reported;
                metered++;
            }
        }
        let duration = '未记录';
        if (Number.isFinite(j.activeReviewSeconds) && j.activeReviewSeconds >= 0) {
            const seconds = Math.round(j.activeReviewSeconds);
            duration = `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
            if (j.reviewTimingPartial) duration += '（仅续审）';
        }
        return {chars, estimated, tokens, metered, calls: requests.length, failed, retries, duration};
    }

    function estimate(j) {
        const a = assumptions(), m = measure(j), issues = j.issues, n = issues.length;
        const ratio = m.chars / Math.max(a.baseWan * 10000, 1);
        const manual = a.baseHours * ratio;
        const spotHours = a.spot * ratio;
        const counts = {}; let reviewMin = 0;
        for (const p of ['A', 'B', 'C', 'D']) { counts[p] = issues.filter(x => (x.priority || 'C') === p).length; reviewMin += counts[p] * a[p]; }
        const pending = issues.filter(x => x.aiReview === '待核').length;
        const reviewHours = reviewMin / 60, pendHours = pending * a.pend / 60;
        const assisted = spotHours + reviewHours + pendHours;
        const saved = Math.max(manual - assisted, 0);
        return { a, m, n, ratio, manual, spotHours, counts, pending, reviewHours, pendHours, assisted, saved, pct: manual ? saved / manual : 0 };
    }

    // ---------- 导航与页面 ----------
    desktopIcons.impact = '<path d="M3 17h14M5 17V9m4 8V5m4 12v-6m4 6V7"/><path d="M3 4h4M3 4l1.5-1.5M3 4l1.5 1.5"/>';
    desktopTitles.impact = ['成效看板', '本次审查的问题构成、复核进度和人工投入估算。'];
    const navButton = document.createElement('button');
    navButton.dataset.tab = 'impact';
    navButton.innerHTML = `<span>${desktopIcon('impact')}</span>成效看板`;
    document.querySelector('nav.nav [data-tab="review"]').after(navButton);
    navButton.onclick = () => tab('impact');

    const page = document.createElement('section');
    page.className = 'tab';
    page.id = 'tab-impact';
    $('#tab-review').after(page);

    const banner = document.createElement('button');
    banner.type = 'button';
    banner.id = 'impactBanner';
    banner.hidden = true;
    banner.onclick = () => tab('impact');
    $('#tab-review .result-title').after(banner);

    function donut(issues) {
        const total = issues.length || 1, r = 52, c = 2 * Math.PI * r;
        let offset = 0;
        const arcs = ['A', 'B', 'C', 'D'].map(p => {
            const k = issues.filter(x => x.priority === p).length;
            const len = c * k / total;
            const arc = k ? `<circle r="${r}" cx="70" cy="70" fill="none" stroke="${PCOLOR[p]}" stroke-width="18" stroke-dasharray="${len} ${c - len}" stroke-dashoffset="${-offset}"><title>${p} ${PNAME[p]}：${k} 条</title></circle>` : '';
            offset += len;
            return arc;
        }).join('');
        return `<svg viewBox="0 0 140 140" class="im-donut" role="img" aria-label="优先级构成"><g transform="rotate(-90 70 70)">${arcs || `<circle r="${r}" cx="70" cy="70" fill="none" stroke="var(--line)" stroke-width="18"/>`}</g><text x="70" y="68" class="im-donut-num">${issues.length}</text><text x="70" y="90" class="im-donut-label">条问题</text></svg>`;
    }

    function render() {
        if (!job) {
            page.innerHTML = `<div class="im-empty panel"><h2>还没有可展示的审查结果</h2><p>在「AI诊断」中导入方案并完成一次审查，或打开一份已保存的审查记录，这里会自动生成成效看板。</p><button class="primary" type="button" id="imGoReview">去 AI 诊断</button></div>`;
            $('#imGoReview').onclick = () => tab('review');
            return;
        }
        const e = estimate(job), m = e.m, issues = job.issues;
        const newIssues = job.bianshenSummary ? issues.filter(i => i.bianshenPending?.coverage !== 'full') : issues;
        function issueShare(predicate) {
            const count = issues.filter(predicate).length;
            return `${count} 条（${num(100 * count / issues.length, 1)}%）`;
        }
        const statuses = issues.map(x => reviews[x.id]?.status || '待复核');
        const done = statuses.filter(s => DONE.includes(s)).length;
        const rejected = statuses.filter(s => s === '不采纳').length;
        const back = statuses.filter(s => s === '退回补查').length;
        const pending = issues.length - done - rejected - back;
        const handled = issues.length - pending;
        const date = (job.finishedAt || job.createdAt || '').slice(0, 10) || '—';
        const maxCat = Math.max(1, ...CATS.map(c => newIssues.filter(x => x.category === c).length));
        const manualW = 100, assistedW = e.manual ? Math.max(4, 100 * e.assisted / e.manual) : 0;

        page.innerHTML = `
        <div class="im-titleblock" role="group" aria-label="审查记录信息">
            <div class="im-tb-name"><small>方案名称</small><strong>${esc(job.document.name)}</strong></div>
            <div><small>方案类别</small><b>${esc(job.schemeType || '通用')}</b></div>
            <div><small>审查篇幅</small><b>${num(m.chars / 10000, 1)} 万字${m.estimated ? '（估）' : ''}</b></div>
            <div><small>审查日期</small><b>${esc(date)}</b></div>
            <div><small>状态</small><b>${esc(job.stage || '')}</b></div>
        </div>

        <section class="im-hero panel">
            <div class="im-hero-head">
                <div>
                    <h2>本次审查预计节省人工 <span class="im-big">${num(e.saved, 1)}</span> 小时</h2>
                    <p>纯人工约 ${num(e.manual / 8, 1)} 个工作日，AI 辅助约 ${num(e.assisted / 8, 1)} 个工作日，人工投入减少 ${num(e.pct * 100, 0)}%。按下方估算参数计算，可随时调整。</p>
                </div>
            </div>
            <div class="im-dims">
                <div class="im-dim">
                    <div class="im-dim-label"><b>纯人工审查</b><span>${num(e.manual, 1)} 小时</span></div>
                    <div class="im-dim-line manual" style="--w:${manualW}%"><i></i></div>
                    <small>基准 ${num(e.a.baseHours, 1)} 小时 / ${num(e.a.baseWan, 1)} 万字，本次 ${num(m.chars / 10000, 1)} 万字，按篇幅折算</small>
                </div>
                <div class="im-dim">
                    <div class="im-dim-label"><b>AI 初审 + 人工复核</b><span>${num(e.assisted, 1)} 小时</span></div>
                    <div class="im-dim-line assisted" style="--w:${assistedW}%"><span class="im-saved"></span><i></i><em style="--s:${assistedW}%">节省 ${num(e.saved, 1)} 小时</em></div>
                    <small>抽查原文 ${num(e.spotHours, 1)} 小时 + 分级复核 ${e.n} 条意见 ${num(e.reviewHours, 1)} 小时（A ${e.counts.A} · B ${e.counts.B} · C ${e.counts.C} · D ${e.counts.D}）${e.pending ? ` + 待核 ${e.pending} 条补查 ${num(e.pendHours, 1)} 小时` : ''}</small>
                </div>
            </div>
        </section>

        <div class="im-grid">
            <section class="panel im-card">
                <h3>${job.bianshenSummary ? '新增问题构成' : '问题构成'}</h3>
                ${job.bianshenSummary ? '<p>编制阶段已登记待补 '+job.bianshenSummary.registered+' 项，本次仍未闭合。</p>' : ''}
                <div class="im-split">
                    ${donut(newIssues)}
                    <ul class="im-legend">${['A', 'B', 'C', 'D'].map(p => `<li><i style="background:${PCOLOR[p]}"></i>${p} ${PNAME[p]}<b>${newIssues.filter(x => x.priority === p).length}</b></li>`).join('')}</ul>
                </div>
                <div class="im-bars">${CATS.map(c => {
                    const k = newIssues.filter(x => x.category === c).length;
                    return `<div class="im-bar"><span>${c}</span><div><i style="width:${100 * k / maxCat}%"></i></div><b>${k}</b></div>`;
                }).join('')}</div>
            </section>

            <section class="panel im-card">
                <h3>人工复核进度</h3>
                <div class="im-progress-num"><span class="im-big">${handled}</span> / ${issues.length} 条已处理</div>
                <div class="im-stack" role="img" aria-label="复核状态分布">
                    <i style="flex:${done};background:#2E8B57" title="确认修改 ${done}"></i>
                    <i style="flex:${back};background:#E09A0E" title="退回补查 ${back}"></i>
                    <i style="flex:${rejected};background:#7C8BA1" title="不采纳 ${rejected}"></i>
                    <i style="flex:${pending};background:var(--im-track)" title="待复核 ${pending}"></i>
                </div>
                <ul class="im-legend im-legend-row">
                    <li><i style="background:#2E8B57"></i>需修改<b>${statuses.filter(s => s === "确认修改").length}</b></li>
                    <li><i style="background:var(--bp-green)"></i>已修改<b>${statuses.filter(s => s === "已修改").length}</b></li>
                    <li><i style="background:#E09A0E"></i>退回补查<b>${back}</b></li>
                    <li><i style="background:#7C8BA1"></i>不采纳<b>${rejected}</b></li>
                    <li><i style="background:var(--im-track)"></i>人工尚未处理<b>${pending}</b></li>
                </ul>
                <p class="im-note">${handled && issues.length ? `已处理意见中采纳 ${num(100 * done / Math.max(handled, 1), 0)}%。` : '在「AI诊断」中逐条复核后，这里会实时更新。'}</p>
            </section>

            <section class="panel im-card">
                <h3>AI 运行情况</h3>
                <dl class="im-facts">
                    <div><dt>审查原文</dt><dd>${m.chars ? num(m.chars, 0) + ' 字' : '—'}</dd></div>
                    <div><dt>已完成批次</dt><dd>${num(job.completed, 0)} / ${num(job.total, 0)}</dd></div>
                    <div><dt>审查运行用时</dt><dd>${m.duration}</dd></div>
                    <div><dt>审查请求（含失败）</dt><dd>${m.calls} 次</dd></div>
                    <div><dt>已返回用量（tokens）</dt><dd>${m.metered ? num(m.tokens, 0) : '未记录'}</dd></div>
                    <div><dt>AI 标记待核</dt><dd>${issues.some(i => i.aiReview) ? issueShare(i => i.aiReview === '待核') : '—'}</dd></div>
                </dl>
                <p class="im-note">${m.failed} 次请求失败，${m.calls - m.metered} 次未返回用量。${m.retries ? `另有 ${m.retries} 条接口自动重试记录。` : ''}</p>
                ${issues.length && job.citationStats ? `<p class="im-note">部分引文移除 ${issueShare(i => i.partialCitations)}，占比按当前问题清单计算。</p>` : ''}
            </section>
        </div>

        <details class="panel im-assume">
            <summary>估算参数 <small>按本单位实际情况调整，调整后立即重算</small></summary>
            <div class="im-assume-grid">${Object.entries(LABELS).map(([k, [name, unit, hint]]) => `
                <label><span>${name}</span><span class="im-input"><input type="number" min="0" step="${k === 'baseWan' || k === 'spot' ? '0.1' : '1'}" data-assume="${k}" value="${e.a[k]}"><em>${unit}</em></span><small>${hint}</small></label>`).join('')}
            </div>
            <p class="im-formula">纯人工 = 基准工时 × 本次字数 ÷ 基准篇幅；AI 辅助 = 抽查用时 × 本次字数 ÷ 基准篇幅 + Σ 各级意见数 × 对应复核时间 + 待核数 × 额外核对时间。<button type="button" class="link" id="imReset">恢复默认</button></p>
        </details>`;

        page.querySelectorAll('[data-assume]').forEach(input => input.onchange = () => {
            const a = assumptions(), v = Number(input.value);
            if (!Number.isFinite(v) || v < 0 || (input.dataset.assume === 'baseWan' && v <= 0)) { input.value = a[input.dataset.assume]; return; }
            a[input.dataset.assume] = v;
            saveAssumptions(a); render(); updateBanner(); page.querySelector('.im-assume').open = true;
        });
        $('#imReset').onclick = () => { saveAssumptions(DEFAULTS); render(); updateBanner(); page.querySelector('.im-assume').open = true; };
    }

    function updateBanner() {
        if (!job || job.status !== 'done' || !job.issues.length) { banner.hidden = true; return; }
        const e = estimate(job);
        banner.hidden = false;
        banner.innerHTML = `<span class="im-banner-mark" aria-hidden="true"></span><span>本次审查预计节省人工 <b>${num(e.saved, 1)} 小时</b>（减少 ${num(e.pct * 100, 0)}%）</span><span class="im-banner-go">查看成效看板</span>`;
    }

    // 问题卡片按优先级着色，指标卡显示占比。
    function decorate() {
        document.querySelectorAll('#issues .check').forEach(card => {
            const p = card.querySelector('.priority')?.classList[1];
            if (p) card.dataset.p = p;
        });
        if (!job) return;
        const n = job.issues.length || 1;
        const shares = [1, job.issues.filter(x => x.priority === 'A').length / n, job.issues.filter(x => x.priority === 'B').length / n,
            job.issues.filter(x => reviews[x.id]?.status && reviews[x.id].status !== '待复核').length / n];
        document.querySelectorAll('.metrics .metric').forEach((el, i) => el.style.setProperty('--share', job.issues.length ? (100 * shares[i]).toFixed(1) + '%' : '0%'));
    }

    const baseDrawJob = drawJob;
    drawJob = function () { baseDrawJob(); updateBanner(); decorate(); if (page.classList.contains('active')) render(); };
    const baseDrawIssues = drawIssues;
    drawIssues = function () { baseDrawIssues(); decorate(); };
    const baseTab = tab;
    tab = function (name) { baseTab(name); if (name === 'impact') render(); };
    document.addEventListener('change', event => {
        if (event.target.closest?.('#detail') && job) setTimeout(() => { decorate(); updateBanner(); }, 0);
    });

    // 指标卡加图标，便于一眼区分。
    const metricIcons = [
        '<path d="M5 4h10v13H5zM8 8h4M8 11h4"/>',
        '<path d="M10 3 2 17h16zM10 8v4m0 2.5v.5"/>',
        '<circle cx="10" cy="10" r="7"/><path d="M10 6v4l3 2"/>',
        '<circle cx="10" cy="10" r="7"/><path d="m7 10 2 2 4-4"/>',
    ];
    document.querySelectorAll('.metrics .metric').forEach((el, i) => el.insertAdjacentHTML('afterbegin', `<svg class="metric-icon" viewBox="0 0 20 20" aria-hidden="true">${metricIcons[i] || ''}</svg>`));
    document.body.classList.add('visual-v1');
})();
