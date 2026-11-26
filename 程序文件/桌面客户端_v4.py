"""独立 WebView2 窗口；本次后台服务随窗口退出。"""
from pathlib import Path
import sys,os,json,runpy,threading,traceback,time,ctypes,base64
ROOT=Path(__file__).resolve().parent;TASK=ROOT.parent
WORK=TASK/'运行数据'
WORK.mkdir(parents=True,exist_ok=True)
os.environ['TEMP']=os.environ['TMP']=str(WORK)
sys.path.insert(0,str(ROOT/'客户端运行库_v1'))
LOG=WORK/'客户端运行日志_v2.log'
if sys.stdout is None:sys.stdout=LOG.open('a',encoding='utf-8')
if sys.stderr is None:sys.stderr=sys.stdout

def main():
    import webview
    webview.settings["ALLOW_DOWNLOADS"]=True
    testing=False
    def no_model(*args,**kwargs):raise AssertionError('桌面验证禁止调用模型。')
    entry='server_v21.py' if '--legacy' in sys.argv else '复审对照服务_v25.py'
    module=runpy.run_path(str(ROOT/entry),init_globals={'_test_transport':no_model if testing else None})

    # 交付版打开脱敏节选记录，配套原件仍由客户端按 SHA-256 关联。
    example=TASK/'审查记录'/'深基坑216条审查演示_v1.json'
    if example.is_file():
        try:
            ctx=module['ctx']
            job,reviews,docs=ctx['I']['import_record'](json.loads(example.read_text('utf-8-sig')),ctx['DOCS'],ctx['RAW_DOCS'],ROOT)
            jid=job['id']
            ctx['JOBS'][jid]=job
            ctx['JOB_DOCS'][jid]=docs
            ctx['REVIEWS'][jid]=reviews
            for doc in docs:
                if doc:
                    ctx['DOCS'][doc['sha256']]=doc
                    module['X']['register'](doc)
            ctx['ACTIVE_ID']=jid
        except (OSError,ValueError,KeyError):
            with LOG.open('a',encoding='utf-8') as log:log.write(traceback.format_exc())
    server=module['create_server']();url=f'http://127.0.0.1:{server.server_port}'
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    class Bridge:
        def __init__(self):self._window=None;self._allow=False;self._loaded=False
        def pick_submission(self):
            return module['native_selection'](self._window)
        def save_project_parameters(self,jid):
            try:
                return module['save_parameters_as'](self._window,jid)
            except (OSError, ValueError) as exc:
                return {'error':str(exc)}
        def finish_close(self):
            if module['desktop_state']()['busy']:return {'ok':False,'error':'仍有任务在运行，请等当前请求结束。'}
            self._allow=True
            # 先把成功结果返回 JS，待桥接回调结束再销毁 WebView。
            threading.Timer(.35,self._window.destroy).start()
            return {'ok':True}
        def open_data_folder(self):
            os.startfile(str(TASK))
            return True
        def set_theme(self,theme):
            try:
                handle=self._window.native.Handle.ToInt64();dark=ctypes.c_int(theme=='dark')
                ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(handle),20,ctypes.byref(dark),ctypes.sizeof(dark))
            except Exception:pass
            return True
    bridge=Bridge()
    window=webview.create_window('施工方案 AI 审查',url,js_api=bridge,width=1520,height=980,min_size=(1060,740),background_color='#ffffff',hidden=testing)
    bridge._window=window
    def closing():
        if bridge._allow:return True
        if not bridge._loaded and not module['desktop_state']()['busy']:return True
        threading.Thread(target=lambda:window.run_js('window.requestDesktopClose && window.requestDesktopClose()'),daemon=True).start()
        return False
    def loaded():
        bridge._loaded=True
        try:
            from System.Drawing import Icon
            window.native.Icon=Icon(str(ROOT/'客户端图标_v1.ico'))
        except Exception:pass
    window.events.closing+=closing;window.events.loaded+=loaded
    try:
        profile=TASK/'配置文件'/'客户端浏览数据_v1'
        webview.start(None,gui='edgechromium',debug=False,private_mode=False,storage_path=str(profile))
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
if __name__=='__main__':
    try:main()
    except Exception:
        with LOG.open('a',encoding='utf-8') as f:f.write(time.strftime('\n%Y-%m-%d %H:%M:%S\n')+traceback.format_exc())
        if '--self-test' not in sys.argv:ctypes.windll.user32.MessageBoxW(None,'客户端未能启动，请查看“运行数据”中的客户端运行日志。','施工方案 AI 审查',0x10)
        else:raise
