"""模型在线程池中执行；调度、限流记录、回调和断点均由调用线程维护。"""
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from time import monotonic


class ReviewPool:
    def __init__(self, maximum, visual_limit, job):
        self.maximum, self.limit, self.visual_limit = maximum, maximum, visual_limit
        self.job = job
        self.clean = self.timeouts = 0
        self.executor = ThreadPoolExecutor(max_workers=maximum, thread_name_prefix='review')
        self.job['parallelRequested'] = maximum
        self.job.setdefault('parallelPeak', 0)
        self.job.setdefault('parallelAdjustments', [])

    def adjust(self, work, new, reason):
        if self.limit != new:
            change = dict(batch=work['record']['batch'], before=self.limit, after=new, reason=reason)
            self.job['parallelAdjustments'].append(change)
            work['adjustments'].append(change)
            self.limit = new

    def rate(self, work, reason):
        if reason == 'HTTP 429':
            self.clean = self.timeouts = 0
            self.adjust(work, max(1, self.limit // 2), 'HTTP 429')
        elif 'timeout' in reason.lower():
            self.clean = 0
            self.timeouts += 1
            if self.timeouts >= 2:
                self.adjust(work, max(1, self.limit // 2), '连续超时')
                self.timeouts = 0

    def execute(self, items, call, commit, discard, progress):
        events, halt = Queue(), Event()
        active, ready = {}, {}
        sent = cursor = completed = running = 0
        failure = None
        throttled = set()

        def run(i):
            work = items[i]
            events.put(('start', i, None))
            start = monotonic()
            try:
                work['result'] = call(work, lambda reason: events.put(('rate', i, reason)))
            except Exception as exc:
                work['error'] = exc
                halt.set()
            finally:
                work['record']['requestSeconds'] = round(monotonic() - start, 3)
                events.put(('end', i, None))

        while active or (sent < len(items) and not halt.is_set() and not self.job.get('cancel')):
            while (sent < len(items) and len(active) < self.limit and not halt.is_set()
                   and not self.job.get('cancel') and events.empty()):
                visual = items[sent]['visual']
                if visual and sum(active.values()) >= self.visual_limit:
                    break
                active[sent] = visual
                self.executor.submit(run, sent)
                sent += 1
            if not active:
                break
            event, i, reason = events.get()
            work = items[i]
            if event == 'start':
                running += 1
                self.job['parallelPeak'] = max(self.job['parallelPeak'],running)
                continue
            if event == 'rate':
                if reason == 'HTTP 429' or 'timeout' in reason.lower():
                    throttled.add(i)
                self.rate(work, reason)
                progress(completed, self.limit)
                continue
            del active[i]
            running -= 1
            ready[i] = work
            if 'error' not in work:
                completed += 1
                if i not in throttled:
                    self.timeouts = 0
                    self.clean += 1
                    if self.clean >= 5:
                        self.adjust(work, min(self.maximum, self.limit + 1), '连续五批正常')
                        self.clean = 0
            else:
                self.clean = 0
            progress(completed, self.limit)
            while cursor in ready:
                row = ready.pop(cursor)
                if failure is None:
                    try:
                        commit(row)
                    except Exception as exc:
                        halt.set()
                        failure = exc
                else:
                    discard(row)
                cursor += 1
        if failure is not None:
            raise failure

    def close(self):
        self.executor.shutdown(wait=True)

