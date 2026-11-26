"""视觉升级入口：沿用 v19 的全部接口，只在页面上追加视觉样式和成效看板。"""
from pathlib import Path
import json, runpy, sys, threading, webbrowser

ROOT = Path(__file__).parent
previous = runpy.run_path(str(ROOT / 'server_v19.py'), init_globals={'_test_transport': globals().get('_test_transport')})
ctx = previous['ctx']; X = previous['X']; LocalServer = previous['LocalServer']
desktop_state = previous['desktop_state']
runpy.run_path(str(ROOT / '整改工作流_v2.py'))['install'](ctx, X)

STATIC = {
    '/parallel.js': ('并行审查界面_v1.js', 'application/javascript'),
    '/rectify.js': ('整改交付_v1.js', 'application/javascript'),
    '/rectify.css': ('整改交付_v1.css', 'text/css'),
    '/visual.css': ('视觉升级_v1.css', 'text/css'),
    '/impact.js': ('成效看板_v3.js', 'application/javascript'),
}
PAGE = '施工方案AI审查_v17.html'


def page_bytes():
    html = (ROOT / PAGE).read_text(encoding='utf-8')
    html = html.replace('</head>', '<link rel="stylesheet" href="/visual.css"><link rel="stylesheet" href="/rectify.css"></head>', 1)
    head, sep, tail = html.rpartition('</body>')
    return (head + '<script src="/impact.js"></script><script src="/rectify.js"></script><script src="/parallel.js"></script>' + sep + tail).encode('utf-8')


PARALLEL_LOCK = threading.Lock()

class Handler(previous['Handler']):
    def do_GET(self):
        if self.path == '/api/parallel-settings':
            runtime = ctx['E']['RUNTIME']
            return self.reply(dict(lanes=runtime['settings']().get('并发请求数',5),
                                   average=runtime['recent_initial_seconds']()))
        if self.path == '/':
            return self.reply(page_bytes(), ctype='text/html; charset=utf-8')
        if self.path in STATIC:
            name, kind = STATIC[self.path]
            return self.reply((ROOT / name).read_bytes(), ctype=kind + '; charset=utf-8')
        return super().do_GET()

    def do_POST(self):
        if self.path != '/api/parallel-settings':
            return super().do_POST()
        if self.headers.get('X-Prototype-Token') != ctx['TOKEN']:
            return self.reply({'error':'请刷新客户端。'},403)
        try:
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<=256:raise ValueError('设置内容无效。')
            runtime=ctx['E']['RUNTIME']
            value=runtime['parallel_limit'](json.loads(self.rfile.read(size)).get('lanes'))
            with PARALLEL_LOCK:
                if any(j['status']=='running' for j in [*ctx['JOBS'].values(),*X['BATCHES'].values()]):
                    raise ValueError('审查期间并发设置已锁定。')
                config=runtime['settings']()
                config['并发请求数']=value
                runtime['atomic_json'](runtime['CONFIG'],config)
            return self.reply({'lanes':value})
        except (OSError,ValueError,AttributeError) as exc:
            return self.reply({'error':str(exc)},400)


def create_server():
    for port in range(8876, 8896):
        try:
            server = LocalServer(('127.0.0.1', port), Handler); server.daemon_threads = True; return server
        except OSError:
            continue
    raise ValueError('本地服务端口已占用，请关闭不再使用的审查窗口。')


def main():
    server = create_server(); url = f'http://127.0.0.1:{server.server_port}'
    if '--no-open' not in sys.argv: webbrowser.open(url)
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == '__main__': main()
