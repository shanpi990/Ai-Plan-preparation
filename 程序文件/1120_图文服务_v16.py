"""新版入口；复用原审查流程，增加图文、整改和调试功能。"""
from pathlib import Path
import runpy,json,io,threading,sys,webbrowser,socket
ROOT=Path(__file__).parent
runtime_paths=list(sys.path)
base=runpy.run_path(str(ROOT/'1120_审查服务基础_v12.py'))
# 旧引擎会插入历史虚拟环境路径；新版使用启动入口选定的完整运行环境。
sys.path[:]=runtime_paths
ctx=base['Handler'].do_POST.__globals__
structured=runpy.run_path(str(ROOT/'1120_结构化回查_v2.py'))
structured['install'](ctx['E'])
X=runpy.run_path(str(ROOT/'1120_基础功能_v16.py'))
X['install'](ctx,transport=globals().get('_test_transport'))

class Handler(base['Handler']):
    def do_GET(self):
        if self.path=='/':return self.reply((ROOT/'1117_施工方案AI审查_v15.html').read_bytes(),ctype='text/html; charset=utf-8')
        if self.path=='/extended-ui.js':return self.reply((ROOT/'1117_界面扩展_v15.js').read_bytes(),ctype='application/javascript; charset=utf-8')
        return super().do_GET()
    def do_POST(self):
        if self.path in ('/api/start','/api/estimate'):
            try:
                if self.headers.get('X-Prototype-Token')!=ctx['TOKEN']:return self.reply({'error':'请刷新页面后重试。'},403)
                n=int(self.headers.get('Content-Length',0))
                if not 0<n<=85_000_000:raise ValueError('请求大小不正确。')
                data=json.loads(self.rfile.read(n))
                return self.reply(X['dispatch'](ctx,'/api/extended/'+('review-start' if self.path=='/api/start' else 'review-preview'),data))
            except Exception as exc:return self.reply({'error':str(exc)},400)
        if self.path.startswith('/api/extended/'):
            try:
                if self.headers.get('X-Prototype-Token')!=ctx['TOKEN']:return self.reply({'error':'请刷新页面后重试。'},403)
                n=int(self.headers.get('Content-Length',0))
                if not 0<n<=85_000_000:raise ValueError('请求为空或超过大小限制。')
                data=json.loads(self.rfile.read(n))
                return self.reply(X['dispatch'](ctx,self.path,data))
            except Exception as exc:return self.reply({'error':str(exc) if isinstance(exc,(ValueError,KeyError)) else '处理失败：'+str(exc)},400)
        if self.path in ('/api/start','/api/resume','/api/import-result','/api/stop'):
            n=int(self.headers.get('Content-Length',0))
            if not 0<n<=85_000_000:return self.reply({'error':'请求大小不正确。'},400)
            raw=self.rfile.read(n);self.rfile=io.BytesIO(raw)
            try:
                data=json.loads(raw)
                if self.headers.get('X-Prototype-Token')!=ctx['TOKEN']:return self.reply({'error':'请刷新页面后重试。'},403)
                if self.path in ('/api/start','/api/resume'):
                    cfg=ctx['E']['resolve_config'](data.get('config',{}))
                    docs=([ctx['DOCS'][data['sha256']]]+[ctx['DOCS'][h] for h in data.get('design',[])]) if self.path=='/api/start' else ctx['JOB_DOCS'][data['id']]
                    for doc in docs:
                        if doc is None:raise ValueError('请先关联原文。')
                        X['register'](doc)
                        if doc.get('needsPageRendering') and cfg.get('visionEnabled'):raise ValueError('本文件含PDF页面或未读取的图表，请重新导入文件，等待自动提取完成后再诊断。')
                        if any(r.get('imageIds') for r in doc['rows']) and not cfg.get('visionModel'):raise ValueError('请在模型设置填写视觉模型。')
                if self.path=='/api/stop' and (any(t.get('status')=='running' for t in X['OPERATIONS'].values()) or any(b.get('status')=='running' for b in X['BATCHES'].values())):
                    raise ValueError('整改生成、页面转换或批量诊断仍在运行，请等结束后关闭。')
            except Exception as exc:return self.reply({'error':str(exc)},400)
            result=super().do_POST()
            if self.path=='/api/import-result':
                sys.path[:]=runtime_paths
                for docs in ctx['JOB_DOCS'].values():
                    for d in docs:
                        if d is None:continue
                        rawdoc=ctx['RAW_DOCS'].get(d['sha256'])
                        if rawdoc and not d.get('visionVersion'):X['enrich'](d,rawdoc,ctx['E'])
                        X['register'](d)
            return result
        return super().do_POST()

class LocalServer(base['ThreadingHTTPServer']):
    allow_reuse_address=False
    def server_bind(self):
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()

def main():
    server=None
    for port in range(8876,8896):
        try:server=LocalServer(('127.0.0.1',port),Handler);break
        except OSError:continue
    if server is None:raise SystemExit('8876～8895端口均已占用。')
    server.daemon_threads=True;url=f'http://127.0.0.1:{port}';print(url,flush=True)
    if '--no-open' not in sys.argv:webbrowser.open(url)
    try:server.serve_forever()
    finally:server.server_close()
if __name__=='__main__':main()
