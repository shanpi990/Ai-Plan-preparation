(() => {
    const button = document.createElement('button');
    button.type = 'button';
    button.id = 'exportProjectParameters';
    button.className = 'primary';
    button.textContent = '导出给编制助手';
    $('#tab-params .panelhead small').replaceWith(button);
    let busy = false;
    function sync() {
        button.disabled = busy || !job?.parameters?.length;
    }
    const draw = drawParameters;
    drawParameters = function () {
        draw();
        sync();
    };
    sync();

    function notify(result) {
        if (!result) return;
        if (result.error) throw Error(result.error);
        const count = '已导出 ' + result.exported + ' 项，跳过 ' + result.skipped + ' 项。';
        toast(count + (result.path ? '保存位置：' + result.path :
            result.exported ? '' : '当前参数均无可用的方案原文引文。'));
    }

    async function run(action) {
        busy = true;
        sync();
        try {
            notify(await action());
        } catch (err) {
            if (err.name !== 'AbortError') toast(err.message || String(err));
        } finally {
            busy = false;
            sync();
        }
    }

    button.onclick = () => {
        const id = job.id;
        if (window.pywebview?.api?.save_project_parameters) {
            return run(() => window.pywebview.api.save_project_parameters(id));
        }
        const filename = job.document.name.replace(/\.[^.]+$/, '') + '.项目参数.json';
        modal('导出给编制助手', '<p>' + esc(filename) + '</p><div class="round-actions">' +
            '<button id="parameterSaveDefault" class="primary">保存到审查结果</button>' +
            '<button id="parameterSaveOther">' + (window.showSaveFilePicker ? '另存为…' : '浏览器下载') + '</button></div>');
        $('#parameterSaveDefault').onclick = () => {
            $('#dialog').close();
            return run(() => api('/api/extended/parameters-save', {id}));
        };
        $('#parameterSaveOther').onclick = () => {
            $('#dialog').close();
            return run(async () => {
                const handle = window.showSaveFilePicker && await window.showSaveFilePicker({
                    suggestedName: filename, types: [{description: '项目参数', accept: {'application/json': ['.json']}}]
                });
                if (handle && !handle.name.endsWith('.项目参数.json'))
                    throw Error('文件名须以「.项目参数.json」结尾。');
                const result = await api('/api/extended/parameters-export', {id});
                if (!result.exported) return result;
                const file = new Blob([JSON.stringify(result.package)], {type: 'application/json'});
                if (handle) {
                    const out = await handle.createWritable();
                    await out.write(file);
                    await out.close();
                } else {
                    const url = URL.createObjectURL(file);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = result.filename;
                    link.click();
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                }
                return result;
            });
        };
    };
})();
